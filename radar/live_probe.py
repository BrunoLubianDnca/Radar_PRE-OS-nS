"""Teste de integração somente leitura com Nintendo BR.

Não envia e-mail, não grava estado, não inventa descontos.
Falha se nem mesmo um preço regular válido puder ser confirmado.
"""
from __future__ import annotations

import logging
import os
import requests

from .nintendo_watch import WATCHED_GAMES

from .nintendo_catalog import (
    GUEST_PRICES_URL, fetch_catalog, fetch_guest_prices,
    fetch_regional_prices, _brl_amount, PRICE_URL, price_response_diagnostics
)

LOG = logging.getLogger("radar.live_probe")


def run() -> int:
    session = requests.Session()
    samples = WATCHED_GAMES
    catalog, ambiguous = fetch_catalog(session, samples)
    LOG.info("Catálogo Nintendo BR: resolvidos=%d/%d ambiguos=%d",
             len(catalog), len(samples), ambiguous)
    if not catalog:
        LOG.error("Nenhum jogo resolvido no catálogo Nintendo.")
        return 1
    products = list(catalog.values())
    # A API mais recente é testada independentemente da rota guest_prices,
    # que retornou HTTP 404 na execução de 06/11/2026.
    params = {"country": "BR", "ids": ",".join(p.nsuid for p in products),
              "lang": "en"}
    latest = session.get(PRICE_URL, params=params, timeout=(10, 25),
                         allow_redirects=False)
    latest.raise_for_status()
    from urllib.parse import urlparse
    latest_url = urlparse(latest.url)
    if latest_url.scheme != "https" or latest_url.hostname != "api.ec.nintendo.com":
        raise RuntimeError("Destino inesperado na API regional")
    latest_payload = latest.json()
    latest_stats = price_response_diagnostics(
        latest_payload, {p.title: p for p in products})
    LOG.info("API regional v1/price BR: %s", latest_stats)
    latest_rows = (latest_payload.get("prices", [])
                   if isinstance(latest_payload, dict) else [])
    latest_regular = sum(
        isinstance(row, dict) and
        str(row.get("title_id")) in {p.nsuid for p in products} and
        _brl_amount(row.get("regular_price")) is not None
        for row in latest_rows
    )
    LOG.info("API regional v1/price: preços regulares BRL=%d", latest_regular)
    # Preços efetivamente retornados pela Nintendo, incluindo jogos sem desconto.
    by_nsuid = {p.nsuid: p for p in products}
    price_table = []
    for row in latest_rows:
        if not isinstance(row, dict):
            continue
        product = by_nsuid.get(str(row.get("title_id")))
        if product is None:
            continue
        regular = _brl_amount(row.get("regular_price"))
        promotional = _brl_amount(row.get("discount_price"))
        if regular is None:
            continue
        actual = promotional if promotional is not None and promotional < regular else regular
        pct = round((regular - actual) / regular * 100) if regular else 0
        def brl(v):
            return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        price_table.append((product.title, brl(actual), brl(regular),
                            pct, product.shop_url))
    for title, current, regular, discount, official_url in sorted(price_table):
        LOG.info("PREÇO NINTENDO BR: %s | %s | normal %s | -%d%% | %s",
                 title, current, regular, discount, official_url)

    regular_found = 0
    valid_responses = 0
    sale_count = 0
    try:
        for product in products[:2]:
            try:
                response = session.get(
                    GUEST_PRICES_URL, params=[("ns_uids", product.nsuid)],
                    timeout=(10, 15), allow_redirects=False)
                LOG.info("guest_prices %s: HTTP %s", product.title, response.status_code)
                if response.status_code != 200:
                    continue
                payload = response.json()
                if isinstance(payload, list):
                    valid_responses += 1
                    for row in payload:
                        if not isinstance(row, dict) or str(row.get("id")) != product.nsuid:
                            continue
                        prices = row.get("price")
                        if isinstance(prices, dict):
                            regular = _brl_amount(prices.get("regular_price"))
                            regular_found += int(regular is not None and regular > 0)
            except (requests.RequestException, ValueError):
                LOG.warning("guest_prices indisponível para %s", product.title)
    except (requests.RequestException, RuntimeError) as exc:
        LOG.warning("Rota guest_prices indisponível: %s", exc)
    diagnostics = {}
    if valid_responses:
        sales = fetch_guest_prices(session, catalog, diagnostics)
        sale_count = len(sales)
    LOG.info("guest_prices legado: respostas_válidas=%d preços_normais_BRL=%d promoções=%d",
             valid_responses, regular_found, sale_count)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as file:
            file.write("\n## Teste real Nintendo eShop BR\n\n")
            file.write(f"- Títulos resolvidos: {len(catalog)}/{len(samples)}\n")
            file.write("\n| Jogo | Preço atual | Preço normal | Desconto | Loja oficial |\n")
            file.write("|---|---:|---:|---:|---|\n")
            for title, current, regular, discount, official_url in sorted(price_table):
                safe_title = title.replace("|", " ")
                file.write(f"| {safe_title} | {current} | {regular} | {discount}% | [Nintendo]({official_url}) |\n")

            file.write(f"- Respostas individuais válidas: {valid_responses}\n")
            file.write(f"- Preços normais confirmados em BRL: {regular_found}\n")
            file.write(f"- Promoções ativas verificadas: {sale_count}\n")
            file.write("- E-mail e histórico: não alterados\n")
    if not latest_regular:
        LOG.error("FALHOU: nenhum preço normal BRL confirmado na API regional atual.")
        return 1
    LOG.info("APROVADO: integração real BR devolveu preços normais verificáveis.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        raise SystemExit(run())
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        LOG.error("FALHOU: %s", exc)
        raise SystemExit(1)
