"""Lecture Telegram ponctuelle, adaptée aux exécutions courtes de GitHub Actions.

Le fichier ``session_name.session`` d'origine a volontairement été supprimé.
Utilisez une StringSession stockée dans le secret TELEGRAM_STRING_SESSION.
"""

from __future__ import annotations

import asyncio
import os

from telethon import TelegramClient
from telethon.sessions import StringSession


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variable/secret {name} manquant.")
    return value


async def read_recent_messages() -> None:
    api_id = int(required_env("TELEGRAM_API_ID"))
    api_hash = required_env("TELEGRAM_API_HASH")
    string_session = required_env("TELEGRAM_STRING_SESSION")
    channel_username = os.getenv("TELEGRAM_SOURCE_CHANNEL", "Vinland_Saga_vf_fr").strip()
    limit = max(1, min(100, int(os.getenv("TELEGRAM_MESSAGE_LIMIT", "20"))))

    async with TelegramClient(StringSession(string_session), api_id, api_hash) as client:
        channel = await client.get_entity(channel_username)
        print(f"📡 Canal : {getattr(channel, 'title', channel_username)}")
        messages = await client.get_messages(channel, limit=limit)
        for message in reversed(messages):
            if message.text:
                print(f"\n[{message.date}]\n{message.text[:500]}")


if __name__ == "__main__":
    asyncio.run(read_recent_messages())

