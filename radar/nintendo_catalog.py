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

def price_response_diagnostics(payload: dict, products: dict[str, CatalogProduct]) -> dict:
    """Diagnostica preços sem expor valores não verificados ou credenciais."""
    if not isinstance(payload, dict):
        return {"error": "resposta não é objeto"}
    rows = payload.get("prices")
    if not isinstance(rows, list):
        return {"error": "prices ausente ou não é lista", "fields": sorted(payload)[:15]}
    ids = {p.nsuid for p in products.values()}
    relevant = [r for r in rows if isinstance(r, dict) and
                str(r.get("title_id", "")) in ids]
    return {
        "api_rows": len(rows),
        "ids_solicitados": len(ids),
        "ids_reconhecidos": len(relevant),
        "com_preco_normal": sum(isinstance(r.get("regular_price"), dict) for r in relevant),
        "com_preco_promocional": sum(isinstance(r.get("discount_price"), dict) for r in relevant),
        "com_preco_BRL": sum(_brl_amount(r.get("discount_price")) is not None for r in relevant),
        "statuses": sorted({str(r.get("sales_status", "")) for r in relevant})[:8],
        "price_fields": sorted({k for r in relevant[:2] for k in r.keys()})[:15],
        "sale_fields": sorted({k for r in relevant[:2]
                               if isinstance(r.get("discount_price"), dict)
                               for k in r["discount_price"].keys()})[:15],
    }


OFFICIAL_SALES_API = "https://ec.nintendo.com/api/BR/pt/search/sales"


def fetch_official_sales_list(session: requests.Session, max_pages: int = 3
                              ) -> tuple[list[dict], dict]:
    """Catálogo de ofertas eShop BR; endpoint antigo, disponibilidade incerta.

    Usamos apenas NSUIDs que possam ser ligados com segurança a um jogo
    e posteriormente confirmados na API regional de preços.
    """
    collected: list[dict] = []
    stats = {"pages": 0, "items": 0, "total": None, "fields": []}
    for page in range(max(1, min(max_pages, 5))):
        resp = session.get(
            OFFICIAL_SALES_API, params={"count": 50, "offset": 50 * page},
            headers={"User-Agent": "RadarSwitchMVP/1.0"},
            timeout=(8, 20), allow_redirects=False,
        )
        resp.raise_for_status()
        target = urlparse(resp.url)
        if target.scheme != "https" or target.hostname != "ec.nintendo.com":
            raise ValueError("Redirecionamento não autorizado na lista de ofertas")
        data = resp.json()
        if not isinstance(data, dict) or not isinstance(data.get("contents"), list):
            raise ValueError("Formato inesperado na lista oficial de ofertas")
        entries = data["contents"]
        stats["pages"] += 1
        stats["items"] += len(entries)
        stats["total"] = data.get("total") if isinstance(data.get("total"), int) else None
        stats["fields"] = sorted({k for item in entries[:3]
                                   if isinstance(item, dict) for k in item.keys()})[:25]
        collected.extend(item for item in entries if isinstance(item, dict))
        if len(entries) < 50:
            break
    return collected, stats


def match_official_sales_ids(items: list[dict],
                             catalog: dict[str, CatalogProduct]
                             ) -> dict[str, CatalogProduct]:
    """A lista oficial precisa trazer o MESMO NSUID do catálogo validado."""
    known = {p.nsuid: p for p in catalog.values()}
    found: dict[str, CatalogProduct] = {}
    for item in items:
        identifier = str(item.get("id", ""))
        if identifier in known:
            found[known[identifier].title] = known[identifier]
    return found


def _brl_amount(raw: object) -> Decimal | None:
    if not isinstance(raw, dict) or raw.get("currency") != "BRL":
        return None
    value = raw.get("raw_value", raw.get("amount"))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)
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
    if not isinstance(payload, dict) or (
        payload.get("country") not in (None, "BR")
    ):
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


GUEST_PRICES_URL = "https://ec.nintendo.com/api/BR/pt/guest_prices"


