"""Moteur commun pour les publications RSS exécutées par GitHub Actions.

Chaque appel traite au maximum un article puis se termine. La planification est
volontairement déléguée aux fichiers ``.github/workflows/*.yml``.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import logging
import os
import random
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import aiohttp
import feedparser
from deep_translator import GoogleTranslator
from telegram import Bot
from telegram.request import HTTPXRequest


LOGGER = logging.getLogger("actu_poster.news")
STATE_VERSION = 1
MAX_STATE_ITEMS = 500
USER_AGENT = "ActuPosterGitHubActions/1.0"

# Les valeurs par défaut de python-telegram-bot sont courtes (notamment
# 5 s pour attendre une réponse HTTP). Sur GitHub Actions, l'envoi d'une
# photo peut régulièrement dépasser ce délai, même si Telegram fonctionne.
TELEGRAM_CONNECT_TIMEOUT = float(os.getenv("TELEGRAM_CONNECT_TIMEOUT", "20"))
TELEGRAM_READ_TIMEOUT = float(os.getenv("TELEGRAM_READ_TIMEOUT", "60"))
TELEGRAM_WRITE_TIMEOUT = float(os.getenv("TELEGRAM_WRITE_TIMEOUT", "60"))
TELEGRAM_MEDIA_WRITE_TIMEOUT = float(os.getenv("TELEGRAM_MEDIA_WRITE_TIMEOUT", "90"))
TELEGRAM_POOL_TIMEOUT = float(os.getenv("TELEGRAM_POOL_TIMEOUT", "10"))
MAX_TELEGRAM_PHOTO_BYTES = 9_500_000


@dataclass(frozen=True)
class FeedConfig:
    """Configuration d'un canal thématique."""

    name: str
    rss_feed: str
    state_file: str
    title_variants: Sequence[str]
    hashtag_variants: Sequence[str]
    comment_variants: Sequence[str]
    keyword_weights: Mapping[str, int]
    emoji: str
    bot_token_env: str
    channels_env: str
    legacy_channels_env: str | None = None
    translate_content: bool = True


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


def env_value(primary: str, fallback: str) -> str:
    """Lit une variable spécialisée, puis sa valeur commune de secours."""

    return (os.getenv(primary) or os.getenv(fallback) or "").strip()


def env_value_with_source(primary: str, fallback: str) -> tuple[str, str]:
    """Retourne la valeur et le nom de la variable réellement utilisée."""

    primary_value = (os.getenv(primary) or "").strip()
    if primary_value:
        return primary_value, primary
    fallback_value = (os.getenv(fallback) or "").strip()
    if fallback_value:
        return fallback_value, fallback
    return "", primary


def telegram_failure_hint(exc: Exception, *, bot_name: str, channel: str, token_source: str) -> str:
    """Transforme les erreurs Telegram courantes en diagnostic exploitable."""

    detail = str(exc)
    lowered = detail.lower()
    prefix = f"bot {bot_name} via {token_source} → {channel}"
    if "bot is not a member of the channel chat" in lowered:
        return (
            f"{prefix}: le bot n'est pas membre du canal. "
            "Ajoutez CE bot au canal comme administrateur avec le droit de publier, "
            f"ou corrigez {token_source}/{channel}. Erreur Telegram: {detail}"
        )
    if "chat not found" in lowered:
        return (
            f"{prefix}: canal introuvable. Vérifiez l'identifiant du canal et assurez-vous "
            f"que le bot y a accès. Erreur Telegram: {detail}"
        )
    if "not enough rights" in lowered or "not enough rights to send" in lowered:
        return (
            f"{prefix}: droits insuffisants. Donnez au bot le rôle administrateur et "
            f"l'autorisation de publier. Erreur Telegram: {detail}"
        )
    if "timed out" in lowered or "timeout" in lowered:
        return (
            f"{prefix}: délai Telegram dépassé pendant l'envoi. "
            f"Délais actifs: connexion={TELEGRAM_CONNECT_TIMEOUT:.0f}s, "
            f"lecture={TELEGRAM_READ_TIMEOUT:.0f}s, média={TELEGRAM_MEDIA_WRITE_TIMEOUT:.0f}s. "
            f"Erreur Telegram: {detail}"
        )
    return f"{prefix}: {detail}"


