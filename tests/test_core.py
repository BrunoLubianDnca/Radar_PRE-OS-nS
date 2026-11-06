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
    assert "Ver oferta na eShop" in rich
    assert "R$ 14,79" in rich
    assert "80% OFF" in rich
    no_cover = Offer(**{**offer.__dict__, "image_url": ""})
    assert "Nintendo<br>Switch" in format_email([no_cover], 10)[1]
    test_plain, test_html = format_test_email()
    assert "não altera o histórico" in test_plain
    assert "<html" in test_html


def test_popular_only_excludes_obscure_discounted_games():
    from radar.popular import is_popular
    source = parse_detail(DETAIL, URL)
    assert source is not None
    strict = dict(SETTINGS, popular_only=True, max_discount_percent=90)
    assert not qualifies(source, strict)  # The Messenger nao é mainstream
    assert not is_popular("Moonlighter")
    assert not is_popular("Children of Morta")
    assert not is_popular("Dicey Dungeons")
    for name in ("Terraria", "Sid Meier's Civilization VI",
                 "FINAL FANTASY XII THE ZODIAC AGE", "Mario Kart 8 Deluxe",
                 "The Legend of Zelda: Breath of the Wild", "Stardew Valley"):
        assert is_popular(name)
        candidate = Offer(**{**source.__dict__, "title": name})
        assert qualifies(candidate, strict)
    # Uma franquia famosa ainda precisa respeitar o preco e o desconto.
    assert not qualifies(Offer(**{**source.__dict__, "title": "Terraria",
                                 "price": Decimal("101.00")}), strict)
    assert not qualifies(Offer(**{**source.__dict__, "title": "Terraria",
                                 "discount": 20}), strict)


def test_famous_switch_games_without_steam_review_metrics():
    mainline = DETAIL.replace("The Messenger", "Mario Kart 8 Deluxe")
    mainline = mainline.replace("Jogadores 98% positivas 1,4 mil análises", "")
    offer = parse_detail(mainline, URL)
    assert offer is not None
    assert offer.player_reviews == 0
    assert offer.player_positive == 0
    assert qualifies(offer, dict(SETTINGS, popular_only=True))
    # Notas negativas com amostra de jogadores suficiente continuam bloqueadas.
    negative = Offer(**{**offer.__dict__,
                        "player_reviews": 2000, "player_positive": 40})
    assert not qualifies(negative, dict(SETTINGS, popular_only=True))


def test_pagination_only_follows_explicit_safe_links():
    from radar.core import discover_listing_pages
    base = "https://valeojogo.com.br/promocoes/switch/"
    sample = (
        '<a href="?page=2">2</a>'
        '<a href="/promocoes/switch/?page=3">3</a>'
        '<a href="https://evil.example/promocoes/switch/?page=2">evitar</a>'
        '<a href="/promocoes/pc/?page=2">plataforma errada</a>'
        '<a href="?page=999999">fora do limite</a>'
        '<a href="?page=-1">invalido</a>'
        '<button>4</button>'
    )
    assert discover_listing_pages(sample, base, 3) == [
        base + "?page=2", base + "?page=3"
    ]
    assert discover_listing_pages(sample, base, 1) == []
    assert discover_listing_pages('<button>2</button>', base, 3) == []


def test_popularity_ranking_is_explainable_not_sales_data():
    from radar.popular import popularity_evidence, rank_offers
    offer = parse_detail(DETAIL, URL)
    assert offer is not None
    popular = Offer(**{**offer.__dict__, "title": "Terraria",
                       "player_positive": 97, "player_reviews": 72600})
    missing = Offer(**{**offer.__dict__, "title": "Terraria",
                       "player_positive": 0, "player_reviews": 0})
    outside = Offer(**{**offer.__dict__, "title": "Example Unknown Game",
                       "player_reviews": 100})
    ranked = rank_offers([outside, missing, popular])
    assert ranked[0] == popular
    assert popularity_evidence(popular.title, popular.critic,
                               popular.player_positive, popular.player_reviews)[0] > (
                                   popularity_evidence(missing.title, missing.critic,
                                                       missing.player_positive, missing.player_reviews)[0])
    _, evidence = popularity_evidence(missing.title, missing.critic, 0, 0)
    assert "não informadas" in evidence
    assert "vendas" not in evidence.lower()


