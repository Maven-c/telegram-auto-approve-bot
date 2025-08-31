import os
from fastapi import FastAPI, Request, HTTPException
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ChatJoinRequestHandler, MessageHandler, filters, AIORateLimiter
)

# ── ENV ───────────────────────────────────────────────────────────
BOT_TOKEN      = os.getenv("BOT_TOKEN")       # from @BotFather
CHANNEL_ID_ENV = os.getenv("CHANNEL_ID")      # numeric: -100xxxxxxxxxx
IQ_LINK        = os.getenv("IQ_LINK")         # your affiliate link (no UTM)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "supersecret")
PUBLIC_URL     = os.getenv("PUBLIC_URL")      # set after first deploy

if not BOT_TOKEN or not CHANNEL_ID_ENV or not IQ_LINK:
    raise RuntimeError("Missing BOT_TOKEN / CHANNEL_ID / IQ_LINK")

CHANNEL_ID = int(CHANNEL_ID_ENV)

# ── APP + PTB ─────────────────────────────────────────────────────
app = FastAPI()
application = Application.builder().token(BOT_TOKEN).rate_limiter(AIORateLimiter()).build()

# simple memory for v1 (OK for 10k). you can swap to DB later.
started_users = set()

# ── Handlers ──────────────────────────────────────────────────────
async def start_cmd(update: Update, context):
    payload = "direct"
    if update.message and update.message.text:
        parts = update.message.text.split(maxsplit=1)
        if len(parts) == 2:
            payload = parts[1]

    user_id = update.effective_user.id
    started_users.add(user_id)

    # create Join-by-Request link for this campaign (payload)
    link = await context.bot.create_chat_invite_link(
        chat_id=CHANNEL_ID,
        creates_join_request=True,
        name=payload
    )

    text = (
        f"Welcome, {update.effective_user.first_name}! 🚀\n\n"
        "Access our private signals (free for a limited time).\n"
        "Follow these 3 steps:\n"
        "1) Create your trading account\n"
        "2) Deposit at least $20\n"
        "3) Tap Join — I’ll auto-approve you instantly"
    )

    keyboard = [
        [InlineKeyboardButton("🔗 Create IQ Option Account", url=f"{IQ_LINK}?utm_source=telegram&utm_campaign={payload}")],
        [InlineKeyboardButton("✅ Join Private Channel", url=link.invite_link)],
        [InlineKeyboardButton("I’ve Deposited ✅", callback_data=f"deposited:{payload}")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def join_request(update: Update, context):
    req = update.chat_join_request
    user_id = req.from_user.id

    # auto-approve (bot must have "Approve join requests" in channel)
    await context.bot.approve_chat_join_request(chat_id=CHANNEL_ID, user_id=user_id)

    # DM welcome if they pressed /start before
    if user_id in started_users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="You're in ✅\n\nCheck the pinned post.\nFinish signup & deposit so you can follow every trade.\nReply DONE when finished."
            )
        except:
            pass

async def deposited_cb(update: Update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "Great! 🎉 Please upload a screenshot of your deposit here.\n"
        "We’ll verify and unlock extras for you."
    )

async def handle_proof(update: Update, context):
    await update.message.reply_text("Got it ✅ We’ll review and confirm shortly.")

# ── FastAPI <-> PTB wiring ────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(ChatJoinRequestHandler(join_request))
    application.add_handler(CallbackQueryHandler(deposited_cb, pattern=r"^deposited:"))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_proof))

    await application.initialize()
    await application.start()

    # auto-set webhook after first deploy when PUBLIC_URL is set
    if PUBLIC_URL:
        url = f"{PUBLIC_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
        await application.bot.set_webhook(url)

@app.on_event("shutdown")
async def on_shutdown():
    await application.stop()
    await application.shutdown()

@app.get("/")
async def health():
    return {"ok": True}

@app.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}
