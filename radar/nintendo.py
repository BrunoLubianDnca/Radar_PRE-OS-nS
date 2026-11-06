"""Curadoria conservadora de séries Nintendo para alertas prioritários.

Uma franquia reconhecida NÃO comprova editora oficial de cada edição.
Mantemos exclusões explícitas e nunca aceitamos Switch 2 Edition por engano.
"""
from __future__ import annotations

from .popular import normalized_title

# Séries conhecidas, na versão base do Nintendo Switch.
FIRST_PARTY_PREFIXES = (
    "super mario", "mario kart", "mario party", "super mario party",
    "paper mario", "mario vs donkey kong", "luigi s mansion",
    "donkey kong", "the legend of zelda", "zelda", "kirby",
    "metroid", "pikmin", "splatoon", "animal crossing", "fire emblem",
    "super smash bros", "yoshi s crafted world", "wario",
    "advance wars", "nintendo switch sports", "ring fit adventure",
    "pokemon", "pokémon",
)

# Mesmo usando personagens da Nintendo, não atribuir a linha especial
# automaticamente a séries publicadas por parceiros.
EXCLUDED_PREFIXES = (
    "mario rabbids", "mario + rabbids", "mario and sonic",
    "mario sonic", "pokemon unite", "pokemon cafe",
)


def is_nintendo_priority(title: str) -> bool:
    name = normalized_title(title)
    if (not name or "nintendo switch 2 edition" in name
            or name.endswith("switch 2")
            or any(name.startswith(normalized_title(p) + " ") or
                   name == normalized_title(p) for p in EXCLUDED_PREFIXES)):
        return False
    return any(name == normalized_title(p) or
               name.startswith(normalized_title(p) + " ")
               for p in FIRST_PARTY_PREFIXES)
