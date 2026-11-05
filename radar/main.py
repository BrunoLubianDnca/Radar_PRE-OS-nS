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

from .core import BR, Offer, discovery, parse_detail, qualifies, select_alerts
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


def money_brl(value) -> str:
    return "R$ " + f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def email_alert(offers: list[Offer], max_items: int, *, test_email: bool = False) -> None:
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("Secrets ausentes: " + ", ".join(missing))
    msg = EmailMessage()
    msg["From"] = os.getenv("EMAIL_FROM") or os.environ["SMTP_USER"]
    msg["To"] = os.environ["EMAIL_TO"]
    msg["Subject"] = ("[Radar Switch] Teste de e-mail — configuração OK" if test_email
                      else f"[Radar Switch] {len(offers)} promoção(ões) nova(s) até R$ 100")
    plain, rich = format_test_email() if test_email else format_email(offers, max_items)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Sem SMTP e sem salvar estado")
    parser.add_argument("--send-initial", action="store_true", help="Enviar ofertas da primeira execução")
    parser.add_argument("--test-email", action="store_true", help="Envia apenas um e-mail de teste, sem consulta ou mudanças no histórico")
    args = parser.parse_args(argv)
    if args.test_email:
        email_alert([], 0, test_email=True)
        LOG.info("E-mail de teste aceito pelo SMTP; nenhuma coleta e nenhum estado alterado")
        return 0
    settings = json.loads((ROOT / "config/settings.json").read_text(encoding="utf-8"))
    state_file = ROOT / "data/state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    session = requests.Session()
    source = settings["source_url"]
    html_listing = fetch(session, source)
    urls = discovery(html_listing, source, int(settings["max_source_age_hours"]))
    # MVP acompanha os jogos exibidos na primeira página da vitrine, não todo o catálogo.
    LOG.info("Candidatos na vitrine: %d", len(urls))
    offers: list[Offer] = []
    failed = 0
    parsed_count = 0
    discarded_count = 0
    for i, url in enumerate(urls, 1):
        LOG.info("Analisando %d/%d: %s", i, len(urls), url)
        if i > 1:
            time.sleep(float(settings["request_delay_seconds"]))
        try:
            game_html = fetch(session, url)
            offer = parse_detail(game_html, url)
            if offer is None:
                discarded_count += 1
                continue
            parsed_count += 1
            if qualifies(offer, settings):
                offers.append(offer)
                LOG.info("Elegível: %s | %s | -%d%%", offer.title, money_brl(offer.price), offer.discount)
            else:
                LOG.info("Fora dos filtros: %s | %s | -%d%% | Crítica %d | Jogadores %d%% (%d)", offer.title, money_brl(offer.price), offer.discount, offer.critic, offer.player_positive, offer.player_reviews)
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            failed += 1
            LOG.warning("Falha na página %s: %s", url, exc)
    # Não grave o estado se parte da vitrine estiver indisponível: evita falsos
    # avisos de 'promoção nova' quando a página se recuperar.
    LOG.info("Resumo: candidatos=%d, interpretados=%d, sem dados=%d, elegíveis=%d, erros HTTP=%d", len(urls), parsed_count, discarded_count, len(offers), failed)
    if failed:
        raise RuntimeError(f"Falharam {failed}/{len(urls)} páginas. Estado preservado.")
    if parsed_count == 0:
        raise RuntimeError("Nenhuma oferta digital reconhecida: verificar estrutura do site; estado preservado")
    if not offers:
        LOG.info("Nenhum jogo atingiu todos os filtros. Histórico preservado, sem e-mail.")
        return 0
    if len(urls) >= 10 and parsed_count < len(urls) // 3:
        raise RuntimeError("Cobertura do parser insuficiente; evitar histórico parcial")
    alerts, new_state = select_alerts(offers, state, bootstrap=not args.send_initial)
    LOG.info("Elegíveis: %d | Alertas: %d", len(offers), len(alerts))
    if args.dry_run:
        for offer in alerts:
            print(f"{offer.title} | {money_brl(offer.price)} | -{offer.discount}% | {offer.shop_url}")
        print("DRY RUN: nenhum e-mail enviado; estado não modificado")
        return 0
    if alerts:
        email_alert(alerts, int(settings["max_games_per_email"]))
        LOG.info("E-mail aceito pelo SMTP")
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
