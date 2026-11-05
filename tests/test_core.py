from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo
import pytest
from radar.core import Offer, discovery, parse_detail, qualifies, select_alerts

URL = 'https://valeojogo.com.br/jogo/the-messenger/'
LISTING = '''<html><body><h1>Promoções de jogos de Nintendo Switch hoje</h1>
<p>25 jogos em promoção · preços de 04/11/2026 · conferidos todo dia</p>
<a href="/jogo/the-messenger/">The Messenger</a></body></html>'''
DETAIL = '''<html><body><div>87 Crítica 98%Steam 97 Vale o Jogo</div><h1>The Messenger</h1>
<div>Jogadores 98% positivas 1,4 mil análises</div><h2>Onde comprar</h2>
<div>Switch digital</div><div>Nintendo eShop</div><span>R$ 73,96</span> -80%
<span>R$ 14,79</span> <a href="https://www.nintendo.com/pt-br/store/products/example/">Ver na eShop</a>
<div>PC digital</div><div>Steam</div><span>R$ 10,00</span>
<h2>Histórico de preço</h2></body></html>'''
SETTINGS = {"max_price_brl": 100, "min_discount_percent": 30,
            "min_critic_score": 80, "min_player_positive_percent": 85,
            "min_player_reviews": 200}


def test_discovery():
    assert discovery(LISTING, 'https://valeojogo.com.br/promocoes/switch/',
                     now=datetime(2026, 11, 5, 19, tzinfo=ZoneInfo('America/Sao_Paulo'))) == [URL]


def test_discovery_stale():
    with pytest.raises(ValueError):
        discovery(LISTING, 'https://valeojogo.com.br/promocoes/switch/',
                  now=datetime(2026, 12, 5, tzinfo=ZoneInfo('America/Sao_Paulo')))


def test_parse_and_filter():
    deal = parse_detail(DETAIL, URL)
    assert deal is not None
    assert deal.price == Decimal('14.79')
    assert deal.discount == 80
    assert deal.player_reviews == 1400
    assert qualifies(deal, SETTINGS)
    assert not qualifies(deal, dict(SETTINGS, max_price_brl=10))


def test_reject_wrong_store():
    assert parse_detail(DETAIL.replace('www.nintendo.com', 'fake-shop.example'), URL) is None


def test_bootstrap_and_dedupe_and_drop():
    deal = parse_detail(DETAIL, URL)
    alerts, state = select_alerts([deal], {"initialized": False, "active": {}})
    assert not alerts
    assert not select_alerts([deal], state)[0]
    better = Offer(**{**deal.__dict__, "price": Decimal("9.99")})
    assert select_alerts([better], state)[0] == [better]
    # Uma oferta encerrada e retornando deve gerar novo aviso.
    _, gone = select_alerts([], state)
    assert select_alerts([deal], gone)[0] == [deal]


def test_eshop_discount_range_and_price_ceiling():
    base = parse_detail(DETAIL, URL)
    assert base is not None
    settings = dict(SETTINGS, max_discount_percent=90)

    # Sem preco minimo: ofertas abaixo de R$50 tambem sao validas.
    assert qualifies(base, settings)
    for price in ("0.01", "49.99", "50.00", "100.00"):
        candidate = Offer(**{**base.__dict__, "price": Decimal(price)})
        assert qualifies(candidate, settings)
    assert not qualifies(Offer(**{**base.__dict__, "price": Decimal("100.01")}), settings)
    assert not qualifies(Offer(**{**base.__dict__, "price": Decimal("0.00")}), settings)

    for discount in (30, 50, 90):
        candidate = Offer(**{**base.__dict__, "discount": discount})
        assert qualifies(candidate, settings)
    for discount in (29, 91):
        candidate = Offer(**{**base.__dict__, "discount": discount})
        assert not qualifies(candidate, settings)


def test_alert_order_prefers_largest_discount():
    base = parse_detail(DETAIL, URL)
    assert base is not None
    offers = [
        Offer(**{**base.__dict__, "page_url": URL + "30", "discount": 30}),
        Offer(**{**base.__dict__, "page_url": URL + "90", "discount": 90}),
        Offer(**{**base.__dict__, "page_url": URL + "50", "discount": 50}),
    ]
    alerts, _ = select_alerts(offers, {"initialized": True, "active": {}})
    assert [o.discount for o in alerts] == [90, 50, 30]


def test_image_extracted_only_from_allowlisted_cdn():
    detail = DETAIL.replace(
        "<h1>The Messenger</h1>",
        '<h1>The Messenger</h1><img src="https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/764790/header.jpg">'
    )
    deal = parse_detail(detail, URL)
    assert deal is not None
    assert deal.image_url.startswith("https://shared.fastly.steamstatic.com/")
    malicious = DETAIL.replace(
        "<h1>The Messenger</h1>",
        '<h1>The Messenger</h1><img src="https://tracker.example/img.png">'
    )
    other = parse_detail(malicious, URL)
    assert other is not None and not other.image_url


def test_email_html_with_cover_buttons_and_plain_text():
    from radar.email_template import format_email, format_test_email
    offer = parse_detail(DETAIL, URL)
    assert offer is not None
    offer = Offer(**{**offer.__dict__, "image_url":
                   "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/764790/header.jpg"})
    plain, rich = format_email([offer], 10, preview=True)
    assert "The Messenger" in plain
    assert "PRÉVIA" in plain
    assert 'alt="Capa de The Messenger"' in rich
    assert "Ver na Nintendo eShop" in rich
    assert "R$ 14,79" in rich
    assert "-80% OFF" in rich
    no_cover = Offer(**{**offer.__dict__, "image_url": ""})
    assert "Nintendo Switch</div>" in format_email([no_cover], 10)[1]
    test_plain, test_html = format_test_email()
    assert "não altera o histórico" in test_plain
    assert "<html" in test_html
