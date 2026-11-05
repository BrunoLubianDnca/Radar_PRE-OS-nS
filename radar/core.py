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
from .popular import is_popular

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
    image_url: str = ""

    def as_dict(self) -> dict:
        return {"title": self.title, "page_url": self.page_url,
                "shop_url": self.shop_url, "price": str(self.price),
                "old_price": str(self.old_price), "discount": self.discount,
                "critic": self.critic, "player_positive": self.player_positive,
                "player_reviews": self.player_reviews, "image_url": self.image_url}


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



def discover_listing_pages(html: str, base: str, max_pages: int) -> list[str]:
    """Segue somente links HTML explícitos de paginação da MESMA vitrine.

    Botões JavaScript sem href não são URLs verificadas e não são adivinhados.
    Consulta limitada pelo max_pages para evitar loops ou varredura agressiva.
    """
    from urllib.parse import parse_qs, urlencode, urlunparse
    if max_pages <= 1:
        return []
    base_url = urlparse(base)
    result: list[str] = []
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.select("a[href]"):
        target = urlparse(urljoin(base, a.get("href", "")))
        if (target.scheme != "https" or target.hostname != "valeojogo.com.br"
                or target.path.rstrip("/") != base_url.path.rstrip("/")):
            continue
        params = parse_qs(target.query, keep_blank_values=False)
        if set(params) != {"page"} or len(params["page"]) != 1:
            continue
        raw = params["page"][0]
        if not raw.isascii() or not raw.isdigit():
            continue
        page_number = int(raw)
        if not 2 <= page_number <= max_pages:
            continue
        candidate = urlunparse(("https", "valeojogo.com.br",
                                base_url.path, "", urlencode({"page": page_number}), ""))
        if candidate not in result:
            result.append(candidate)
    return sorted(result, key=lambda u: int(parse_qs(urlparse(u).query)["page"][0]))

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
    if deal:
        old_price, discount, price = (
            money(deal.group(1)), int(deal.group(2)), money(deal.group(3))
        )
    else:
        # Formato alternativo explícito: "-75% R$ 22,49 de R$ 89,99".
        # Não procurar números fora da entrada da eShop (risco de pegar PC/PS).
        alternative = re.search(
            r"[−–-]\s*(\d{1,3})\s*%\s*R\$\s*([\d.]+,\d{2})\s*"
            r"(?:de|antes|era)\s*R\$\s*([\d.]+,\d{2})",
            snippet[:160], re.I
        )
        if not alternative:
            log.warning("Preco/desconto eShop nao reconhecido: %s | %s",
                        page_url, snippet[:130])
            return None
        discount, price, old_price = (
            int(alternative.group(1)), money(alternative.group(2)),
            money(alternative.group(3))
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
    critic = int(critic_match.group(1))
    # Nintendo não publica uma contagem de análises equivalente à Steam.
    # Alguns títulos conhecidos não possuem esse indicador na fonte.
    # Zero significa "não disponível", nunca "0% de aprovação".
    positive, count = reviews if reviews is not None else (0, 0)
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
    # Preferir a capa/arte principal, nunca imagens aleatórias da página.
    # Aceitar apenas HTTPS em CDNs conhecidas de imagens de jogos.
    allowed_images = (
        "shared.fastly.steamstatic.com",
        "images.igdb.com",
        "cdn.cloudflare.steamstatic.com",
        "steamcdn-a.akamaihd.net",
    )
    image_url = ""
    candidates = []
    for meta in soup.select('meta[property="og:image"], meta[name="twitter:image"]'):
        candidates.append(meta.get("content", ""))
    for img in soup.select("img[src]")[:6]:
        candidates.append(img.get("src", ""))
    for raw_url in candidates:
        resolved = urljoin(page_url, raw_url)
        parts = urlparse(resolved)
        if (parts.scheme == "https" and parts.hostname in allowed_images):
            image_url = resolved
            break
    return Offer(title, page_url, shop_url, price, old_price, discount,
                 critic, positive, count, image_url=image_url)


def qualifies(o: Offer, settings: dict) -> bool:
    """Apenas franquias conhecidas, oferta digital verificável e boas notas.

    Avaliação de jogadores não é obrigatória quando a fonte não fornece
    amostra suficiente. Se houver amostra robusta, ela deve ser positiva.
    """
    if not (Decimal("0") < o.price <= Decimal(str(settings["max_price_brl"]))):
        return False
    if not (settings["min_discount_percent"] <= o.discount
            <= settings.get("max_discount_percent", 100)):
        return False
    if settings.get("popular_only", False) and not is_popular(o.title):
        return False
    if o.critic < settings["min_critic_score"]:
        return False
    # A nota de jogadores só restringe quando a fonte informa amostra
    # de pelo menos min_player_reviews análises.
    min_reviews = settings.get("min_player_reviews", 200)
    if o.player_reviews >= min_reviews:
        return o.player_positive >= settings["min_player_positive_percent"]
    return True


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