def parse_guest_prices(payload: object, products: dict[str, CatalogProduct],
                       now: datetime | None = None) -> list[VerifiedPrice]:
    """Resposta real da rota BR: lista de objetos com id e price.*.

    Aceitar apenas BRL e desconto válido; status on sale pode existir sem
    desconto, portanto não prova promoção.
    """
    if not isinstance(payload, list):
        raise ValueError("guest_prices não retornou uma lista")
    catalog = {item.nsuid: item for item in products.values()}
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    seen: set[str] = set()
    verified = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        nsuid = str(item.get("id", ""))
        if nsuid not in catalog or nsuid in seen:
            continue
        seen.add(nsuid)
        prices = item.get("price")
        if not isinstance(prices, dict):
            continue
        regular = _brl_amount(prices.get("regular_price"))
        promotion = prices.get("discount_price")
        discounted = _brl_amount(promotion)
        if (regular is None or discounted is None or
                not Decimal("0") < discounted < regular):
            continue
        if not _sale_is_current(promotion, now):
            continue
        percent = int(((regular - discounted) / regular * 100).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP))
        if 1 <= percent <= 99:
            verified.append(VerifiedPrice(catalog[nsuid], discounted, regular, percent))
    return verified


def fetch_guest_prices(session: requests.Session,
                       products: dict[str, CatalogProduct],
                       diagnostics: dict | None = None) -> list[VerifiedPrice]:
    """Consulta lotes BR de até 99 NSUIDs; falha do lote tenta unidades."""
    if not products:
        return []
    values = list(products.values())
    result: dict[str, VerifiedPrice] = {}
    stats = {"batches": 0, "items": 0, "prices": 0,
             "batch_failures": 0, "individual_failures": 0}
    for offset in range(0, len(values), 99):
        batch = values[offset:offset + 99]
        ids = [p.nsuid for p in batch]

        def request_group(group: list[str]) -> object:
            # Lista de tuplas produz query "ns_uids=...&ns_uids=..." sem
            # misturar a região BR com outra localização.
            response = session.get(
                GUEST_PRICES_URL, params=[("ns_uids", value) for value in group],
                headers={"User-Agent": "RadarSwitchMVP/1.0"},
                timeout=(10, 25), allow_redirects=False)
            response.raise_for_status()
            target = urlparse(response.url)
            if target.scheme != "https" or target.hostname != "ec.nintendo.com":
                raise ValueError("Destino inesperado para guest_prices")
            return response.json()

        stats["batches"] += 1
        try:
            payload = request_group(ids)
            if not isinstance(payload, list):
                raise ValueError("Formato não-lista retornado pelo lote")
            subset = {p.title: p for p in batch}
            offers = parse_guest_prices(payload, subset)
            stats["items"] += len(payload)
            for offer in offers:
                result[offer.product.nsuid] = offer
        except (requests.RequestException, ValueError, TypeError):
            stats["batch_failures"] += 1
            for product in batch:
                try:
                    data = request_group([product.nsuid])
                    if not isinstance(data, list):
                        raise ValueError("Resposta individual inválida")
                    stats["items"] += len(data)
                    for offer in parse_guest_prices(data, {product.title: product}):
                        result[offer.product.nsuid] = offer
                except (requests.RequestException, ValueError, TypeError):
                    stats["individual_failures"] += 1
    stats["prices"] = len(result)
    if diagnostics is not None:
        diagnostics.update(stats)
    if stats["batch_failures"] and not stats["items"]:
        raise RuntimeError("Nenhuma resposta de preços válida em guest_prices BR")
    return list(result.values())


def fetch_regional_prices(session: requests.Session,
                          products: dict[str, CatalogProduct],
                          diagnostics: dict | None = None) -> list[VerifiedPrice]:
    if not products:
        return []
    ids = ",".join(sorted({p.nsuid for p in products.values()}))
    response = session.get(PRICE_URL,
                           params={"country": "BR", "ids": ids, "lang": "en"},
                           headers={"User-Agent": "RadarSwitchMVP/1.0"},
                           timeout=(10, 25), allow_redirects=False)
    response.raise_for_status()
    parts = urlparse(response.url)
    if parts.scheme != "https" or parts.hostname != "api.ec.nintendo.com":
        raise ValueError("Redirecionamento inesperado na API Nintendo")
    payload = response.json()
    if diagnostics is not None:
        diagnostics.update(price_response_diagnostics(payload, products))
    return parse_regional_prices(payload, products)