def test_unverifiable_eshop_purchase_is_not_fabricated():
    # Algumas fichas entregam somente um resumo (página carregada em JS).
    # Sem a seção e o link oficial, não há como provar o preço digital.
    skeleton = """<html><h1>Borderlands Collection</h1>
    <p>Crítica 84/100. Nintendo eShop (Switch) R$ 49,98 (-75%).</p>
    <p>Carregando o histórico de preço, as lojas e a comunidade...</p></html>"""
    assert parse_detail(skeleton, "https://valeojogo.com.br/jogo/borderlands/") is None


def test_explicit_alternate_price_order_still_verifies_discount_and_store():
    original = '<span>R$ 73,96</span> -80%\n<span>R$ 14,79</span>'
    assert original in DETAIL
    alternate = DETAIL.replace(
        original, '-80% <span>R$ 14,79</span> de <span>R$ 73,96</span>'
    )
    parsed = parse_detail(alternate, URL)
    assert parsed is not None
    assert parsed.price == Decimal("14.79")
    assert parsed.old_price == Decimal("73.96")
    assert parsed.discount == 80
    # Mesmo formato, mas desconto mentiroso: rejeitar em vez de alertar.
    assert parse_detail(alternate.replace("-80%", "-95%"), URL) is None
    # Link fora da Nintendo não é compra digital verificada.
    assert parse_detail(alternate.replace("www.nintendo.com", "fake.example"), URL) is None


def test_general_multiplatform_source_does_not_reduce_switch_coverage():
    from radar.main import ensure_primary_coverage
    # Execução real: 59 URLs ao todo, mas apenas 36 são das vitrines Switch.
    # Os 23 candidatos da vitrine geral não entram no denominador.
    assert ensure_primary_coverage(36, 17) is None
    # Ainda precisamos bloquear quando as fontes Switch param de funcionar.
    with pytest.raises(RuntimeError, match="Cobertura Switch insuficiente"):
        ensure_primary_coverage(36, 4)
    assert ensure_primary_coverage(9, 1) is None


def test_nintendo_priority_curated_and_partner_excluded():
    from radar.nintendo import is_nintendo_priority
    for title in (
        "Super Mario Bros. Wonder", "Mario Kart 8 Deluxe",
        "Donkey Kong Country: Tropical Freeze",
        "The Legend of Zelda: Tears of the Kingdom",
        "Kirby and the Forgotten Land", "Metroid Dread",
        "Animal Crossing: New Horizons", "Luigi's Mansion 3",
        "Pokémon Legends: Arceus", "Pikmin 4",
    ):
        assert is_nintendo_priority(title), title
    for title in (
        "Mario + Rabbids Sparks of Hope",
        "Mario & Sonic at the Olympic Games",
        "Pokémon UNITE",
        "The Legend of Zelda: Breath of the Wild Nintendo Switch 2 Edition",
        "The Messenger", "Risk of Rain 2",
    ):
        assert not is_nintendo_priority(title), title


def test_nintendo_own_price_and_discount_rules_do_not_change_normal_games():
    from radar.nintendo import is_nintendo_priority
    base = parse_detail(DETAIL, URL)
    assert base is not None
    cfg = dict(SETTINGS, popular_only=True, max_discount_percent=90,
               nintendo_priority_enabled=True,
               nintendo_max_price_brl=250, nintendo_min_discount_percent=15)
    mario = Offer(**{**base.__dict__, "title": "Super Mario Bros. Wonder",
                    "price": Decimal("199.90"), "old_price": Decimal("249.90"),
                    "discount": 20})
    assert is_nintendo_priority(mario.title)
    assert qualifies(mario, cfg)
    assert not qualifies(mario, dict(cfg, nintendo_priority_enabled=False))
    assert not qualifies(Offer(**{**mario.__dict__, "price": Decimal("250.01")}), cfg)
    assert not qualifies(Offer(**{**mario.__dict__, "discount": 14}), cfg)
    # Mario + Rabbids é uma série associada, não ganha os limites especiais.
    rabbids = Offer(**{**mario.__dict__, "title": "Mario + Rabbids Sparks of Hope"})
    assert not qualifies(rabbids, cfg)
    # Terceiros seguem 30% e teto de 100 reais.
    third_party = Offer(**{**mario.__dict__, "title": "Terraria"})
    assert not qualifies(third_party, cfg)


def test_nintendo_first_in_email_and_presentation():
    from radar.main import prioritize_email_offers
    from radar.email_template import format_email
    base = parse_detail(DETAIL, URL)
    assert base is not None
    mario = Offer(**{**base.__dict__, "title": "Super Mario Bros. Wonder",
                     "discount": 20, "price": Decimal("199.90")})
    terraria = Offer(**{**base.__dict__, "title": "Terraria", "discount": 80})
    assert prioritize_email_offers([terraria, mario])[0].title == mario.title
    plain, rich = format_email([mario], 10)
    assert "NINTENDO EM DESTAQUE" in rich
    assert "Super Mario Bros. Wonder" in plain
    assert "Ver oferta na eShop" in rich
    assert "NINTENDO EM DESTAQUE" not in format_email([terraria], 10)[1]


