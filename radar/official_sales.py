"""Ofertas Nintendo oficiais extraídas SOMENTE de cartões completos da loja.

Nenhum preço de JavaScript, JSON parcial ou outra plataforma é inferido.
Se a Nintendo renderiza só via JS, retornamos lista vazia, sem falsos alertas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .nintendo_watch import matched_watch_game

CURRENCY = r"R\$\s*([\d.]+,\d{2})"
SALE = re.compile(r"Preço\s+promocional\s*:\s*" + CURRENCY, re.I)
REGULAR = re.compile(r"Preço\s+normal\s*:\s*" + CURRENCY, re.I)
SWITCH = re.compile(r"Nintendo\s+Switch(?!\s*2)", re.I)
PRODUCT_PATH = re.compile(r"^/pt-br/store/products/[a-z0-9-]+-switch/?$")


def is_official_product_url(url: str) -> bool:
    parts = urlparse(url)
    return (parts.scheme == "https" and parts.hostname == "www.nintendo.com"
            and parts.username is None and parts.password is None
            and bool(PRODUCT_PATH.fullmatch(parts.path))
            and not parts.query and not parts.fragment)


def brl_decimal(value: str) -> Decimal:
    return Decimal(value.replace(".", "").replace(",", "."))


@dataclass(frozen=True)
class OfficialSale:
    watched_title: str
    product_url: str
    price: Decimal
    old_price: Decimal
    discount: int


def parse_official_sales(html: str) -> list[OfficialSale]:
    """Requer preços e título vinculados à mesma ficha de produto no DOM."""
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, OfficialSale] = {}
    for anchor in soup.select("a[href]"):
        url = urljoin("https://www.nintendo.com", anchor.get("href", ""))
        if not is_official_product_url(url):
            continue
        # A âncora contém o título em alguns layouts; em outros, o H2/H3
        # fica dentro do cartão. Não usar o texto da página inteira.
        card = anchor
        while card.parent and card.name != "body":
            text = card.get_text(" ", strip=True)
            if len(text) > 1200:
                break
            if SALE.search(text) and REGULAR.search(text):
                break
            card = card.parent
        text = card.get_text(" ", strip=True)
        sale = SALE.search(text)
        regular = REGULAR.search(text)
        if not sale or not regular or len(text) > 1200:
            continue
        if not SWITCH.search(text) or "Switch 2 Edition" in text:
            continue
        links = [a for a in card.select("a[href]")
                 if "/store/products/" in a.get("href", "")]
        if len(links) > 2:
            continue  # bloco grande poderia misturar preços entre jogos
        headings = card.select("h2,h3,h4")
        names = [anchor.get_text(" ", strip=True)]
        names += [h.get_text(" ", strip=True) for h in headings]
        watched = next((matched_watch_game(name) for name in names
                        if matched_watch_game(name)), None)
        if not watched:
            continue
        price = brl_decimal(sale.group(1))
        old = brl_decimal(regular.group(1))
        if not (Decimal("0") < price < old):
            continue
        discount = int(((old - price) / old * 100).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP))
        if not 1 <= discount <= 99:
            continue
        found[watched] = OfficialSale(watched, url, price, old, discount)
    return list(found.values())
