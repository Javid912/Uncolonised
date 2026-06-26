"""
Uncolonised — Telegram Bot for Curated Submissions

Accepts article submissions from whitelisted contributors.
Stores in the submissions queue for agent review and editorial approval.

Workflow:
    Contributor sends article markdown → stored in submissions table
    → content-reviewer agent reviews → you approve/reject via admin API
    → article becomes a draft post → you publish

Environment:
    TELEGRAM_BOT_TOKEN   — bot token from @BotFather
    DATABASE_URL          — PostgreSQL connection string
    ADMIN_API_KEY         — API key for admin endpoints
    ALLOWED_USER_IDS      — comma-separated Telegram user IDs (whitelist)
    API_BASE_URL          — e.g. http://api:8000
"""

import logging
import os
import sys

import asyncpg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
ALLOWED_USER_IDS_STR = os.getenv("ALLOWED_USER_IDS", "")

ALLOWED_USER_IDS = set()
for uid in ALLOWED_USER_IDS_STR.split(","):
    uid = uid.strip()
    if uid:
        ALLOWED_USER_IDS.add(int(uid))


async def store_submission(pool, user_id: int, username: str, text: str) -> dict:
    lines = text.strip().split("\n", 1)
    title = lines[0].strip().strip("#").strip() or "Untitled"
    body_md = lines[1] if len(lines) > 1 else ""

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO submissions
                (submission_type, title, body_md, author_name,
                 telegram_uid, telegram_username, status)
            VALUES ('post', $1, $2, $3, $4, $5, 'pending')
            RETURNING id, title, status, created_at
            """,
            title,
            body_md,
            username or f"user_{user_id}",
            user_id,
            username,
        )
    return dict(row)


async def main():
    if not TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN is not set.")
        sys.exit(1)
    if not DATABASE_URL:
        log.error("DATABASE_URL is not set.")
        sys.exit(1)

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=4)

    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    async def start(update: Update, _):
        uid = update.effective_user.id
        if uid not in ALLOWED_USER_IDS and ALLOWED_USER_IDS:
            await update.message.reply_text("You are not authorized to use this bot.")
            return
        await update.message.reply_text(
            "Send me your article as a Markdown message.\n"
            "First line = title, rest = body.\n\n"
            "Your submission will be reviewed by our editorial team."
        )

    async def handle_message(update: Update, _):
        uid = update.effective_user.id
        username = update.effective_user.username or ""

        if ALLOWED_USER_IDS and uid not in ALLOWED_USER_IDS:
            await update.message.reply_text("Unauthorized.")
            log.warning("Unauthorized user %s (id=%s) tried to submit.", username, uid)
            return

        text = update.message.text or update.message.caption or ""
        if not text.strip():
            await update.message.reply_text("Message is empty. Send your article.")
            return

        try:
            result = await store_submission(pool, uid, username, text)
            log.info(
                "Submission #%s from @%s: %s",
                result["id"],
                username,
                result["title"],
            )
            await update.message.reply_text(
                f"Received! Your submission *#{result['id']}* has been queued for review.\n\n"
                f"Title: _{result['title']}_",
                parse_mode="Markdown",
            )
        except Exception as e:
            log.exception("Failed to store submission")
            await update.message.reply_text("Something went wrong. Please try again.")

    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    log.info("Bot started. Allowed users: %s", ALLOWED_USER_IDS or "anyone")
    await application.run_polling()

    await pool.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