def test_no_link_outside_eshop_offer_or_across_other_platforms():
    # Um preço Nintendo seguido de uma seção de PC sem seu CTA não é
    # suficiente para vincular o preço a outro botão eShop da página.
    original_link = ('<a href="https://www.nintendo.com/pt-br/store/products/example/">'
                     'Ver na eShop</a>')
    assert original_link in DETAIL
    without_cta = DETAIL.replace(original_link, "")
    assert parse_detail(without_cta, URL) is None
    misplaced = without_cta.replace(
        "<div>PC digital</div>",
        '<div>PC digital</div>' + original_link)
    assert parse_detail(misplaced, URL) is None


def test_email_keeps_nintendo_priority_in_visual_order():
    from radar.main import prioritize_email_offers
    from radar.email_template import format_email
    base = parse_detail(DETAIL, URL)
    assert base is not None
    mario = Offer(**{**base.__dict__, "title": "Super Mario Bros. Wonder",
                     "discount": 20, "price": Decimal("199.90")})
    ordinary = Offer(**{**base.__dict__, "title": "Terraria",
                        "discount": 80, "price": Decimal("22.49")})
    ordered = prioritize_email_offers([ordinary, mario])
    assert [x.title for x in ordered] == [mario.title, ordinary.title]
    plain, html = format_email(ordered, 12)
    assert html.index(mario.title) < html.index(ordinary.title)
    assert plain.index(mario.title) < plain.index(ordinary.title)


def test_critical_and_optional_sources_are_distinct():
    from radar.main import is_optional_source
    assert is_optional_source("https://valeojogo.com.br/promocoes/nintendo/")
    assert is_optional_source("https://valeojogo.com.br/promocoes/bem-avaliados/")
    assert not is_optional_source("https://valeojogo.com.br/promocoes/switch/")
    assert not is_optional_source("https://valeojogo.com.br/promocoes/jogos-baratos-switch/")


def test_nintendo_watchlist_diagnostics_no_guessed_links():
    from radar.nintendo_watch import (
        WATCHED_GAMES, matched_watch_game, create_watch_report,
        register_candidate, register_result, watch_counts,
    )
    from radar.main import write_watch_summary
    assert len(WATCHED_GAMES) >= 25
    assert matched_watch_game("Super Mario Bros.™ Wonder") == "Super Mario Bros. Wonder"
    assert matched_watch_game("Super Mario Bros. Wonder Nintendo Switch 2 Edition") is None
    assert matched_watch_game("Mario + Rabbids Sparks of Hope") is None
    report = create_watch_report()
    url = "https://valeojogo.com.br/jogo/mario-kart-8-deluxe/"
    register_candidate(report, "Mario Kart 8 Deluxe", url)
    register_result(report, "Mario Kart 8 Deluxe", url, parsed=True, eligible=False)
    counts = watch_counts(report)
    assert counts["encontrados"] == 1
    assert counts["elegiveis"] == 0
    assert counts["nao_encontrados"] == len(WATCHED_GAMES) - 1
    assert "fora dos critérios" in write_watch_summary(report)
    assert "não apareceu nas vitrines" in write_watch_summary(report)


def test_official_nintendo_html_sale_requires_same_product_prices_and_switch():
    from radar.official_sales import parse_official_sales, is_official_product_url
    url = "https://www.nintendo.com/pt-br/store/products/super-mario-bros-wonder-switch/"
    sample = """<html><body><article>
       <a href="/pt-br/store/products/super-mario-bros-wonder-switch/">Super Mario Bros. Wonder</a>
       <div>Nintendo Switch</div>
       <span>Preço promocional: R$ 199,90</span>
       <span>Preço normal: R$ 329,90</span>
       </article></body></html>"""
    result = parse_official_sales(sample)
    assert len(result) == 1
    assert result[0].watched_title == "Super Mario Bros. Wonder"
    assert result[0].price == Decimal("199.90")
    assert result[0].old_price == Decimal("329.90")
    assert result[0].product_url == url
    assert result[0].discount == 39
    assert is_official_product_url(url)
    assert not is_official_product_url("https://fake.nintendo.com/pt-br/store/products/super-mario-bros-wonder-switch/")
    assert parse_official_sales(sample.replace("Nintendo Switch</div>", "Nintendo Switch 2</div>")) == []
    assert parse_official_sales(sample.replace("R$ 199,90", "R$ 339,90")) == []
    assert parse_official_sales(sample.replace('href="/pt-br/store/products/', 'href="https://malicious.example/pt-br/store/products/')) == []


