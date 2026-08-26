from pathlib import Path

from news_publisher import (
    FeedConfig,
    PostedState,
    format_message,
    select_most_important,
)


def sample_config(state_file: Path) -> FeedConfig:
    return FeedConfig(
        name="test",
        rss_feed="https://example.test/rss.xml",
        state_file=str(state_file),
        title_variants=("ACTU",),
        hashtag_variants=("#Test",),
        comment_variants=("Votre avis ?",),
        keyword_weights={"important": 20},
        emoji="🔥",
        bot_token_env="TEST_TOKEN",
        channels_env="TEST_CHANNELS",
    )


def test_state_is_persisted_per_channel(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = PostedState(str(state_path), ["@one", "@two"])
    state.mark("@one", "article-1")
    state.save()

    restored = PostedState(str(state_path), ["@one", "@two"])
    restored.load()

    assert restored.has("@one", "article-1")
    assert not restored.has("@two", "article-1")
    assert restored.unseen_by_any("article-1")


def test_legacy_list_state_is_supported(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('["old-article"]', encoding="utf-8")

    state = PostedState(str(state_path), ["@one", "@two"])
    state.load()

    assert state.has("@one", "old-article")
    assert state.has("@two", "old-article")


def test_selection_prefers_important_unseen_article(tmp_path: Path) -> None:
    state = PostedState(str(tmp_path / "state.json"), ["@channel"])
    state.mark("@channel", "already-posted")
    entries = [
        {"id": "already-posted", "title": "important", "summary": "long " * 40},
        {"id": "normal", "title": "normal", "summary": "court"},
        {"id": "priority", "title": "Information importante", "summary": "court"},
    ]

    selected = select_most_important(entries, state, {"important": 20})

    assert selected is not None
    assert selected["id"] == "priority"


def test_html_is_escaped_and_caption_stays_short(tmp_path: Path) -> None:
    config = sample_config(tmp_path / "state.json")
    message = format_message(config, "A & B < C", "<p>Résumé & détails</p> " * 100)

    assert "A &amp; B &lt; C" in message
    assert "<p>" not in message
    assert len(message) < 1024