def parse_channels(raw_value: str) -> list[str]:
    """Accepte des identifiants Telegram séparés par des virgules."""

    return [value.strip() for value in raw_value.split(",") if value.strip()]


def clean_text(value: str) -> str:
    """Retire les balises d'un résumé RSS et normalise les espaces."""

    without_tags = re.sub(r"<[^>]*>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def truncate(value: str, maximum: int) -> str:
    value = value.strip()
    if len(value) <= maximum:
        return value
    return value[: maximum - 1].rstrip() + "…"


def entry_identifier(entry: Mapping[str, Any]) -> str:
    """Construit un identifiant stable pour empêcher les doublons."""

    return str(entry.get("id") or entry.get("link") or entry.get("title") or "").strip()


class PostedState:
    """Historique persistant par canal Telegram."""

    def __init__(self, path: str, channels: Sequence[str]) -> None:
        self.path = Path(path)
        self.channels = list(channels)
        self.posted: dict[str, list[str]] = {channel: [] for channel in channels}

    def load(self) -> None:
        if not self.path.exists():
            return

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("État illisible (%s), nouvel historique utilisé.", exc)
            return

        # Compatibilité avec l'ancien format Railway: une simple liste.
        if isinstance(raw, list):
            legacy = [str(item) for item in raw][-MAX_STATE_ITEMS:]
            self.posted = {channel: list(legacy) for channel in self.channels}
            return

        channels_state = raw.get("channels", {}) if isinstance(raw, dict) else {}
        if not isinstance(channels_state, dict):
            return

        for channel in self.channels:
            values = channels_state.get(channel, [])
            if isinstance(values, list):
                self.posted[channel] = [str(item) for item in values][-MAX_STATE_ITEMS:]

    def has(self, channel: str, item_id: str) -> bool:
        return item_id in self.posted.get(channel, [])

    def unseen_by_any(self, item_id: str) -> bool:
        return any(not self.has(channel, item_id) for channel in self.channels)

    def mark(self, channel: str, item_id: str) -> None:
        history = self.posted.setdefault(channel, [])
        if item_id not in history:
            history.append(item_id)
        self.posted[channel] = history[-MAX_STATE_ITEMS:]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": STATE_VERSION, "channels": self.posted}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)


def compute_importance(entry: Mapping[str, Any], keyword_weights: Mapping[str, int]) -> int:
    title = clean_text(str(entry.get("title", ""))).lower()
    summary = clean_text(str(entry.get("summary", ""))).lower()
    score = len(summary.split())
    for keyword, weight in keyword_weights.items():
        if keyword.lower() in title or keyword.lower() in summary:
            score += weight
    return score


def select_most_important(
    entries: Iterable[Mapping[str, Any]],
    state: PostedState,
    keyword_weights: Mapping[str, int],
) -> Mapping[str, Any] | None:
    candidates = [
        entry
        for entry in entries
        if entry_identifier(entry) and state.unseen_by_any(entry_identifier(entry))
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda entry: compute_importance(entry, keyword_weights))


def extract_image(entry: Mapping[str, Any]) -> str | None:
    media_content = entry.get("media_content")
    if media_content and isinstance(media_content, list):
        return media_content[0].get("url")

    media_thumbnail = entry.get("media_thumbnail")
    if media_thumbnail and isinstance(media_thumbnail, list):
        return media_thumbnail[0].get("url")

    match = re.search(r'<img[^>]+src=["\']([^"\']+)', str(entry.get("summary", "")))
    return match.group(1) if match else None


async def fetch_entries(url: str) -> list[Mapping[str, Any]]:
    timeout = aiohttp.ClientTimeout(total=30)
    headers = {"User-Agent": USER_AGENT}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            payload = await response.read()

    parsed = feedparser.parse(payload)
    entries = list(parsed.entries[:30])
    if not entries:
        detail = getattr(parsed, "bozo_exception", "flux vide")
        raise RuntimeError(f"Aucune entrée RSS reçue: {detail}")
    return entries


def translation_is_error(value: str) -> bool:
    """Détecte une page/message d'erreur renvoyé à la place d'une traduction."""

    normalized = clean_text(value).lower()
    if not normalized:
        return True

    error_markers = (
        "error 500",
        "server error",
        "that's an error",
        "thats an error",
        "please try again later",
        "service unavailable",
        "too many requests",
        "bad gateway",
        "gateway timeout",
        "captcha",
    )
    return any(marker in normalized for marker in error_markers)


async def translate_to_french(value: str) -> str:
    """Traduit vers le français sans jamais publier une page d'erreur Google."""

    source = clean_text(value)
    if not source:
        return source
    try:
        translated = await asyncio.to_thread(
            GoogleTranslator(source="auto", target="fr").translate,
            source,
        )
        translated = clean_text(str(translated or ""))
        if translation_is_error(translated):
            LOGGER.warning(
                "Le service de traduction a renvoyé une erreur à la place du texte; "
                "le contenu source est conservé."
            )
            return source
        return translated
    except Exception as exc:  # La publication reste possible sans traduction.
        LOGGER.warning("Traduction indisponible: %s", exc)
        return source


async def download_image(url: str | None) -> Path | None:
    if not url:
        return None

    timeout = aiohttp.ClientTimeout(total=30)
    headers = {"User-Agent": USER_AGENT}
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "")
                if content_type and not content_type.startswith("image/"):
                    raise RuntimeError(f"type inattendu: {content_type}")
                payload = await response.read()

        if not payload:
            return None

        with tempfile.NamedTemporaryFile(prefix="actu-poster-", suffix=".jpg", delete=False) as handle:
            handle.write(payload)
            return Path(handle.name)
    except Exception as exc:
        LOGGER.warning("Image indisponible: %s", exc)
        return None


