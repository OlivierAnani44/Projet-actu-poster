def generate_prediction(home, away, odds):
    if odds["home"] < odds["away"]:
        return f"🎯 **Pronostic : Victoire {home}**"
    elif odds["away"] < odds["home"]:
        return f"🎯 **Pronostic : Victoire {away}**"
    else:
        return "🎯 **Pronostic : Match nul**"
