from ai_rewrite import rewrite_text

def detect_competition(text):
    competitions = {
        "Ligue 1": "#Ligue1 🇫🇷",
        "Premier League": "#PremierLeague 🇬🇧",
        "Liga": "#Liga 🇪🇸",
        "Serie A": "#SerieA 🇮🇹",
        "Bundesliga": "#Bundesliga 🇩🇪",
        "Champions League": "#UCL 🏆"
    }
    for key in competitions:
        if key.lower() in text.lower():
            return competitions[key]
    return "#Football ⚽"

def format_post(article):
    rewritten = rewrite_text(article["title"], article["summary"])
    hashtag = detect_competition(rewritten)

    message = f"""
⚽ **ACTUALITÉ FOOTBALL**

🔥 {rewritten}

🔗 [Lire la suite]({article['link']})

{hashtag} #FootNews #Football
"""
    return message, article["image"]
