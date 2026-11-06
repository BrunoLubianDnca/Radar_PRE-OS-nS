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
from .official_sales import is_official_product_url

ALGOLIA_URL = "https://u3b6gr4ua3-dsn.algolia.net/1/indexes/*/queries"
ALGOLIA_APP = "U3B6GR4UA3"
# Chave pública de pesquisa (não credencial de usuário).
ALGOLIA_SEARCH_KEY = "9a20c93440cf63cf1a7008d75f7438bf"
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
                   "titleName")
                  if isinstance(hit.get(key), str) and hit[key].strip()), "")
    raw_id = next((hit[key] for key in
                   ("nsuid", "nsuid_br", "nsuidBR", "title_id", "titleId")
                   if isinstance(hit.get(key), (str, int))), "")
    if not raw_id and isinstance(hit.get("nsuids"), list):
        for item in hit["nsuids"]:
            if isinstance(item, (str, int)) and NSUID.fullmatch(str(item)):
                raw_id = item
                break
    return title.strip(), str(raw_id)


def _product_url(hit: dict) -> str:
    for field in ("url", "product_url", "productUrl", "product_page_url",
                  "productPageUrl", "canonical_url"):
        raw = hit.get(field)
        if not isinstance(raw, str):
            continue
        url = ("https://www.nintendo.com" + raw
               if raw.startswith("/pt-br/store/products/") else raw)
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
    queries = [{"indexName": "ncom_game_pt_br",
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


def _brl_amount(raw: object) -> Decimal | None:
    if not isinstance(raw, dict) or raw.get("currency") != "BRL":
        return None
    value = raw.get("amount")
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d{1,2})?", value):
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _sale_is_current(raw: dict, now: datetime) -> bool:
    for field, before in (("start_datetime", False), ("end_datetime", True)):
        when = raw.get(field)
        if not when:
            continue
        if not isinstance(when, str):
            return False
        try:
            dt = datetime.fromisoformat(when.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return False
            dt = dt.astimezone(timezone.utc)
        except ValueError:
            return False
        if before and now > dt:
            return False
        if not before and now < dt:
            return False
    return True


def parse_regional_prices(payload: dict, products: dict[str, CatalogProduct],
                          now: datetime | None = None) -> list[VerifiedPrice]:
    """Exige country=BR, currency=BRL e desconto ativo para ID cadastrado."""
    if not isinstance(payload, dict) or payload.get("country") != "BR":
        raise ValueError("Preço de outra região ou resposta inválida")
    prices = payload.get("prices")
    if not isinstance(prices, list):
        raise ValueError("Sem lista de preços da eShop Brasil")
    by_id = {p.nsuid: p for p in products.values()}
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    verified = []
    seen = set()
    for row in prices:
        if not isinstance(row, dict):
            continue
        nsuid = str(row.get("title_id", ""))
        if nsuid not in by_id or nsuid in seen:
            continue
        seen.add(nsuid)
        old = _brl_amount(row.get("regular_price"))
        sale_data = row.get("discount_price")
        sale = _brl_amount(sale_data)
        if old is None or sale is None or not (Decimal("0") < sale < old):
            continue
        if not _sale_is_current(sale_data, now):
            continue
        discount = int(((old - sale) / old * 100).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP))
        if not 1 <= discount <= 99:
            continue
        verified.append(VerifiedPrice(by_id[nsuid], sale, old, discount))
    return verified


def fetch_regional_prices(session: requests.Session,
                          products: dict[str, CatalogProduct]) -> list[VerifiedPrice]:
    if not products:
        return []
    ids = ",".join(sorted({p.nsuid for p in products.values()}))
    response = session.get(PRICE_URL,
                           params={"country": "BR", "ids": ids, "lang": "pt"},
                           headers={"User-Agent": "RadarSwitchMVP/1.0"},
                           timeout=(10, 25), allow_redirects=False)
    response.raise_for_status()
    parts = urlparse(response.url)
    if parts.scheme != "https" or parts.hostname != "api.ec.nintendo.com":
        raise ValueError("Redirecionamento inesperado na API Nintendo")
    return parse_regional_prices(response.json(), products)