def test_official_nintendo_sale_never_invents_critic_score():
    from radar.official_sales import parse_official_sales
    from radar.email_template import format_email
    sample = """<article><a href="/pt-br/store/products/metroid-dread-switch/">
    Metroid Dread</a><div>Nintendo Switch</div>
    <p>Preço promocional: R$ 199,90</p>
    <p>Preço normal: R$ 329,90</p></article>"""
    found = parse_official_sales(sample)
    assert len(found) == 1
    sale = found[0]
    offer = Offer(
        title=sale.watched_title, page_url=sale.product_url,
        shop_url=sale.product_url, price=sale.price, old_price=sale.old_price,
        discount=sale.discount, critic=0, player_positive=0, player_reviews=0
    )
    config = dict(SETTINGS, popular_only=True, max_discount_percent=90,
                  nintendo_priority_enabled=True,
                  nintendo_max_price_brl=250, nintendo_min_discount_percent=15)
    assert qualifies(offer, config)
    assert not qualifies(offer, dict(config, nintendo_priority_enabled=False))
    plain, rich = format_email([offer], 12)
    assert "Crítica não disponível" in rich
    assert "Crítica: não disponível" in plain
    assert "0/100" not in rich
    assert "Ver oferta na eShop" in rich


def test_official_sale_rejects_mixed_card_prices():
    from radar.official_sales import parse_official_sales
    sample = """<html><body><div>
      <article><a href="/pt-br/store/products/mario-kart-8-deluxe-switch/">
      Mario Kart 8 Deluxe</a><p>Nintendo Switch</p></article>
      <article><a href="/pt-br/store/products/metroid-dread-switch/">
      Metroid Dread</a><p>Nintendo Switch</p>
      <p>Preço promocional: R$ 49,90</p><p>Preço normal: R$ 329,90</p></article>
    </div></body></html>"""
    found = parse_official_sales(sample)
    assert len(found) == 1
    assert found[0].watched_title == "Metroid Dread"



def test_nintendo_catalog_matches_each_game_exactly_with_official_link():
    from radar.nintendo_catalog import parse_catalog_results
    data = {"results": [{"hits": [
        {"title": "Super Mario Bros. Wonder",
         "nsuid": "70010000068688",
         "url": "/pt-br/store/products/super-mario-bros-wonder-switch/"},
        {"title": "Super Mario Bros. Wonder Nintendo Switch 2 Edition",
         "nsuid": "70010000068689",
         "url": "/pt-br/store/products/super-mario-bros-wonder-switch/"},
        {"title": "Metroid Dread", "nsuid": "70010000012345",
         "url": "https://untrusted.example/pt-br/store/products/metroid-dread-switch/"},
    ]}]}
    found, ambiguous = parse_catalog_results(data)
    assert ambiguous == 0
    assert list(found) == ["Super Mario Bros. Wonder"]
    assert found["Super Mario Bros. Wonder"].nsuid == "70010000068688"
    assert found["Super Mario Bros. Wonder"].shop_url.startswith("https://www.nintendo.com/")
    assert parse_catalog_results({"results": [{"hits": []}]}) == ({}, 0)
    with pytest.raises(ValueError):
        parse_catalog_results({"results": "invalid"})


def test_nintendo_catalog_rejects_conflicting_nsuids():
    from radar.nintendo_catalog import parse_catalog_results
    data = {"results": [{"hits": [
        {"title": "Mario Kart 8 Deluxe", "nsuid": "70010000011111",
         "url": "/pt-br/store/products/mario-kart-8-deluxe-switch/"},
        {"title": "Mario Kart 8 Deluxe", "nsuid": "70010000022222",
         "url": "/pt-br/store/products/mario-kart-8-deluxe-switch/"},
    ]}]}
    found, ambiguous = parse_catalog_results(data)
    assert not found
    assert ambiguous == 1


