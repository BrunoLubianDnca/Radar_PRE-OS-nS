"""Busca individual no catálogo oficial Nintendo BR + preço eShop BR.

Usa endpoints públicos (não documentados) e falha fechada. NENHUM preço da
Algolia é usado como oferta; a API regional BR é a única fonte de preços.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlparse

import requests

from .nintendo_watch import WATCHED_GAMES, matched_watch_game
from .popular import is_popular
from .official_sales import is_official_product_url

ALGOLIA_URL = "https://u3b6gr4ua3-dsn.algolia.net/1/indexes/*/queries"
ALGOLIA_INDEX = "store_all_products_pt_br"
ALGOLIA_APP = "U3B6GR4UA3"
# Chave pública de pesquisa (não credencial de usuário).
ALGOLIA_SEARCH_KEY = "a29c6927638bfd8cee23993e51e721c9"
PRICE_URL = "https://api.ec.nintendo.com/v1/price"
NSUID = re.compile(r"^7001\d{10}$")


@dataclass(frozen=True)
class CatalogProduct:
    title: str
    nsuid: str
    shop_url: str


@dataclass(frozen=True)
class VerifiedPrice:
    product: CatalogProduct
    current: Decimal
    regular: Decimal
    discount: int


def _title_and_id(hit: dict) -> tuple[str, str]:
    title = next((hit[key] for key in
                  ("title", "name", "product_name", "productName", "title_name",
                   "titleName", "displayName")
                  if isinstance(hit.get(key), str) and hit[key].strip()), "")
    raw_id = next((hit[key] for key in
                   ("nsuid", "nsuid_br", "nsuidBR", "title_id", "titleId", "nsuidUS")
                   if isinstance(hit.get(key), (str, int))), "")
    if not raw_id and isinstance(hit.get("nsuids"), list):
        for item in hit["nsuids"]:
            if isinstance(item, (str, int)) and NSUID.fullmatch(str(item)):
                raw_id = item
                break
    return title.strip(), str(raw_id)


def _product_url(hit: dict) -> str:
    for field in ("url", "product_url", "productUrl", "product_page_url",
                  "productPageUrl", "canonical_url", "productUrlPath"):
        raw = hit.get(field)
        if not isinstance(raw, str):
            continue
        if raw.startswith("/pt-br/store/products/"):
            url = "https://www.nintendo.com" + raw
        elif raw.startswith("/store/products/"):
            # Mesmo slug oficial do índice brasileiro; URL localizada.
            url = "https://www.nintendo.com/pt-br" + raw
        else:
            url = raw
        if is_official_product_url(url):
            return url
    return ""


def parse_catalog_results(payload: dict, watched: tuple[str, ...] = WATCHED_GAMES
                          ) -> tuple[dict[str, CatalogProduct], int]:
    """Só aceita uma correspondência única de nome, NSUID e URL da edição Switch."""
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("Formato inesperado do catálogo Nintendo")
    found: dict[str, CatalogProduct] = {}
    ambiguous: set[str] = set()
    for block in payload["results"]:
        if not isinstance(block, dict) or not isinstance(block.get("hits"), list):
            raise ValueError("Lista de jogos inesperada no catálogo Nintendo")
        for hit in block["hits"]:
            if not isinstance(hit, dict):
                continue
            title, nsuid = _title_and_id(hit)
            watched_title = matched_watch_game(title)
            if watched_title not in watched or not NSUID.fullmatch(nsuid):
                continue
            url = _product_url(hit)
            if not url:
                continue
            # Rejeitar Switch 2 Editions, DLCs e resultados com descrição ambígua.
            low = title.casefold()
            if any(word in low for word in ("switch 2 edition", "upgrade pack",
                                           "pacote de melhoria", "passe de pistas")):
                continue
            product = CatalogProduct(watched_title, nsuid, url)
            if watched_title in found and found[watched_title] != product:
                ambiguous.add(watched_title)
            else:
                found[watched_title] = product
    for title in ambiguous:
        found.pop(title, None)
    return found, len(ambiguous)


def fetch_catalog(session: requests.Session,
                  watched: tuple[str, ...] = WATCHED_GAMES
                  ) -> tuple[dict[str, CatalogProduct], int]:
    """Uma busca multiquery para os títulos monitorados, não uma página limitada."""
    queries = [{"indexName": ALGOLIA_INDEX,
                "params": "query=" + requests.utils.quote(name, safe="") + "&hitsPerPage=8"}
               for name in watched]
    response = session.post(
        ALGOLIA_URL, json={"requests": queries},
        headers={"x-algolia-application-id": ALGOLIA_APP,
                 "x-algolia-api-key": ALGOLIA_SEARCH_KEY,
                 "User-Agent": "RadarSwitchMVP/1.0"},
        timeout=(10, 25), allow_redirects=False,
    )
    response.raise_for_status()
    if response.url.rstrip("/") != ALGOLIA_URL.rstrip("/"):
        raise ValueError("Redirecionamento inesperado no catálogo")
    return parse_catalog_results(response.json(), watched)


def catalog_diagnostics(payload: dict) -> dict:
    """Campos presentes nos primeiros resultados, sem registrar dados pessoais."""
    blocks = payload.get("results") if isinstance(payload, dict) else None
    hits = [hit for block in (blocks or [])
            if isinstance(block, dict)
            for hit in block.get("hits", [])
            if isinstance(hit, dict)]
    keys = sorted({k for hit in hits[:5] for k in hit.keys()})
    return {"hits": len(hits), "fields": keys[:40]}


def _is_original_switch(hit: dict, title: str, url: str) -> bool:
    """Não confundir a edição Switch original com Switch 2, DLC ou pacote."""
    if any(phrase in title.casefold() for phrase in (
        "switch 2 edition", "upgrade pack", "pacote de melhoria", "expansion pass",
        "season pass", "soundtrack", "trilha sonora"
    )):
        return False
    if not is_official_product_url(url):
        return False
    hardware = " ".join(str(hit.get(field) or "") for field in (
        "platform", "platformCode", "system", "productType"))
    if "SWITCH_2" in hardware.upper().replace(" ", "_"):
        return False
    if "Switch 2" in hardware and "Switch" not in hardware.replace("Switch 2", ""):
        return False
    return True


def parse_store_deal_hits(payload: dict) -> dict[str, CatalogProduct]:
    """Seleciona jogos acompanhados OU franquias populares na página Deals."""
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("Resposta Deals inválida")
    found: dict[str, CatalogProduct] = {}
    conflicts: set[str] = set()
    for block in payload["results"]:
        if not isinstance(block, dict) or not isinstance(block.get("hits"), list):
            raise ValueError("Resultados Deals inválidos")
        for hit in block["hits"]:
            if not isinstance(hit, dict):
                continue
            title, identifier = _title_and_id(hit)
            if not title or not NSUID.fullmatch(identifier):
                continue
            url = _product_url(hit)
            if not _is_original_switch(hit, title, url):
                continue
            tracked = matched_watch_game(title)
            if not tracked and not is_popular(title):
                continue
            title = tracked or title
            candidate = CatalogProduct(title, identifier, url)
            if title in found and found[title] != candidate:
                conflicts.add(title)
            else:
                found[title] = candidate
    for name in conflicts:
        found.pop(name, None)
    return found


def fetch_store_deals(session: requests.Session, pages: int = 2) -> tuple[dict[str, CatalogProduct], dict]:
    """Busca Deals pelo endpoint de consulta direta da loja Nintendo Brasil.

    Mantém um diagnóstico da consulta sem filtros se Deals vier vazio:
    distingue índice vazio de facet incompatível.
    """
    found: dict[str, CatalogProduct] = {}
    stats = {"hits": 0, "matches": 0, "fields": [], "pages": 0,
             "unfiltered_hits": None, "facet_unavailable": False}
    endpoint = f"https://u3b6gr4ua3-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"
    headers = {"x-algolia-application-id": ALGOLIA_APP,
               "x-algolia-api-key": ALGOLIA_SEARCH_KEY,
               "User-Agent": "RadarSwitchMVP/1.0",
               "Origin": "https://www.nintendo.com"}
    for page in range(max(1, min(pages, 3))):
        response = session.post(
            endpoint,
            json={"query": "", "hitsPerPage": 80, "page": page,
                  "filters": '(topLevelFilters:"Deals")'},
            headers=headers, timeout=(10, 25), allow_redirects=False,
        )
        response.raise_for_status()
        if response.url.rstrip("/") != endpoint.rstrip("/"):
            raise ValueError("Destino inesperado na consulta Deals Nintendo")
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("hits"), list):
            raise ValueError("Resposta inesperada do índice Deals Nintendo")
        hits = payload["hits"]
        stats["hits"] += len(hits)
        stats["pages"] += 1
        stats["fields"] = sorted({k for hit in hits[:3]
                                  if isinstance(hit, dict) for k in hit.keys()})[:40]
        found.update(parse_store_deal_hits({"results": [{"hits": hits}]}))
        if len(hits) < 80:
            break
    if stats["hits"] == 0:
        probe = session.post(
            endpoint, json={"query": "", "hitsPerPage": 1},
            headers=headers, timeout=(10, 25), allow_redirects=False,
        )
        probe.raise_for_status()
        if probe.url.rstrip("/") != endpoint.rstrip("/"):
            raise ValueError("Destino inesperado na sondagem Nintendo")
        payload = probe.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("hits"), list):
            raise ValueError("Sondagem Nintendo retornou estrutura inválida")
        stats["unfiltered_hits"] = len(payload["hits"])
        stats["facet_unavailable"] = bool(payload["hits"])
        stats["fields"] = sorted({k for hit in payload["hits"]
                                  if isinstance(hit, dict) for k in hit.keys()})[:40]
    stats["matches"] = len(found)
    return found, stats


