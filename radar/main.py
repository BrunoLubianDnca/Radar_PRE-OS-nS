"""Entry point: python -m radar.main"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import smtplib
import sys
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .core import BR, Offer, discovery, discover_listing_pages, parse_detail, qualifies, select_alerts
from .popular import popularity_evidence, rank_offers
from .nintendo import is_nintendo_priority
from .official_sales import parse_official_sales
from .nintendo_catalog import fetch_catalog, fetch_store_deals, fetch_regional_prices
from .nintendo_watch import (create_watch_report, register_candidate,
                             register_catalog_match, register_result, watch_counts)
from .email_template import format_email, format_test_email

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"User-Agent": "RadarSwitchMVP/1.0 (personal-deal-checker; +https://github.com)",
           "Accept-Language": "pt-BR,pt;q=0.9"}
LOG = logging.getLogger("radar-switch")


def fetch(session: requests.Session, url: str) -> str:
    r = session.get(url, headers=HEADERS, timeout=(10, 25), allow_redirects=True)
    r.raise_for_status()
    if urlparse(r.url).hostname != "valeojogo.com.br":
        raise RuntimeError("Redirecionamento inesperado para outro domínio")
    if len(r.content) < 500:
        raise RuntimeError("Resposta HTML incompleta")
    return r.text


def fetch_nintendo_sales(session: requests.Session) -> str:
    """Consulta opcional de ofertas oficiais; falhar não interrompe o Radar."""
    url = "https://www.nintendo.com/pt-br/store/sales-and-deals/"
    response = session.get(url, headers=HEADERS, timeout=(8, 18), allow_redirects=True)
    response.raise_for_status()
    final = urlparse(response.url)
    if final.scheme != "https" or final.hostname != "www.nintendo.com":
        raise RuntimeError("Redirecionamento inesperado na loja Nintendo")
    if len(response.content) < 500:
        raise RuntimeError("HTML incompleto na loja Nintendo")
    return response.text


def money_brl(value) -> str:
    return "R$ " + f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def write_delivery_summary(*, mode: str, status: str, count: int, reason: str) -> None:
    """Explica no Summary por que o e-mail foi enviado ou não."""
    destination = os.getenv("GITHUB_STEP_SUMMARY")
    if not destination:
        return
    with open(destination, "a", encoding="utf-8") as file:
        file.write(
            "\n## Entrega do Radar\n\n"
            f"- Modo: **{mode}**\n"
            f"- Situação: **{status}**\n"
            f"- Ofertas no e-mail: **{count}**\n"
            f"- Detalhe: {reason}\n"
        )


def email_alert(offers: list[Offer], max_items: int, *, test_email: bool = False, preview: bool = False) -> None:
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("Secrets ausentes: " + ", ".join(missing))
    msg = EmailMessage()
    msg["From"] = os.getenv("EMAIL_FROM") or os.environ["SMTP_USER"]
    msg["To"] = os.environ["EMAIL_TO"]
    msg["Subject"] = ("[Radar Switch] Teste de e-mail — configuração OK" if test_email
                      else (f"[Radar Switch] PRÉVIA — {len(offers)} ofertas encontradas" if preview
                            else f"[Radar Switch] {len(offers)} promoção(ões) nova(s) na eShop"))
    plain, rich = format_test_email() if test_email else format_email(offers, max_items, preview=preview)
    msg.set_content(plain)
    msg.add_alternative(rich, subtype="html")
    host, port = os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
    elif port == 587:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
    else:
        raise ValueError("SMTP_PORT deve ser 465 (SSL) ou 587 (STARTTLS)")


def ensure_primary_coverage(primary_count: int, primary_parsed: int) -> None:
    """Protege a coleta Switch sem contar páginas de outras plataformas.

    A vitrine geral de jogos bem avaliados é complementar: suas páginas de
    PC/Xbox/PS não são falhas do parser da Nintendo eShop.
    """
    if primary_count >= 10 and primary_parsed < primary_count // 3:
        raise RuntimeError(
            f"Cobertura Switch insuficiente ({primary_parsed}/{primary_count}); "
            "histórico preservado"
        )


def is_optional_source(source: str) -> bool:
    """Vitrines amplas adicionam oportunidades, sem bloquear o radar Switch."""
    return urlparse(source).path.rstrip("/") in (
        "/promocoes/bem-avaliados", "/promocoes/nintendo"
    )


def prioritize_email_offers(offers: list[Offer]) -> list[Offer]:
    """Primeiro a curadoria Nintendo, depois relevância dos demais jogos."""
    first_party = [o for o in offers if is_nintendo_priority(o.title)]
    others = [o for o in offers if not is_nintendo_priority(o.title)]
    return rank_offers(first_party) + rank_offers(others)


def write_watch_summary(report: dict, output_path: str | None = None) -> str:
    """Diagnóstico de cada jogo Nintendo; nenhuma oferta é inventada."""
    counts = watch_counts(report)
    lines = [
        "## Acompanhamento Nintendo",
        "",
        f"**{counts['acompanhados']} títulos cadastrados** | "
        f"{counts['encontrados']} encontrados nas vitrines | "
        f"{counts['elegiveis']} ofertas elegíveis",
        "",
        "| Jogo | Situação |",
        "|---|---|",
    ]
    for entry in report.values():
        lines.append(f"| {entry.name} | {entry.status} |")
    summary = "\n".join(lines) + "\n"
    if output_path:
        with open(output_path, "a", encoding="utf-8") as summary_file:
            summary_file.write(summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Sem SMTP e sem salvar estado")
    parser.add_argument("--send-initial", action="store_true", help="Enviar ofertas da primeira execução")
    parser.add_argument("--test-email", action="store_true", help="Envia apenas um e-mail de teste, sem consulta ou mudanças no histórico")
    parser.add_argument("--preview-email", action="store_true", help="Envia prévia das ofertas atuais sem salvar histórico")
    args = parser.parse_args(argv)
    if args.test_email:
        email_alert([], 0, test_email=True)
        LOG.info("E-mail de teste aceito pelo SMTP; nenhuma coleta e nenhum estado alterado")
        write_delivery_summary(mode="Teste SMTP", status="aceito pelo servidor SMTP", count=0,
                               reason="Confira o recebimento no destinatário configurado; SMTP não confirma a caixa de entrada.")
        return 0
    settings = json.loads((ROOT / "config/settings.json").read_text(encoding="utf-8"))
    state_file = ROOT / "data/state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    session = requests.Session()
    # A página oficial é sempre a PRIMEIRA fonte consultada, inclusive em
    # prévias. O HTML é reutilizado abaixo sem uma segunda requisição.
    official_html = None
    try:
        LOG.info("Fonte oficial prioritária: https://www.nintendo.com/pt-br/store/sales-and-deals/")
        official_html = fetch_nintendo_sales(session)
        LOG.info("Página oficial Nintendo consultada com sucesso (%d caracteres)",
                 len(official_html))
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        LOG.warning("Página oficial Nintendo indisponível: %s. Fontes alternativas preservadas.", exc)
    sources = settings.get("source_urls") or [settings["source_url"]]
    urls = []
    max_pages = max(1, min(int(settings.get("max_listing_pages", 1)), 5))
    primary_urls: set[str] = set()
    watch_report = create_watch_report()
    for source in sources:
        # Páginas subsequentes só são visitadas se aparecerem como links href
        # no HTML. Botões que dependem de JS não autorizam chutar URLs.
        pending = [source]
        visited: set[str] = set()
        while pending and len(visited) < max_pages:
            page_url = pending.pop(0)
            if page_url in visited:
                continue
            if visited:
                time.sleep(float(settings["request_delay_seconds"]))
            try:
                html_listing = fetch(session, page_url)
                discovered = discovery(html_listing, page_url, int(settings["max_source_age_hours"]))
            except (requests.RequestException, RuntimeError, ValueError) as exc:
                if not is_optional_source(source):
                    raise
                LOG.warning("Fonte complementar indisponível %s: %s. Coleta Switch preservada.", page_url, exc)
                break
            visited.add(page_url)
            LOG.info("Vitrine %s: %d candidatos", page_url, len(discovered))
            for anchor in BeautifulSoup(html_listing, "html.parser").select("a[href]"):
                from urllib.parse import urljoin
                possible = urljoin(page_url, anchor.get("href", ""))
                if possible in discovered:
                    register_candidate(watch_report, anchor.get_text(" ", strip=True), possible)
            for url in discovered:
                if url not in urls:
                    urls.append(url)
            for linked in discover_listing_pages(html_listing, source, max_pages):
                if linked not in visited and linked not in pending:
                    pending.append(linked)
        if "/promocoes/switch/" in source or "/jogos-baratos-switch/" in source:
            primary_urls.update(urls)
        LOG.info("Cobertura %s: %d pagina(s) HTML verificadas", source, len(visited))
    LOG.info("Candidatos únicos nas vitrines: %d", len(urls))
    offers: list[Offer] = []
    failed = 0
    parsed_count = 0
    primary_parsed = 0
    discarded_count = 0
    for i, url in enumerate(urls, 1):
        LOG.info("Analisando %d/%d: %s", i, len(urls), url)
        if i > 1:
            time.sleep(float(settings["request_delay_seconds"]))
        try:
            game_html = fetch(session, url)
            offer = parse_detail(game_html, url)
            if offer is None:
                title_node = BeautifulSoup(game_html, "html.parser").find("h1")
                if title_node:
                    register_result(watch_report, title_node.get_text(" ", strip=True), url,
                                    parsed=False)
                discarded_count += 1
                continue
            parsed_count += 1
            eligible = qualifies(offer, settings)
            register_result(watch_report, offer.title, url, parsed=True, eligible=eligible)
            if url in primary_urls:
                primary_parsed += 1
            if eligible:
                offers.append(offer)
                relevance, evidence = popularity_evidence(offer.title, offer.critic, offer.player_positive, offer.player_reviews)
                LOG.info("Elegível%s: %s | %s | -%d%% | relevância editorial %d/100 (%s)", " Nintendo" if is_nintendo_priority(offer.title) else "", offer.title, money_brl(offer.price), offer.discount, relevance, evidence)
            else:
                LOG.info("Fora dos filtros: %s | %s | -%d%% | Crítica %d | Jogadores %d%% (%d)", offer.title, money_brl(offer.price), offer.discount, offer.critic, offer.player_positive, offer.player_reviews)
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            failed += 1
            LOG.warning("Falha na página %s: %s", url, exc)
    watch_stats = watch_counts(watch_report)
    LOG.info("Nintendo acompanhado: cadastrados=%d, vistos=%d, elegíveis=%d, não encontrados=%d, sem oferta verificável=%d, fora dos critérios=%d",
             watch_stats["acompanhados"], watch_stats["encontrados"],
             watch_stats["elegiveis"], watch_stats["nao_encontrados"],
             watch_stats["sem_oferta_verificavel"], watch_stats["fora_criterios"])
    for entry in watch_report.values():
        if entry.page_url:
            LOG.info("Nintendo acompanhado: %s => %s", entry.name, entry.status)
    # Consulta independente ao catálogo oficial de ofertas. Só aproveita
    # cartões com título, versão Switch e dois preços dentro do mesmo bloco.
    # Se o site entregar apenas o shell JS, fica sem resultados e sem inventar.
    try:
        official_sales = parse_official_sales(official_html) if official_html else []
        LOG.info("Ofertas oficiais Nintendo verificadas em HTML: %d", len(official_sales))
        for sale in official_sales:
            offer = Offer(
                title=sale.watched_title, page_url=sale.product_url,
                shop_url=sale.product_url, price=sale.price,
                old_price=sale.old_price, discount=sale.discount,
                critic=0, player_positive=0, player_reviews=0
            )
            approved = qualifies(offer, settings)
            register_result(watch_report, offer.title, offer.page_url,
                            parsed=True, eligible=approved)
            if approved:
                # Não duplicar se a mesma URL oficial já estiver em ofertas.
                if not any(o.shop_url == offer.shop_url for o in offers):
                    offers.append(offer)
                LOG.info("Nintendo oficial elegível: %s | %s | -%d%%",
                         offer.title, money_brl(offer.price), offer.discount)
            else:
                LOG.info("Nintendo oficial fora dos critérios: %s | %s | -%d%%",
                         offer.title, money_brl(offer.price), offer.discount)
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        LOG.warning("Catálogo oficial Nintendo indisponível: %s. Continuando com vitrines.", exc)

    # Busca nominal (31 consultas em uma chamada Algolia) + preço direto
    # pela API regional da Nintendo. Não depende dos 28 cards das vitrines.
    try:
        catalog, ambiguous = fetch_catalog(session)
        LOG.info("Nintendo catálogo BR: %d títulos resolvidos; %d ambíguos",
                 len(catalog), ambiguous)
        for title, product in catalog.items():
            register_catalog_match(watch_report, title, product.shop_url)
        price_offers = fetch_regional_prices(session, catalog)
        LOG.info("Nintendo preços BR: %d ofertas com desconto verificado",
                 len(price_offers))
        for value in price_offers:
            product = value.product
            offer = Offer(
                title=product.title, page_url=product.shop_url,
                shop_url=product.shop_url, price=value.current,
                old_price=value.regular, discount=value.discount,
                critic=0, player_positive=0, player_reviews=0,
            )
            eligible = qualifies(offer, settings)
            register_result(watch_report, offer.title, offer.page_url,
                            parsed=True, eligible=eligible)
            if eligible:
                if not any(item.shop_url == offer.shop_url for item in offers):
                    offers.append(offer)
                LOG.info("Nintendo preço oficial BR elegível: %s | %s | -%d%%",
                         offer.title, money_brl(offer.price), offer.discount)
            else:
                LOG.info("Nintendo preço oficial BR fora dos critérios: %s | %s | -%d%%",
                         offer.title, money_brl(offer.price), offer.discount)
    except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
        LOG.warning("Busca nominal/preço Nintendo BR indisponível: %s. Ofertas comuns preservadas.", exc)

    # Buscar jogos da seleção "Todas as ofertas" da Nintendo Brasil
    # pelo índice utilizado pelo catálogo da loja. Só confirma promoções
    # após cruzar cada NSUID com o endpoint regional de preços BR.
    try:
        deal_catalog, deal_stats = fetch_store_deals(session)
        LOG.info("Nintendo vitrine oficial Deals: páginas=%d resultados=%d jogos acompanhados=%d",
                 deal_stats["pages"], deal_stats["hits"], deal_stats["matches"])
        if not deal_catalog:
            LOG.warning("Nintendo Deals sem correspondência: campos disponíveis no índice=%s",
                        ", ".join(deal_stats["fields"]))
        for name, product in deal_catalog.items():
            if name in watch_report and watch_report[name].status != "oferta elegível":
                register_catalog_match(watch_report, name, product.shop_url)
        verified_deals = fetch_regional_prices(session, deal_catalog)
        LOG.info("Nintendo vitrine Deals: %d promoções BRL confirmadas", len(verified_deals))
        for value in verified_deals:
            product = value.product
            offer = Offer(
                title=product.title, page_url=product.shop_url,
                shop_url=product.shop_url, price=value.current,
                old_price=value.regular, discount=value.discount,
                critic=0, player_positive=0, player_reviews=0
            )
            approved = qualifies(offer, settings)
            register_result(watch_report, offer.title, offer.page_url,
                            parsed=True, eligible=approved)
            if approved and not any(o.shop_url == offer.shop_url for o in offers):
                offers.append(offer)
                LOG.info("Nintendo Deals elegível: %s | %s | -%d%%",
                         offer.title, money_brl(offer.price), offer.discount)
    except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
        LOG.warning("Nintendo vitrine Deals: erro na API %s; fontes auxiliares preservadas.", exc)

    # Atualizar contagem incluindo a checagem oficial.
    watch_stats = watch_counts(watch_report)
    LOG.info("Nintendo verificação final: acompanhados=%d encontrados=%d elegíveis=%d",
             watch_stats["acompanhados"], watch_stats["encontrados"], watch_stats["elegiveis"])
    # O resumo deve refletir os dados das duas fontes.
    write_watch_summary(watch_report, os.getenv("GITHUB_STEP_SUMMARY"))

    # Não grave o estado se parte da vitrine estiver indisponível: evita falsos
    # avisos de 'promoção nova' quando a página se recuperar.
    LOG.info("Resumo: candidatos=%d, interpretados=%d, sem dados=%d, elegíveis=%d, erros HTTP=%d", len(urls), parsed_count, discarded_count, len(offers), failed)
    if failed:
        raise RuntimeError(f"Falharam {failed}/{len(urls)} páginas. Estado preservado.")
    if parsed_count == 0:
        raise RuntimeError("Nenhuma oferta digital reconhecida: verificar estrutura do site; estado preservado")
    if not offers:
        LOG.info("Nenhum jogo atingiu todos os filtros. Histórico preservado, sem e-mail.")
        write_delivery_summary(mode="Automático/Prévia", status="não enviado", count=0,
                               reason="Nenhuma oferta elegível foi encontrada.")
        return 0
    LOG.info("Cobertura Switch: %d/%d | fontes complementares: %d candidatos extras",
             primary_parsed, len(primary_urls), len(urls) - len(primary_urls))
    ensure_primary_coverage(len(primary_urls), primary_parsed)
    if args.preview_email:
        # Escolhe primeiro as ofertas mais relevantes; o template preserva a
        # apresentação visual e ordena por desconto dentro dessa seleção.
        selected = prioritize_email_offers(offers)[:int(settings["max_games_per_email"])]
        email_alert(selected, int(settings["max_games_per_email"]), preview=True)
        LOG.info("Prévia de ofertas enviada, histórico não alterado")
        write_delivery_summary(mode="Prévia", status="aceito pelo servidor SMTP", count=len(selected),
                               reason="Repete ofertas atuais, mesmo quando não são novas. Histórico preservado.")
        return 0
    alerts, new_state = select_alerts(offers, state, bootstrap=not args.send_initial)
    LOG.info("Elegíveis: %d | Alertas: %d", len(offers), len(alerts))
    if args.dry_run:
        for offer in alerts:
            print(f"{offer.title} | {money_brl(offer.price)} | -{offer.discount}% | {offer.shop_url}")
        print("DRY RUN: nenhum e-mail enviado; estado não modificado")
        return 0
    if alerts:
        selected = prioritize_email_offers(alerts)[:int(settings["max_games_per_email"])]
        email_alert(selected, int(settings["max_games_per_email"]))
        LOG.info("E-mail aceito pelo SMTP")
        write_delivery_summary(mode="Automático", status="aceito pelo servidor SMTP", count=len(selected),
                               reason="Novas promoções ou quedas adicionais de preço. Entrega final depende do provedor.")
    if not alerts:
        LOG.info("Nenhuma promoção nova ou redução adicional de preço: nenhum e-mail gerado.")
        write_delivery_summary(mode="Automático", status="não enviado", count=0,
                               reason="Ofertas já conhecidas, sem queda adicional de preço.")
    # Só atualiza depois do SMTP concluir, permitindo tentativa posterior se falhar.
    state_file.write_text(json.dumps(new_state, ensure_ascii=False, indent=2, sort_keys=True)
                          + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        sys.exit(main())
    except Exception as e:
        LOG.exception("Monitoramento falhou, estado não atualizado")
        sys.exit(1)
