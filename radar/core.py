"""Coleta conservadora de ofertas da eShop BR via páginas públicas.

O HTML de terceiros pode mudar. Qualquer ambiguidade faz a oferta ser ignorada,
nunca substituída por um preço adivinhado.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

BR = ZoneInfo("America/Sao_Paulo")
MONEY = r"R\$\s*([\d.]+,\d{2})"
DEAL_RE = re.compile(
    rf"Switch\s+digital\s+Nintendo\s+eShop\s+{MONEY}\s*-\s*(\d{{1,3}})%\s+{MONEY}",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"preços\s+de\s+(\d{2}/\d{2}/\d{4})", re.IGNORECASE)


@dataclass(frozen=True)
class Offer:
    title: str
    page_url: str
    shop_url: str
    price: Decimal
    old_price: Decimal
    discount: int
    critic: int
    player_positive: int
    player_reviews: int

    def as_dict(self) -> dict:
        return {"title": self.title, "page_url": self.page_url,
                "shop_url": self.shop_url, "price": str(self.price),
                "old_price": str(self.old_price), "discount": self.discount,
                "critic": self.critic, "player_positive": self.player_positive,
                "player_reviews": self.player_reviews}


def money(s: str) -> Decimal:
    return Decimal(s.replace(".", "").replace(",", "."))


def age_check(soup: BeautifulSoup, max_hours: int, now: datetime | None = None) -> None:
    text = soup.get_text(" ", strip=True)
    hit = DATE_RE.search(text)
    if hit is None:
        raise ValueError("Fonte sem data de preços verificável; coleta interrompida")
    day = datetime.strptime(hit.group(1), "%d/%m/%Y").date()
    now = (now or datetime.now(BR)).astimezone(BR)
    # Fonte informa somente o dia, não a hora de aferição.
    day_start = datetime.combine(day, datetime.min.time(), BR)
    if day_start > now or now - day_start > timedelta(hours=max_hours + 24):
        raise ValueError(f"Tabela possivelmente desatualizada: {day.isoformat()}")


def discovery(html: str, base: str, max_age_hours: int = 48,
              now: datetime | None = None) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    age_check(soup, max_age_hours, now)
    result: list[str] = []
    for a in soup.select('a[href]'):
        url = urljoin(base, a.get("href", ""))
        p = urlparse(url)
        if (p.scheme == "https" and p.hostname == "valeojogo.com.br"
                and re.fullmatch(r"/jogo/[a-zA-Z0-9_-]+/?", p.path)):
            normalized = f"https://valeojogo.com.br{p.path.rstrip('/')}/"
            if normalized not in result:
                result.append(normalized)
    if not result:
        raise ValueError("Nenhum jogo encontrado na vitrine; layout possivelmente alterado")
    return result


def _parse_reviews(text: str) -> tuple[int, int] | None:
    # Captura apenas o bloco 'Jogadores' antes de 'Onde comprar'.
    m = re.search(r"Jogadores\s+(\d{1,3})%\s+positivas\s+"
                  r"([\d.,]+(?:\s*mil)?)\s+análises", text, re.I)
    if not m:
        return None
    score = int(m.group(1))
    raw = m.group(2).replace("\u00a0", " ").strip()
    try:
        if raw.endswith("mil"):
            number = int(Decimal(raw[:-3].strip().replace(",", ".")) * 1000)
        else:
            number = int(raw.replace(".", ""))
    except (ValueError, InvalidOperation):
        return None
    return score, number


def parse_detail(html: str, page_url: str) -> Offer | None:
    """Extrai somente oferta DIGITAL da Nintendo; rejeita dados ambíguos.

    Aceita variações de espaços, hífens, quebras e ordem dos preços.
    Nunca usa preços de PC, Xbox, PlayStation ou mídia física.
    """
    log = logging.getLogger("radar-switch.parser")
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h1")
    if heading is None:
        log.warning("Sem titulo h1: %s", page_url)
        return None
    title = heading.get_text(" ", strip=True)
    text = soup.get_text(" ", strip=True)
    start = text.find("Onde comprar")
    end = text.find("Histórico de preço", start)
    if start < 0:
        log.warning("Secao Onde comprar ausente: %s", page_url)
        return None
    section = text[start:end] if end >= 0 else text[start:start + 4000]

    # Isolar a entrada da eShop, mesmo com outras plataformas na página.
    entry = re.search(r"Switch\s+digital\s+Nintendo\s+eShop", section, re.I)
    if entry is None:
        log.info("Sem oferta Switch digital eShop: %s", page_url)
        return None
    snippet = section[entry.end(): entry.end() + 280]
    # Os primeiros preços da entrada devem estar na sequência:
    # preço antigo, desconto, preço atual.
    deal = re.search(
        r"R\$\s*([\d.]+,\d{2})\s*[−–-]\s*(\d{1,3})\s*%\s*"
        r"R\$\s*([\d.]+,\d{2})",
        snippet, re.I
    )
    if not deal:
        log.warning("Preco/desconto eShop nao reconhecido: %s | %s",
                    page_url, snippet[:130])
        return None
    old_price, discount, price = (
        money(deal.group(1)), int(deal.group(2)), money(deal.group(3))
    )
    if not (Decimal("0") < price < old_price and 1 <= discount <= 99):
        log.warning("Valores eShop invalidos: %s", page_url)
        return None
    calculated = (Decimal(1) - price / old_price) * 100
    if abs(calculated - Decimal(discount)) > Decimal("1.5"):
        log.warning("Desconto nao confere: %s", page_url)
        return None

    before = text[:start]
    critic_match = (
        re.search(r"(\d{1,3})\s+Crítica\b", before, re.I)
        or re.search(r"Crítica\s+(\d{1,3})\b", before, re.I)
    )
    if critic_match is None:
        log.info("Sem nota de critica: %s", page_url)
        return None
    reviews = _parse_reviews(before)
    if reviews is None:
        log.info("Sem nota/quantidade de avaliacoes de jogadores: %s", page_url)
        return None
    critic = int(critic_match.group(1))
    positive, count = reviews
    if not all(0 <= score <= 100 for score in (critic, positive)):
        return None

    # A página pode trazer outros links para Nintendo; exigir contexto da oferta.
    shop_url = ""
    for anchor in soup.select("a[href]"):
        if not re.search(r"Ver na eShop", anchor.get_text(" ", strip=True), re.I):
            continue
        candidate = anchor.get("href", "")
        parsed = urlparse(candidate)
        domain = (parsed.hostname or "").lower()
        if (parsed.scheme == "https" and
            (domain == "nintendo.com" or domain.endswith(".nintendo.com"))):
            shop_url = candidate
            break
    if not shop_url:
        log.warning("Link oficial Nintendo ausente: %s", page_url)
        return None
    return Offer(title, page_url, shop_url, price, old_price, discount,
                 critic, positive, count)


def qualifies(o: Offer, settings: dict) -> bool:
    return (o.price >= Decimal(str(settings.get("min_price_brl", 0)))
            and o.price <= Decimal(str(settings["max_price_brl"]))
            and o.discount >= settings["min_discount_percent"]
            and o.critic >= settings["min_critic_score"]
            and o.player_positive >= settings["min_player_positive_percent"]
            and o.player_reviews >= settings["min_player_reviews"])


def select_alerts(offers: list[Offer], state: dict, bootstrap: bool = True
                  ) -> tuple[list[Offer], dict]:
    """Alerta na entrada em promoção ou em queda adicional de preço.

    Não apaga o histórico inteiro por resultados parciais: o chamador só salva
    após executar a coleta completa. Chave é a URL canônica do jogo.
    """
    previous = state.get("active", {})
    first = not state.get("initialized", False)
    fresh: dict[str, dict] = {}
    alerts: list[Offer] = []
    for offer in offers:
        key = offer.page_url
        fresh[key] = offer.as_dict()
        old = previous.get(key)
        if ((not first or not bootstrap)
                and (old is None or offer.price < Decimal(str(old["price"])))):
            alerts.append(offer)
    alerts.sort(key=lambda o: (-o.discount, o.price, -o.critic))
    return alerts, {"initialized": True, "active": fresh}
