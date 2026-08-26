import re

import main3


def test_local_prediction_has_valid_shape() -> None:
    home = main3.TeamForm(wins=4, draws=1, losses=0, gf=12, ga=3, matches_analyzed=5)
    away = main3.TeamForm(wins=1, draws=1, losses=3, gf=4, ga=10, matches_analyzed=5)

    prediction, confidence, analysis, score = main3.analyze_match_locally(
        "Real Madrid", "Example FC", home, away, "esp.1"
    )

    assert prediction in {"home_win", "away_win", "draw"}
    assert 4 <= confidence <= 9
    assert analysis
    assert re.fullmatch(r"\d-\d", score)


def test_telegram_html_escapes_dynamic_team_names() -> None:
    prediction = main3.MatchPrediction(
        home_team="A & B",
        away_team="C < D",
        prediction="home_win",
        confidence=7.0,
        odds=2.5,
        analysis_text="Forme <forte> & stable",
        league="Test & Cup",
        score_probable="2-1",
    )

    message = main3.format_combo_message("TEST", [prediction], "MEDIUM")

    assert "A &amp; B" in message
    assert "C &lt; D" in message
    assert "Forme &lt;forte&gt; &amp; stable" in message

