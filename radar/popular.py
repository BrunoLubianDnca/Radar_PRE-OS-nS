"""Seleção conservadora de franquias e jogos amplamente conhecidos.

Uma nota alta ou desconto elevado não são prova de popularidade.
Esta lista é editorial e pode ser ampliada em futuras versões.
"""
from __future__ import annotations

import re
import unicodedata

POPULAR_GAMES = (
    "super mario", "mario kart", "mario party", "mario + rabbids",
    "the legend of zelda", "zelda", "pokemon", "pokémon",
    "animal crossing", "super smash bros", "splatoon", "metroid",
    "kirby", "donkey kong", "pikmin", "fire emblem", "luigi's mansion",
    "xenoblade chronicles", "bayonetta", "nintendo switch sports",
    "minecraft", "sonic", "crash bandicoot", "spyro", "rayman",
    "lego ", "star wars", "hogwarts legacy", "harry potter",
    "the witcher", "skyrim", "the elder scrolls", "assassin's creed",
    "assassins creed", "batman", "borderlands", "bioshock",
    "final fantasy", "dragon quest", "persona", "monster hunter",
    "resident evil", "mortal kombat", "street fighter",
    "naruto", "dragon ball", "one piece", "tomb raider",
    "red dead redemption", "dark souls", "diablo", "doom",
    "civilization", "sid meier", "terraria", "stardew valley",
    "hollow knight", "celeste", "cuphead", "undertale", "hades",
    "dead cells", "slay the spire", "balatro", "cult of the lamb",
    "dave the diver", "dredge", "overcooked", "it takes two",
    "the binding of isaac", "vampire survivors", "ori and the",
    "untitled goose game", "little nightmares", "the walking dead",
    "life is strange", "prince of persia", "tetris effect", "tekken",
    "subnautica", "no man's sky", "no mans sky", "portal",
    "disco elysium", "risk of rain", "darkest dungeon",
    "return to monkey island", "monkey island", "undertale",
    "spiritfarer", "the outer worlds", "yooka-laylee",
    "ace attorney", "phoenix wright", "okami", "katamari damacy",
    "just dance", "nba 2k", "ea sports fc", "fifa",
)


def normalized_title(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def is_popular(title: str) -> bool:
    value = " " + normalized_title(title) + " "
    return any(
        " " + normalized_title(name) + " " in value
        for name in POPULAR_GAMES
    )



def popularity_evidence(title: str, critic: int, player_positive: int,
                        player_reviews: int) -> tuple[int, str]:
    """Estimativa editorial (0..100), NÃO são vendas ou popularidade oficial.

    Fontes dos sinais: título/franquia conhecida da lista auditável, nota da
    crítica e nota/quantidade de avaliações exibidas pelo Vale o Jogo.
    Volume é proporcional em escala logarítmica para evitar que um único
    jogo com centenas de milhares de avaliações domine todos os alertas.
    """
    import math
    franchise = is_popular(title)
    # A ausência de dados não é confundida com avaliação negativa.
    score = (25 if franchise else 0) + round(max(0, min(100, critic)) * 0.30)
    evidence = ["franquia editorial" if franchise else "sem franquia reconhecida",
                f"crítica {critic}/100"]
    if player_reviews > 0:
        volume = min(30, round(6 * math.log10(player_reviews + 1)))
        score += volume
        evidence.append(f"{player_reviews} avaliações na fonte")
        if player_positive >= 85:
            score += 15
            evidence.append(f"{player_positive}% positivas")
    else:
        evidence.append("avaliações de jogadores não informadas")
    return min(100, score), "; ".join(evidence)


def rank_offers(offers: list) -> list:
    """Ordem de relevância explicável, preservando objetos Offer sem mutações."""
    return sorted(
        offers,
        key=lambda o: (
            -popularity_evidence(o.title, o.critic, o.player_positive,
                                 o.player_reviews)[0],
            -o.discount, o.price, o.title.casefold()
        ),
    )
