"""Acompanhamento nominal de jogos Nintendo.

Não gera URLs supostas nem inventa preços: apenas cruza jogos monitorados
com títulos efetivamente encontrados nas vitrines públicas. A compra só é
considerada quando parse_detail confirma oferta digital e link eShop.
"""
from __future__ import annotations

from dataclasses import dataclass
from .popular import normalized_title

WATCHED_GAMES = (
    "Super Mario Bros. Wonder",
    "Super Mario Odyssey",
    "New Super Mario Bros. U Deluxe",
    "Super Mario 3D World + Bowser's Fury",
    "Super Mario RPG",
    "Paper Mario: The Thousand-Year Door",
    "Mario Kart 8 Deluxe",
    "Super Mario Party",
    "Super Mario Party Jamboree",
    "Mario Party Superstars",
    "Mario vs. Donkey Kong",
    "Donkey Kong Country: Tropical Freeze",
    "Donkey Kong Country Returns HD",
    "The Legend of Zelda: Breath of the Wild",
    "The Legend of Zelda: Tears of the Kingdom",
    "The Legend of Zelda: Echoes of Wisdom",
    "The Legend of Zelda: Link's Awakening",
    "Kirby and the Forgotten Land",
    "Kirby's Return to Dream Land Deluxe",
    "Metroid Dread",
    "Metroid Prime Remastered",
    "Luigi's Mansion 2 HD",
    "Luigi's Mansion 3",
    "Animal Crossing: New Horizons",
    "Pikmin 4",
    "Splatoon 3",
    "Fire Emblem Engage",
    "Super Smash Bros. Ultimate",
    "Pokémon Legends: Arceus",
    "Pokémon Scarlet",
    "Pokémon Violet",
)


def matched_watch_game(title: str) -> str | None:
    """Correspondência exata normalizada, com sufixos de versão bem delimitados."""
    actual = normalized_title(title.replace("™", "").replace("®", ""))
    for wanted in WATCHED_GAMES:
        expected = normalized_title(wanted)
        if actual == expected:
            return wanted
        # Algumas fichas usam marcas comerciais e 'Nintendo Switch' como sufixo.
        if actual in (expected + " nintendo switch", expected + " switch"):
            return wanted
    return None


@dataclass
class WatchEntry:
    name: str
    page_url: str = ""
    status: str = "não apareceu nas vitrines"


def create_watch_report() -> dict[str, WatchEntry]:
    return {name: WatchEntry(name=name) for name in WATCHED_GAMES}


def register_candidate(report: dict[str, WatchEntry], title: str, url: str) -> None:
    name = matched_watch_game(title)
    if name and name in report and not report[name].page_url:
        report[name].page_url = url
        report[name].status = "apareceu; oferta ainda não verificada"


def register_catalog_match(report: dict[str, WatchEntry], title: str, url: str) -> None:
    """Identificado por busca nominal; ainda não significa promoção."""
    name = matched_watch_game(title)
    if name in report:
        entry = report[name]
        entry.page_url = url
        entry.status = "localizado no catálogo BR; desconto não confirmado"


def register_result(report: dict[str, WatchEntry], title: str, url: str,
                    *, parsed: bool, eligible: bool = False) -> None:
    name = matched_watch_game(title)
    if not name or name not in report:
        return
    entry = report[name]
    entry.page_url = url
    entry.status = ("oferta elegível" if eligible else
                    "fora dos critérios" if parsed else
                    "sem oferta digital verificável")


def watch_counts(report: dict[str, WatchEntry]) -> dict[str, int]:
    statuses = [entry.status for entry in report.values()]
    return {
        "acompanhados": len(statuses),
        "encontrados": sum(bool(item.page_url) for item in report.values()),
        "elegiveis": statuses.count("oferta elegível"),
        "sem_oferta_verificavel": statuses.count("sem oferta digital verificável"),
        "fora_criterios": statuses.count("fora dos critérios"),
        "nao_encontrados": statuses.count("não apareceu nas vitrines"),
    }
