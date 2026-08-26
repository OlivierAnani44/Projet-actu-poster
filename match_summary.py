"""Résumés ponctuels des matchs terminés via API-Football."""

from __future__ import annotations

import os

import requests


URL_FINISHED = "https://v3.football.api-sports.io/fixtures?status=FT"


def generate_summary(match: dict) -> str:
    home = match["teams"]["home"]["name"]
    away = match["teams"]["away"]["name"]
    score_h = match["goals"]["home"]
    score_a = match["goals"]["away"]
    league = match["league"]["name"]
    goals = [event for event in match.get("events", []) if event.get("type") == "Goal"]

    summary = (
        "📝 <b>RÉSUMÉ DU MATCH</b>\n\n"
        f"⚽ {home} {score_h} - {score_a} {away}\n"
        f"🏆 {league}\n\n"
    )
    for goal in goals:
        summary += (
            f"⚽ {goal.get('player', {}).get('name', 'Buteur inconnu')} "
            f"({goal.get('time', {}).get('elapsed', '?')}')\n"
        )
    return summary + "\n🔥 Un match intense jusqu’au coup de sifflet final !"


def fetch_finished_matches() -> list[dict]:
    api_key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Secret API_FOOTBALL_KEY manquant.")
    response = requests.get(
        URL_FINISHED,
        headers={"x-apisports-key": api_key},
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("response", [])

