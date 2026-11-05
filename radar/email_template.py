"""E-mails HTML responsivos para o Radar Nintendo Switch.

Compatibilidade: Gmail, Apple Mail, Outlook e clientes móveis.
Sem dependências externas. Mantém as assinaturas públicas existentes.
"""
from __future__ import annotations

import html
from datetime import datetime
from decimal import Decimal

from .core import BR, Offer


def brl(value: Decimal) -> str:
    return "R$ " + f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def email_shell(content: str, preview: bool = False) -> str:
    title = "Prévia do Radar" if preview else "Ofertas do Nintendo Switch"
    preheader = (
        "Confira como as ofertas aparecem no seu e-mail."
        if preview else "Jogos selecionados, preços e avaliações em um só lugar."
    )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>{escape(title)}</title>
  <style>
    /* Melhorias progressivas: todo o conteúdo continua legível sem este CSS. */
    @media only screen and (max-width: 480px) {{
      .outer-pad {{ padding: 12px 8px !important; }}
      .head-pad {{ padding: 24px 19px 21px !important; }}
      .body-pad {{ padding: 23px 16px 12px !important; }}
      .foot-pad {{ padding: 18px 19px !important; }}
      .card-image {{ width: 82px !important; max-width: 82px !important; }}
      .image-cell {{ width: 82px !important; padding: 16px 10px 16px 14px !important; }}
      .details-cell {{ padding: 15px 12px 15px 0 !important; }}
      .game-title {{ font-size: 15px !important; line-height: 20px !important; }}
      .price {{ font-size: 21px !important; }}
      .action-link {{ font-size: 12px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;width:100%;background-color:#f3f5f8;color:#152033;font-family:Arial,Helvetica,sans-serif;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%">
  <div style="display:none!important;font-size:1px;color:#f3f5f8;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all">
    {escape(preheader)}
  </div>
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;background-color:#f3f5f8">
    <tr>
      <td class="outer-pad" align="center" style="padding:30px 12px">
        <!--[if mso]><table role="presentation" width="600" align="center" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:separate;max-width:600px;background-color:#ffffff;border:1px solid #e3e8ef">
          <tr>
            <td class="head-pad" style="padding:29px 30px 26px;border-bottom:1px solid #e7ebf1">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse">
                <tr>
                  <td valign="middle" style="font-size:13px;line-height:20px;font-weight:700;letter-spacing:1.2px;color:#14263f">RADAR <span style="color:#2563eb">SWITCH</span></td>
                  <td align="right" valign="middle" style="font-size:11px;line-height:16px;color:#778397">ESHOP BRASIL</td>
                </tr>
              </table>
              <h1 style="margin:27px 0 8px;font-size:26px;line-height:32px;font-weight:700;letter-spacing:-0.6px;color:#101c2e">{escape(title)}</h1>
              <p style="margin:0;font-size:13px;line-height:20px;color:#657287">Jogos digitais até R$ 100, com descontos de 30% a 90%.</p>
            </td>
          </tr>
          <tr><td class="body-pad" style="padding:26px 30px 15px">{content}</td></tr>
          <tr>
            <td class="foot-pad" style="padding:22px 30px;border-top:1px solid #e7ebf1;background-color:#fbfcfe">
              <p style="margin:0 0 6px;font-size:12px;line-height:18px;font-weight:700;color:#34445b">Antes de comprar</p>
              <p style="margin:0;font-size:11px;line-height:18px;color:#718096">Preços e disponibilidade podem mudar. Confirme as condições na Nintendo eShop. Avaliações e informações: Vale o Jogo.</p>
              <p style="margin:12px 0 0;font-size:11px;line-height:17px;color:#8994a4">Radar pessoal de ofertas. Projeto independente, sem afiliação com a Nintendo.</p>
            </td>
          </tr>
        </table>
        <!--[if mso]></td></tr></table><![endif]-->
      </td>
    </tr>
  </table>
</body>
</html>"""


def _offer_card(offer: Offer) -> str:
    image_url = getattr(offer, "image_url", "") or ""
    if image_url:
        image = (
            f'<img class="card-image" src="{escape(image_url)}" alt="Capa de {escape(offer.title)}" '
            'width="96" style="display:block;width:96px;max-width:96px;height:auto;border:0;outline:none;text-decoration:none;background-color:#edf1f6">'
        )
    else:
        image = (
            '<table role="presentation" width="96" cellpadding="0" cellspacing="0" border="0" '
            'style="border-collapse:collapse;background-color:#edf1f6"><tr>'
            '<td align="center" height="112" style="height:112px;padding:0 5px;font-size:11px;line-height:16px;color:#657287">'
            'Nintendo<br>Switch</td></tr></table>'
        )

    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate;border:1px solid #e2e8f0;background-color:#ffffff;margin:0 0 12px">
      <tr>
        <td class="image-cell" width="96" valign="top" style="width:96px;padding:17px 13px 17px 17px">{image}</td>
        <td class="details-cell" valign="top" style="padding:17px 17px 17px 0">
          <p class="game-title" style="margin:0 0 9px;font-size:16px;line-height:22px;font-weight:700;color:#152033">{escape(offer.title)}</p>
          <p style="margin:0 0 8px;line-height:26px">
            <span class="price" style="font-size:23px;line-height:27px;font-weight:700;color:#152033;white-space:nowrap">{escape(brl(offer.price))}</span>
            <span style="font-size:12px;line-height:18px;color:#8994a4;text-decoration:line-through;white-space:nowrap">{escape(brl(offer.old_price))}</span>
          </p>
          <p style="margin:0 0 11px;font-size:12px;line-height:19px">
            <span style="font-weight:700;color:#147d57">{escape(offer.discount)}% OFF</span>
            <span style="color:#c5cbd5">&nbsp; | &nbsp;</span>
            <span style="color:#69778b">Crítica {escape(offer.critic)}/100</span>
          </p>
          <p style="margin:0 0 12px;font-size:12px;line-height:18px;color:#69778b">{escape(offer.player_positive)}% de avaliações positivas · {escape(offer.player_reviews)} análises</p>
          <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate">
            <tr><td bgcolor="#1b4f98" style="background-color:#1b4f98;padding:10px 13px">
              <a class="action-link" href="{escape(offer.shop_url)}" target="_blank" style="display:inline-block;color:#ffffff;font-size:12px;line-height:17px;font-weight:700;text-decoration:none">Ver oferta na eShop</a>
            </td></tr>
          </table>
          <p style="margin:11px 0 0;font-size:11px;line-height:17px"><a href="{escape(offer.page_url)}" target="_blank" style="color:#466a9c;text-decoration:underline">Preço e avaliações da fonte</a></p>
        </td>
      </tr>
    </table>"""


def format_email(offers: list[Offer], max_items: int, *, preview: bool = False) -> tuple[str, str]:
    # Preserva exatamente o critério de ordenação do projeto atual.
    shown = sorted(offers, key=lambda o: (-o.discount, o.price, -o.critic))[:max_items]
    timestamp = datetime.now(BR).strftime("%d/%m/%Y às %H:%M")
    intro = (
        "Prévia solicitada manualmente. Os valores são os da consulta e não representam alertas inéditos."
        if preview else f"{len(offers)} nova(s) oferta(s) detectada(s)."
    )

    title = "Ofertas selecionadas"
    message = f"""
      <p style="margin:0 0 7px;font-size:13px;line-height:20px;color:#58677c">{escape(intro)}</p>
      <p style="margin:0 0 25px;font-size:11px;line-height:17px;color:#8a95a5">Consulta em {escape(timestamp)} (Brasília)</p>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin:0 0 13px">
        <tr><td style="font-size:16px;line-height:23px;font-weight:700;color:#152033">{title}</td>
        <td align="right" style="font-size:11px;line-height:17px;color:#7c8899">{len(shown)} {('jogo' if len(shown) == 1 else 'jogos')}</td></tr>
      </table>"""
    text_lines = [
        f"Radar Nintendo Switch — {'PRÉVIA' if preview else 'NOVAS OFERTAS'}",
        intro, f"Consulta: {timestamp}", ""
    ]

    if not shown:
        message += '<p style="margin:0 0 22px;padding:18px;background-color:#f8fafc;font-size:13px;line-height:21px;color:#64748b">Nenhuma oferta para exibir nesta consulta.</p>'
        text_lines.append("Nenhuma oferta para exibir nesta consulta.")

    for offer in shown:
        message += _offer_card(offer)
        text_lines += [
            f"{offer.title} — {brl(offer.price)} (antes {brl(offer.old_price)}, -{offer.discount}%)",
            f"Crítica: {offer.critic}/100 · Jogadores: {offer.player_positive}%",
            f"Nintendo: {offer.shop_url}", f"Fonte: {offer.page_url}", ""
        ]

    if len(offers) > len(shown):
        remaining = len(offers) - len(shown)
        message += f'<p style="margin:10px 0 8px;font-size:12px;line-height:19px;color:#7c8899">Mais {remaining} ofertas não exibidas neste e-mail.</p>'
        text_lines.append(f"Mais {remaining} ofertas não exibidas.")

    text_lines.append("Confirme o preço na eShop antes da compra.")
    return "\n".join(text_lines), email_shell(message, preview=preview)


def format_test_email() -> tuple[str, str]:
    message = (
        "Teste de envio realizado. As configurações SMTP estão operacionais e "
        "o layout HTML pode ser exibido pelo seu provedor de e-mail. "
        "Este teste não altera o histórico nem consulta promoções."
    )
    body = (
        '<p style="margin:0 0 9px;font-size:16px;line-height:23px;font-weight:700;color:#152033">Teste de notificação</p>'
        '<p style="margin:0 0 16px;font-size:13px;line-height:22px;color:#58677c">'
        + escape(message) + '</p>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse">'
        '<tr><td style="padding:13px 15px;background-color:#edf8f3;border-left:3px solid #238b61;color:#21664d;font-size:12px;line-height:19px">'
        'Envio de teste concluído.</td></tr></table>'
    )
    return "Radar Nintendo Switch — E-mail de teste\n\n" + message, email_shell(body, preview=True)

