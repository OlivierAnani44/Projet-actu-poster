"""Outil optionnel pour créer puis épingler le message partenaire."""

from telegram import Bot


PINNED_TEXT = """
🎁 <b>BONUS OFFICIEL – 1xBet</b>

💰 Bookmaker partenaire : <b>1xBet</b>
🎁 Code promo : <b>XPVIP</b>

👉 Pariez ici :
https://refpa58144.com/L?tag=d_5133758m_4129c_&amp;site=5133758&amp;ad=4129

⚠️ Jouez responsablement (18+)
""".strip()


async def pin_message(bot: Bot, channel_id: str) -> None:
    message = await bot.send_message(
        chat_id=channel_id,
        text=PINNED_TEXT,
        parse_mode="HTML",
    )
    await bot.pin_chat_message(
        chat_id=channel_id,
        message_id=message.message_id,
        disable_notification=True,
    )

