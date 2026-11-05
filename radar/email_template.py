"""E-mails HTML compatíveis com clientes de e-mail (tabelas e CSS inline)."""
from __future__ import annotations

import html
from datetime import datetime
from decimal import Decimal

from .core import BR, Offer


def brl(value: Decimal) -> str:
    return "R$ " + f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def escape(value: str) -> str:
    return html.escape(str(value), quote=True)


def email_shell(content: str, preview: bool = False) -> str:
    title = "Prévia do Radar" if preview else "Ofertas do Nintendo Switch"
    return f"""<!doctype html><html lang="pt-BR"><head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    </head><body style="margin:0;padding:0;background-color:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#172033">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f1f5f9">
      <tr><td align="center" style="padding:28px 12px">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:620px;background:#ffffff;border-radius:14px;overflow:hidden">
          <tr><td style="background:#152239;color:#ffffff;padding:28px 26px">
            <div style="font-size:12px;letter-spacing:1.3px;font-weight:bold;color:#b9d6f5">RADAR NINTENDO SWITCH</div>
            <h1 style="margin:10px 0 0;font-size:25px;line-height:31px;color:#ffffff">{title}</h1>
            <p style="font-size:13px;line-height:21px;margin:12px 0 0;color:#cbd5e1">eShop Brasil &middot; jogos digitais &middot; até R$ 100 &middot; 30% a 90% OFF</p>
          </td></tr>
          <tr><td style="padding:22px 23px">{content}</td></tr>
          <tr><td style="padding:18px 26px;background:#f8fafc;font-size:12px;line-height:19px;color:#64748b">
            Valores sujeitos a alteração. Confira preço, região e disponibilidade na Nintendo antes de comprar.<br>
            Radar pessoal de ofertas. Fontes e avaliações: Vale o Jogo. Não afiliado à Nintendo.
          </td></tr>
        </table>
      </td></tr>
    </table></body></html>"""


def format_email(offers: list[Offer], max_items: int, *, preview: bool = False) -> tuple[str, str]:
    shown = sorted(offers, key=lambda o: (-o.discount, o.price, -o.critic))[:max_items]
    timestamp = datetime.now(BR).strftime("%d/%m/%Y às %H:%M")
    intro = ("Prévia solicitada manualmente. Os valores são os da consulta e não representam alertas inéditos."
             if preview else f"{len(offers)} nova(s) oferta(s) detectada(s).")
    message = f"<p style='font-size:14px;color:#475569;margin:0 0 18px;line-height:22px'>{escape(intro)}<br><span style='font-size:12px'>{escape(timestamp)} (Brasília)</span></p>"
    text_lines = [f"Radar Nintendo Switch — {'PRÉVIA' if preview else 'NOVAS OFERTAS'}",
                  intro, f"Consulta: {timestamp}", ""]
    for offer in shown:
        # Fontes de imagens são previamente verificadas na extração; qualquer falha
        # de carregamento no Gmail não esconde os dados do card.
        image_url = getattr(offer, "image_url", "") or ""
        thumb = (f'<img src="{escape(image_url)}" alt="Capa de {escape(offer.title)}" '
                 'width="110" style="display:block;width:110px;max-width:110px;height:auto;'
                 'border:0;border-radius:7px" />') if image_url else (
                 '<div style="width:110px;padding:25px 0;text-align:center;background:#e2e8f0;'
                 'color:#64748b;font-size:12px;border-radius:7px">Nintendo Switch</div>')
        shop = escape(offer.shop_url)
        page = escape(offer.page_url)
        message += f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
               style="border:1px solid #e2e8f0;border-radius:11px;margin:0 0 14px;background:#ffffff">
          <tr><td valign="top" width="116" style="padding:15px 8px 15px 14px">{thumb}</td>
          <td valign="top" style="padding:15px 14px 15px 5px">
            <div style="font-size:15px;line-height:20px;font-weight:bold;color:#0f172a">{escape(offer.title)}</div>
            <div style="padding-top:8px"><span style="font-size:22px;font-weight:bold;color:#047857">{escape(brl(offer.price))}</span>
              <span style="font-size:12px;color:#64748b;text-decoration:line-through">{escape(brl(offer.old_price))}</span></div>
            <div style="margin:7px 0"><span style="font-weight:bold;font-size:12px;color:#9a3412;background:#ffedd5;padding:4px 7px;border-radius:5px">-{offer.discount}% OFF</span></div>
            <div style="font-size:11px;line-height:18px;color:#64748b">Crítica: {offer.critic}/100 &middot; Jogadores: {offer.player_positive}% ({offer.player_reviews} análises)</div>
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-top:11px">
              <tr><td style="background:#2563eb;border-radius:6px;padding:10px 13px">
                <a href="{shop}" style="font-size:12px;font-weight:bold;text-decoration:none;color:#ffffff">Ver na Nintendo eShop</a>
              </td></tr></table>
            <div style="font-size:11px;margin-top:10px"><a href="{page}" style="color:#2563eb">Conferir preço e avaliações</a></div>
          </td></tr>
        </table>"""
        text_lines += [f"{offer.title} — {brl(offer.price)} (antes {brl(offer.old_price)}, -{offer.discount}%)",
                       f"Crítica: {offer.critic}/100 · Jogadores: {offer.player_positive}%",
                       f"Nintendo: {offer.shop_url}", f"Fonte: {offer.page_url}", ""]
    if len(offers) > len(shown):
        remaining = len(offers)-len(shown)
        message += f'<p style="font-size:12px;color:#64748b">Mais {remaining} ofertas não exibidas neste e-mail.</p>'
        text_lines.append(f"Mais {remaining} ofertas não exibidas.")
    text_lines.append("Confirme o preço na eShop antes da compra.")
    return "\n".join(text_lines), email_shell(message, preview=preview)


def format_test_email() -> tuple[str, str]:
    message = ("Teste de envio realizado. As configurações SMTP estão operacionais e "
               "o layout HTML pode ser exibido pelo seu provedor de e-mail. "
               "Este teste não altera o histórico nem consulta promoções.")
    body = ('<div style="padding:20px;border:1px solid #d1fae5;border-radius:10px;'
            'background:#f0fdf4;color:#166534;font-size:15px;line-height:24px">'
            '<strong>Teste de notificação</strong><p style="margin:9px 0 0">'
            + escape(message) + '</p></div>')
    return "Radar Nintendo Switch — E-mail de teste\n\n" + message, email_shell(body, preview=True)