def format_message(config: FeedConfig, title: str, summary: str) -> str:
    header = html.escape(random.choice(list(config.title_variants)))
    hashtags = " ".join(random.sample(list(config.hashtag_variants), k=min(5, len(config.hashtag_variants))))
    comment = html.escape(random.choice(list(config.comment_variants)))
    safe_title = html.escape(truncate(title, 180))
    safe_summary = html.escape(truncate(summary, 520))
    return (
        f"{config.emoji} <b>{header} :</b> <i>{safe_title}</i>\n\n"
        f"<blockquote>{safe_summary}</blockquote>\n\n"
        f"{hashtags}\n\n<b>{comment}</b>"
    )


async def publish_once(config: FeedConfig, *, dry_run: bool = False, force: bool = False) -> bool:
    """Publie au maximum un article, puis rend immédiatement la main."""

    token, token_source = env_value_with_source(config.bot_token_env, "BOT_TOKEN")
    channels_raw = (os.getenv(config.channels_env) or "").strip()
    if not channels_raw and config.legacy_channels_env:
        channels_raw = (os.getenv(config.legacy_channels_env) or "").strip()
    channels = parse_channels(channels_raw)

    if dry_run and not channels:
        channels = ["dry-run"]
    if not dry_run and not token:
        raise RuntimeError(
            f"Secret manquant: {config.bot_token_env} ou BOT_TOKEN."
        )
    if not channels:
        raise RuntimeError(f"Secret manquant: {config.channels_env}.")

    state = PostedState(config.state_file, channels)
    state.load()
    if force:
        state = PostedState(config.state_file, channels)

    entries = await fetch_entries(config.rss_feed)
    selected = select_most_important(entries, state, config.keyword_weights)
    if selected is None:
        LOGGER.info("Aucun nouvel article %s à publier.", config.name)
        return False

    item_id = entry_identifier(selected)
    raw_title = str(selected.get("title", ""))
    raw_summary = str(selected.get("summary", ""))

    if config.translate_content:
        title, summary = await asyncio.gather(
            translate_to_french(raw_title),
            translate_to_french(raw_summary),
        )
    else:
        title = clean_text(raw_title)
        summary = clean_text(raw_summary)

    # Dernière barrière: un message d'erreur externe ne doit jamais être posté.
    if translation_is_error(title) or translation_is_error(summary):
        raise RuntimeError(
            "Article ignoré: le titre ou le résumé ressemble à une erreur HTTP externe."
        )

    message = format_message(config, title, summary)

    if dry_run:
        print(message)
        return True

    image_path = await download_image(extract_image(selected))
    if image_path:
        try:
            image_size = image_path.stat().st_size
            LOGGER.info("Image téléchargée: %.2f Mo.", image_size / (1024 * 1024))
            if image_size > MAX_TELEGRAM_PHOTO_BYTES:
                LOGGER.warning(
                    "Image trop lourde pour un envoi photo fiable (%.2f Mo); "
                    "publication du texte uniquement.",
                    image_size / (1024 * 1024),
                )
                image_path.unlink(missing_ok=True)
                image_path = None
        except OSError as exc:
            LOGGER.warning("Impossible de lire la taille de l'image: %s", exc)

    successes = 0
    failures: list[str] = []

    # Les timeouts par défaut de PTB sont trop courts pour certains uploads
    # depuis GitHub Actions. On utilise une requête HTTP dédiée, avec un délai
    # plus confortable pour les photos et pour la réponse de Telegram.
    request = HTTPXRequest(
        connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
        read_timeout=TELEGRAM_READ_TIMEOUT,
        write_timeout=TELEGRAM_WRITE_TIMEOUT,
        media_write_timeout=TELEGRAM_MEDIA_WRITE_TIMEOUT,
        pool_timeout=TELEGRAM_POOL_TIMEOUT,
    )

    try:
        async with Bot(token=token, request=request) as bot:
            me = await bot.get_me(
                connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
                read_timeout=TELEGRAM_READ_TIMEOUT,
                write_timeout=TELEGRAM_WRITE_TIMEOUT,
                pool_timeout=TELEGRAM_POOL_TIMEOUT,
            )
            bot_name = f"@{me.username}" if me.username else f"id={me.id}"
            LOGGER.info(
                "Bot Telegram actif pour %s: %s (secret %s).",
                config.name,
                bot_name,
                token_source,
            )
            for channel in channels:
                if state.has(channel, item_id):
                    continue
                try:
                    if image_path:
                        with image_path.open("rb") as image_file:
                            await bot.send_photo(
                                chat_id=channel,
                                photo=image_file,
                                caption=message,
                                parse_mode="HTML",
                                connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
                                read_timeout=TELEGRAM_READ_TIMEOUT,
                                write_timeout=TELEGRAM_MEDIA_WRITE_TIMEOUT,
                                pool_timeout=TELEGRAM_POOL_TIMEOUT,
                            )
                    else:
                        await bot.send_message(
                            chat_id=channel,
                            text=message,
                            parse_mode="HTML",
                            disable_web_page_preview=True,
                            connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
                            read_timeout=TELEGRAM_READ_TIMEOUT,
                            write_timeout=TELEGRAM_WRITE_TIMEOUT,
                            pool_timeout=TELEGRAM_POOL_TIMEOUT,
                        )
                    state.mark(channel, item_id)
                    successes += 1
                    LOGGER.info("Publication %s envoyée sur %s.", config.name, channel)
                except Exception as exc:
                    diagnostic = telegram_failure_hint(
                        exc,
                        bot_name=bot_name,
                        channel=channel,
                        token_source=token_source,
                    )
                    failures.append(diagnostic)
                    LOGGER.error("Échec Telegram: %s", diagnostic)
    finally:
        if image_path:
            image_path.unlink(missing_ok=True)
        state.save()

    if successes == 0:
        raise RuntimeError("Aucune publication envoyée: " + "; ".join(failures))
    if failures:
        raise RuntimeError(
            f"Publication partielle ({successes} succès): " + "; ".join(failures)
        )
    return True


def run_cli(config: FeedConfig) -> None:
    parser = argparse.ArgumentParser(description=f"Publication RSS {config.name}")
    parser.add_argument("--dry-run", action="store_true", help="prévisualise sans envoyer ni modifier l'état")
    parser.add_argument("--force", action="store_true", help="ignore l'historique des publications")
    args = parser.parse_args()
    configure_logging()
    env_force = os.getenv("FORCE_RUN", "").lower() in {"1", "true", "yes", "oui"}
    asyncio.run(publish_once(config, dry_run=args.dry_run, force=args.force or env_force))
