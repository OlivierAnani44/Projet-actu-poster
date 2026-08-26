"""Détection ponctuelle des cartons rouges via API-Football.

Ce module n'exécute aucune boucle. Il peut être appelé par un futur workflow
planifié sans garder de processus en vie.
"""

from __future__ import annotations

import os

import requests


URL = "https://v3.football.api-sports.io/fixtures?live=all"


def check_red_cards(known_reds: set[str] | None = None) -> tuple[list[str], set[str]]:
    api_key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Secret API_FOOTBALL_KEY manquant.")

    known = set(known_reds or set())
    response = requests.get(
        URL,
        headers={"x-apisports-key": api_key},
        timeout=20,
    )
    response.raise_for_status()
    matches = response.json().get("response", [])
    alerts: list[str] = []

    for match in matches:
        fixture_id = match["fixture"]["id"]
        league = match["league"]["name"]
        home = match["teams"]["home"]["name"]
        away = match["teams"]["away"]["name"]

        for event in match.get("events", []):
            if event.get("type") != "Card" or event.get("detail") != "Red Card":
                continue
            player = event.get("player", {}).get("name", "Joueur inconnu")
            key = f"{fixture_id}-{player}"
            if key in known:
                continue
            known.add(key)
            alerts.append(
                "🟥 <b>CARTON ROUGE !</b>\n\n"
                f"⚽ {home} 🆚 {away}\n"
                f"👤 Joueur : {player}\n"
                f"⏱ {event.get('time', {}).get('elapsed', '?')}'\n"
                f"🏆 {league}\n\n"
                "🔥 Match totalement relancé !"
            )

    return alerts, known

