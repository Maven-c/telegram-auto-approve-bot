import os
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, AIORateLimiter,
    CommandHandler, CallbackQueryHandler, ChatJoinRequestHandler, MessageHandler, filters
)

# === ENV ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID_ENV = os.getenv("CHANNEL_ID")
IQ_LINK = os.getenv("IQ_LINK")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "supersecret")
PUBLIC_URL = os.getenv("PUBLIC_URL")

if not BOT_TOKEN or not CHANNEL_ID_ENV or not IQ_LINK:
    raise RuntimeError("Missing BOT_TOKEN / CHANNEL_ID / IQ_LINK")

CHANNEL_ID = int(CHANNEL_ID_ENV)

# === APPs ===
app = FastAPI()
application: Application = (
    Application.builder()
    .token(BOT_TOKEN)
    .rate_limiter(AIORateLimiter())
    .build()
)

# -------- Handlers --------
async def start(update: Update, context):
    user = update.effective_user
    payload = (update.message.text.split(" ", 1)[1] if update.message and " " in update.message.text else "ad1")

    # final tracked link (your base link + campaign tags)
    tracked_link = f"{IQ_LINK}adtrack={payload}&utm_source=telegram&utm_campaign={payload}"

    kb = [
        [InlineKeyboardButton("🔐 Join Private Channel", url=f"https://t.me/+{abs(CHANNEL_ID)}")],
        [InlineKeyboardButton("🧾 Create IQ Option Account", url=tracked_link)],
        [InlineKeyboardButton("✅ I’ve Deposited", callback_data="deposited")],
    ]
    await update.message.reply_text(
        f"Hey {user.first_name} 👋\n\n"
        "Follow these steps:\n"
        "1) Tap *Join Private Channel* (request → gets auto-approved).\n"
        "2) Create your account and deposit.\n"
        "3) Tap *I’ve Deposited* and send proof.\n",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def on_join_request(update: Update, context):
    """
    Auto-approve the join request, then DM the user.
    Requirements:
    - Bot is ADMIN in the channel with 'Add members / Manage join requests'
    - Channel has 'Join by request' enabled
    """
    req = update.chat_join_request    # PTB v20 object
    user_id = req.from_user.id
    chat_id = req.chat.id

    try:
        # Approve
        await context.bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)

        # DM welcome (works if user pressed /start previously)
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "You're in ✅\n\n"
                "Next:\n"
                "• Create your IQ Option account and deposit\n"
                "• Then reply here with *DONE* and a screenshot.\n"
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        # Log but don’t crash
        print(f"Auto-approve failed: {e}")

async def on_callback(update: Update, context):
    q = update.callback_query
    await q.answer()
    if q.data == "deposited":
        await q.edit_message_text("Great! Please *reply* to this chat with your deposit screenshot.", parse_mode="Markdown")

async def on_image_or_doc(update: Update, context):
    # naive proof capture
    await update.message.reply_text("Got it ✅ Our team will review and activate you shortly.")

# Register handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(ChatJoinRequestHandler(on_join_request))
application.add_handler(CallbackQueryHandler(on_callback))
application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, on_image_or_doc))

# -------- FastAPI endpoints --------
@app.get("/")
async def health():
    return {"ok": True}

@app.post(f"/webhook/{{secret}}")
async def telegram_webhook(secret: str, request: Request):
    # simple shared-secret check
    if secret != WEBHOOK_SECRET:
        return {"ok": False, "error": "bad secret"}

    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}
