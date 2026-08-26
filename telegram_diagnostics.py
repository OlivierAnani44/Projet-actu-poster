"""Diagnostic manuel des associations bot Telegram → canal, sans publication."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class Route:
    label: str
    token_env: str
    channel_env: str


ROUTES = (
    Route("Actualités football", "FOOTBALL_BOT_TOKEN", "FOOTBALL_CHANNEL_ID"),
    Route("Actualités cinéma", "CINEMA_BOT_TOKEN", "CINEMA_CHANNEL_ID"),
    Route("Pronostics", "PREDICTIONS_BOT_TOKEN", "PREDICTIONS_CHANNEL_ID"),
)


def resolve_token(specialized: str) -> tuple[str, str]:
    value = (os.getenv(specialized) or "").strip()
    if value:
        return value, specialized
    return (os.getenv("BOT_TOKEN") or "").strip(), "BOT_TOKEN"


def api(token: str, method: str, **params):
    response = requests.post(
        f"https://api.telegram.org/bot{token}/{method}",
        json=params,
        timeout=15,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"ok": False, "description": response.text[:300]}
    return response.status_code, payload


def diagnose(route: Route) -> bool:
    token, token_source = resolve_token(route.token_env)
    channel = (os.getenv(route.channel_env) or "").strip()
    print(f"\n=== {route.label} ===")
    print(f"Token utilisé : {token_source}")
    print(f"Canal : {channel or '[MANQUANT]'}")

    if not token or not channel:
        print("❌ Secret manquant.")
        return False

    status, me = api(token, "getMe")
    if status != 200 or not me.get("ok"):
        print(f"❌ Token invalide ({status}) : {me.get('description', 'erreur inconnue')}")
        return False

    bot = me["result"]
    username = f"@{bot.get('username')}" if bot.get("username") else f"id={bot['id']}"
    print(f"Bot : {username}")

    status, member = api(token, "getChatMember", chat_id=channel, user_id=bot["id"])
    if status != 200 or not member.get("ok"):
        description = member.get("description", "erreur inconnue")
        print(f"❌ Le bot n'a pas accès à ce canal ({status}) : {description}")
        print(f"➡️ Ajoutez {username} au canal {channel} comme administrateur.")
        return False

    info = member["result"]
    membership = info.get("status")
    can_post = info.get("can_post_messages")
    print(f"Statut dans le canal : {membership}")

    if membership not in {"administrator", "creator"}:
        print("❌ Pour publier dans un canal Telegram, le bot doit être administrateur.")
        return False
    if can_post is False:
        print("❌ Le bot est administrateur mais n'a pas le droit de publier des messages.")
        return False

    print("✅ Association bot → canal correcte.")
    return True


def main() -> int:
    ok = True
    for route in ROUTES:
        ok = diagnose(route) and ok
    print("\n" + ("✅ Tous les canaux sont correctement configurés." if ok else "❌ Au moins une association bot/canal doit être corrigée."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
