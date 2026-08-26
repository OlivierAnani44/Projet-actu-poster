"""Actualités cinéma — point d'entrée compatible GitHub Actions."""

from news_publisher import FeedConfig, run_cli


CONFIG = FeedConfig(
    name="cinéma",
    rss_feed="https://www.allocine.fr/rss/news.xml",
    state_file=".state/cinema.json",
    bot_token_env="CINEMA_BOT_TOKEN",
    channels_env="CINEMA_CHANNEL_ID",
    legacy_channels_env="CINEMA_CHANNELS",
    emoji="🎬🎥",
    title_variants=(
        "CINÉ INFO", "ACTU FILMS", "NEWS SÉRIES", "FLASH CINÉ",
        "DERNIÈRE MINUTE CINÉ", "ACTUALITÉ FILM", "SÉRIES À LA UNE",
        "LE POINT CINÉ", "INFO FILM", "RÉSUMÉ SÉRIES",
    ),
    hashtag_variants=(
        "#Cinéma", "#Films", "#Séries", "#ActuCiné", "#SortiesCiné",
        "#FilmFrançais", "#SeriesFrançaises", "#ActualitéCinéma",
        "#FansDeCinéma", "#CinéNews", "#CultureCiné", "#Streaming",
        "#BoxOffice", "#FilmDuJour", "#SerieDuJour",
    ),
    comment_variants=(
        "💬 Qu’en pensez-vous ?", "🗣️ Partagez votre avis en commentaire",
        "👇 Votre réaction nous intéresse", "🎬 Dites-nous ce que vous en pensez",
        "🔥 Vous êtes fan de cette sortie ?", "📢 Débattons-en !",
        "🤔 Bonne ou mauvaise nouvelle selon vous ?", "💭 Votre analyse ici",
        "📝 Partagez votre opinion", "🙌 On attend vos réactions",
    ),
    keyword_weights={
        "première": 10, "sortie": 10, "box-office": 8, "critique": 8,
        "série": 7, "film": 7, "festival": 12, "oscar": 15,
        "cannes": 15, "acteur": 6, "réalisateur": 6, "cinéma": 5,
    },
)


if __name__ == "__main__":
    run_cli(CONFIG)
