"""Actualités football — point d'entrée compatible GitHub Actions."""

from news_publisher import FeedConfig, run_cli


CONFIG = FeedConfig(
    name="football",
    rss_feed="https://www.footmercato.net/flux-rss",
    state_file=".state/football.json",
    bot_token_env="FOOTBALL_BOT_TOKEN",
    channels_env="FOOTBALL_CHANNEL_ID",
    legacy_channels_env="FOOTBALL_CHANNELS",
    translate_content=False,
    ensure_image=True,
    image_label="ACTU FOOT",
    emoji="🔥🔥",
    title_variants=(
        "NOUVELLE FOOT", "INFO FOOT", "ACTUALITÉ FOOT", "FLASH FOOT",
        "DERNIÈRE MINUTE FOOT", "ACTU FOOTBALL", "FOOT À LA UNE",
        "LE POINT FOOT", "INFO MATCH", "RÉSUMÉ FOOT", "FOOT AUJOURD’HUI",
        "ACTU MATCH", "FOOT AFRICAIN", "AFCON ACTUALITÉ", "FOOT INTERNATIONAL",
        "LE FAIT DU JOUR FOOT", "ACTUALITÉ SPORT FOOT", "FLASH MATCH",
        "FOOT EN DIRECT", "FOOT : L’ESSENTIEL",
    ),
    hashtag_variants=(
        "#Football", "#Foot", "#ActuFoot", "#InfoFoot", "#FootActu",
        "#FootballAfricain", "#Afcon", "#FootInternational", "#MatchDeFoot",
        "#FootAujourdHui", "#PassionFoot", "#FansDeFoot", "#ActualiteSportive",
        "#FootNews", "#FootAfrique", "#FootDuJour", "#ResumeFoot",
        "#MondeDuFoot", "#FootLive", "#CultureFoot",
    ),
    comment_variants=(
        "💬 Qu’en pensez-vous ?", "🗣️ Donnez votre avis en commentaire",
        "👇 Votre réaction nous intéresse", "⚽ Dites-nous ce que vous en pensez",
        "🔥 Êtes-vous d’accord avec cette info ?", "📢 Débattons-en dans les commentaires",
        "🤔 Bonne ou mauvaise nouvelle selon vous ?", "💭 Votre analyse en commentaire",
        "📝 Partagez votre opinion", "🙌 On attend vos réactions",
        "👀 Votre point de vue compte", "⚽ Fans de foot, à vous la parole",
    ),
    keyword_weights={
        "goal": 10, "but": 10, "score": 8, "victoire": 8, "défaite": 8,
        "titre": 7, "championnat": 6, "afcon": 12, "afrique": 10,
        "international": 8, "match important": 12, "résultat": 7,
    },
)


if __name__ == "__main__":
    run_cli(CONFIG)
