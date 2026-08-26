def advanced_prediction(stats):
    score_home = (
        stats["home_form"] * 0.3 +
        stats["home_xg"] * 0.4 +
        stats["home_home_adv"] * 0.2 -
        stats["home_red_risk"] * 0.1
    )

    score_away = (
        stats["away_form"] * 0.3 +
        stats["away_xg"] * 0.4 -
        stats["away_home_adv"] * 0.2 -
        stats["away_red_risk"] * 0.1
    )

    if score_home > score_away:
        return "Victoire domicile", "2-1"
    elif score_away > score_home:
        return "Victoire extérieur", "1-2"
    else:
        return "Match nul", "1-1"