def test_nintendo_prices_eshop_brl_discount_freshness():
    from radar.nintendo_catalog import CatalogProduct, parse_regional_prices
    from datetime import timezone
    product = CatalogProduct(
        "Metroid Dread", "70010000012345",
        "https://www.nintendo.com/pt-br/store/products/metroid-dread-switch/"
    )
    values = {"Metroid Dread": product}
    row = {
        "title_id": 70010000012345,
        "regular_price": {"amount": "329.90", "currency": "BRL"},
        "discount_price": {"amount": "199.90", "currency": "BRL",
                           "start_datetime": "2026-11-01T00:00:00Z",
                           "end_datetime": "2026-11-15T23:59:59Z"},
    }
    now = datetime(2026, 11, 6, tzinfo=timezone.utc)
    matches = parse_regional_prices({"country": "BR", "prices": [row]}, values, now)
    assert len(matches) == 1 and matches[0].discount == 39
    assert matches[0].current == Decimal("199.90")
    assert parse_regional_prices({"country": "BR", "prices": [row]}, values,
                                 datetime(2026, 11, 16, tzinfo=timezone.utc)) == []
    assert parse_regional_prices({"country": "BR", "prices": [{
        **row, "discount_price": {"amount": "199.90", "currency": "USD"}}]},
        values, now) == []
    assert parse_regional_prices({"country": "BR", "prices": [{
        **row, "discount_price": None}]}, values, now) == []
    with pytest.raises(ValueError):
        parse_regional_prices({"country": "US", "prices": [row]}, values, now)


def test_nintendo_catalog_calls_are_batched_and_region_is_br():
    from radar.nintendo_catalog import fetch_catalog, fetch_regional_prices, CatalogProduct
    class MockResponse:
        def __init__(self, url, payload):
            self.url = url
            self.payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self.payload
    class MockSession:
        def __init__(self):
            self.posts = []
            self.gets = []
        def post(self, url, **kw):
            self.posts.append((url, kw))
            return MockResponse(url, {"results": [{"hits": []} for _ in range(3)]})
        def get(self, url, **kw):
            self.gets.append((url, kw))
            return MockResponse(url + "?country=BR", {"country": "BR", "prices": []})
    session = MockSession()
    products, ambiguous = fetch_catalog(
        session, ("Super Mario Bros. Wonder", "Metroid Dread", "Mario Kart 8 Deluxe"))
    assert products == {} and ambiguous == 0
    assert len(session.posts) == 1
    assert len(session.posts[0][1]["json"]["requests"]) == 3
    assert all(r["indexName"] == "ncom_game_pt_br"
               for r in session.posts[0][1]["json"]["requests"])
    chosen = {"Metroid Dread": CatalogProduct(
        "Metroid Dread", "70010000012345",
        "https://www.nintendo.com/pt-br/store/products/metroid-dread-switch/")}
    assert fetch_regional_prices(session, chosen) == []
    assert session.gets[0][1]["params"]["country"] == "BR"
    assert session.gets[0][1]["params"]["ids"] == "70010000012345"


def test_nintendo_catalog_failure_never_fabricates_price():
    from radar.nintendo_catalog import fetch_catalog, parse_regional_prices
    import requests
    class FailedSession:
        def post(self, *args, **kwargs):
            raise requests.ConnectionError("catalog unavailable")
    with pytest.raises(requests.ConnectionError):
        fetch_catalog(FailedSession(), ("Metroid Dread",))
    with pytest.raises(ValueError):
        parse_regional_prices({"country": "BR", "prices": "not-list"}, {})



def test_watch_report_differentiates_catalog_match_and_actual_sale():
    from radar.nintendo_watch import (
        create_watch_report, register_catalog_match, register_result, watch_counts,
    )
    from radar.main import write_watch_summary
    report = create_watch_report()
    title = "Super Mario Bros. Wonder"
    official = "https://www.nintendo.com/pt-br/store/products/super-mario-bros-wonder-switch/"
    register_catalog_match(report, title, official)
    assert watch_counts(report)["encontrados"] == 1
    assert watch_counts(report)["elegiveis"] == 0
    assert "desconto não confirmado" in write_watch_summary(report)
    register_result(report, title, official, parsed=True, eligible=True)
    assert watch_counts(report)["elegiveis"] == 1
    assert "oferta elegível" in write_watch_summary(report)



def test_catalog_accepts_nintendo_sourced_unlocalized_store_path_only():
    from radar.nintendo_catalog import parse_catalog_results
    payload = {"results": [{"hits": [{
        "title": "Donkey Kong Country: Tropical Freeze",
        "nsuid": "70010000012345",
        "url": "/store/products/donkey-kong-country-tropical-freeze-switch/",
    }]}]}
    entries, ambiguous = parse_catalog_results(payload)
    assert ambiguous == 0
    assert entries["Donkey Kong Country: Tropical Freeze"].shop_url == (
        "https://www.nintendo.com/pt-br/store/products/"
        "donkey-kong-country-tropical-freeze-switch/"
    )
