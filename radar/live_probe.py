"""Teste de integração somente leitura com Nintendo BR.

Não envia e-mail, não grava estado, não inventa descontos.
Falha se nem mesmo um preço regular válido puder ser confirmado.
"""
from __future__ import annotations

import logging
import os
import requests

from .nintendo_catalog import (
    GUEST_PRICES_URL, fetch_catalog, fetch_guest_prices,
    fetch_regional_prices, _brl_amount
)

LOG = logging.getLogger("radar.live_probe")


def run() -> int:
    session = requests.Session()
    samples = ("Super Mario Bros. Wonder", "Mario Kart 8 Deluxe",
               "Metroid Dread", "The Legend of Zelda: Breath of the Wild")
    catalog, ambiguous = fetch_catalog(session, samples)
    LOG.info("Catálogo Nintendo BR: resolvidos=%d/%d ambiguos=%d",
             len(catalog), len(samples), ambiguous)
    if not catalog:
        LOG.error("Nenhum jogo resolvido no catálogo Nintendo.")
        return 1
    products = list(catalog.values())[:4]
    regular_found = 0
    valid_responses = 0
    sale_count = 0
    for product in products:
        response = session.get(
            GUEST_PRICES_URL, params=[("ns_uids", product.nsuid)],
            timeout=(10, 25), allow_redirects=False)
        response.raise_for_status()
        from urllib.parse import urlparse
        target = urlparse(response.url)
        if target.scheme != "https" or target.hostname != "ec.nintendo.com":
            raise RuntimeError("Destino de preços inesperado")
        payload = response.json()
        if not isinstance(payload, list):
            LOG.warning("guest_prices formato inesperado para %s: %s",
                        product.title, type(payload).__name__)
            continue
        valid_responses += 1
        for row in payload:
            if not isinstance(row, dict) or str(row.get("id")) != product.nsuid:
                continue
            prices = row.get("price")
            if not isinstance(prices, dict):
                continue
            regular = _brl_amount(prices.get("regular_price"))
            if regular is not None and regular > 0:
                regular_found += 1
            LOG.info("guest_prices %s: status=%s preço_normal_BRL=%s desconto_BRL=%s",
                     product.title, row.get("sales_status"),
                     regular is not None,
                     _brl_amount(prices.get("discount_price")) is not None)
    diagnostics = {}
    sales = fetch_guest_prices(session, catalog, diagnostics)
    sale_count = len(sales)
    LOG.info("guest_prices: respostas_válidas=%d preços_normais_BRL=%d promoções=%d diagnóstico=%s",
             valid_responses, regular_found, sale_count, diagnostics)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as file:
            file.write("\n## Teste real Nintendo eShop BR\n\n")
            file.write(f"- Títulos resolvidos: {len(catalog)}/{len(samples)}\n")
            file.write(f"- Respostas individuais válidas: {valid_responses}\n")
            file.write(f"- Preços normais confirmados em BRL: {regular_found}\n")
            file.write(f"- Promoções ativas verificadas: {sale_count}\n")
            file.write("- E-mail e histórico: não alterados\n")
    if not regular_found:
        LOG.error("FALHOU: nenhum preço normal da eShop Brasil foi confirmado.")
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
