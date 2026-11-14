import os
import asyncio
import logging
from html import escape
from typing import Optional

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, filters,
)
from telegram.error import TelegramError

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("post-maker")

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ALLOWED_USERS = {
    int(x.strip()) for x in os.getenv("ALLOWED_USERS", "").split(",")
    if x.strip().isdigit()
}

WAIT_TEXT, WAIT_MEDIA, WAIT_BUTTON_TEXT, WAIT_BUTTON_URL, WAIT_TARGET, WAIT_CONFIRM = range(6)

HOME = InlineKeyboardMarkup([
    [InlineKeyboardButton("➕ Create post", callback_data="new")],
    [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
])


def allowed(update: Update) -> bool:
    if not ALLOWED_USERS:
        return True
    user = update.effective_user
    return bool(user and user.id in ALLOWED_USERS)


async def guard(update: Update) -> bool:
    if not allowed(update):
        if update.effective_message:
            await update.effective_message.reply_text("⛔ You are not allowed to use this bot.")
        elif update.callback_query:
            await update.callback_query.answer("Not allowed.", show_alert=True)
        return False
    return True


def draft(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.setdefault("draft", {
        "text": "", "media": None, "buttons": [], "target": None,
    })


def editor_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Set / edit text", callback_data="text")],
        [InlineKeyboardButton("🖼 Add media", callback_data="media"),
         InlineKeyboardButton("🗑 Remove media", callback_data="nomedia")],
        [InlineKeyboardButton("🔗 Add URL button", callback_data="addbutton"),
         InlineKeyboardButton("🧹 Clear buttons", callback_data="clearbuttons")],
        [InlineKeyboardButton("👀 Preview", callback_data="preview")],
        [InlineKeyboardButton("📢 Publish", callback_data="publish")],
        [InlineKeyboardButton("❌ Cancel draft", callback_data="cancel")],
    ])


def format_button_rows(rows: list) -> Optional[InlineKeyboardMarkup]:
    if not rows:
        return None
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(b["text"], url=b["url"]) for b in row]
        for row in rows
    ])


def preview_caption(d: dict) -> str:
    content = d.get("text") or ""
    if not content and not d.get("media"):
        return "*(No text or media yet.)*"
    return content or " "


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "👋 Welcome to Post Maker!\n\nCreate formatted text/media posts, add URL buttons, "
        "preview them, then publish to a group or channel where I am an administrator.",
        reply_markup=HOME,
    )
    return ConversationHandler.END


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    await update.effective_message.reply_text(
        "How to use:\n"
        "1. Tap Create post.\n"
        "2. Set your post text. Telegram HTML is supported: <b>bold</b>, "
        "<i>italic</i>, <u>underline</u>, <s>strike</s>, <code>code</code>, "
        '<a href="https://example.com">links</a>.\n'
        "3. Optionally add one photo, video, or document.\n"
        "4. Add URL buttons. Each button is placed on its own row.\n"
        "5. Preview, choose a destination chat ID, and publish.\n\n"
        "Add the bot to the destination chat first. For a public channel, use @channelusername; "
        "for private chats/groups, use a numeric chat ID.",
        parse_mode=ParseMode.HTML,
    )


async def begin_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not await guard(update):
        return ConversationHandler.END
    context.user_data["draft"] = {"text": "", "media": None, "buttons": [], "target": None}
    await q.edit_message_text("📝 Your new post is ready. Choose an action:", reply_markup=editor_keyboard())
    return WAIT_TEXT


async def menu_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not await guard(update):
        return ConversationHandler.END
    d = draft(context)
    action = q.data

    if action == "text":
        await q.message.reply_text(
            "Send your post text now. HTML formatting is supported.\n"
            "Example: <b>Big news!</b>\n\nSend /skip to leave text empty.",
            parse_mode=ParseMode.HTML,
        )
        return WAIT_TEXT
    if action == "media":
        await q.message.reply_text("Send one photo, video, or document. Send /skip to cancel media.")
        return WAIT_MEDIA
    if action == "nomedia":
        d["media"] = None
        await q.edit_message_text("Media removed.", reply_markup=editor_keyboard())
        return WAIT_TEXT
    if action == "addbutton":
        await q.message.reply_text("Send the button label (for example: Join our channel).")
        return WAIT_BUTTON_TEXT
    if action == "clearbuttons":
        d["buttons"] = []
        await q.edit_message_text("All URL buttons cleared.", reply_markup=editor_keyboard())
        return WAIT_TEXT
    if action == "preview":
        await send_preview(q.message, d)
        await q.message.reply_text("Post editor:", reply_markup=editor_keyboard())
        return WAIT_TEXT
    if action == "publish":
        if not d.get("text") and not d.get("media"):
            await q.message.reply_text("Add text or media before publishing.")
            return WAIT_TEXT
        await q.message.reply_text("Send the destination chat ID or @publicchannelusername.")
        return WAIT_TARGET
    if action == "cancel":
        context.user_data.pop("draft", None)
        await q.edit_message_text("Draft cancelled. Send /start to create another.")
        return ConversationHandler.END
    return WAIT_TEXT


async def set_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    message = update.effective_message
    if message.text == "/skip":
        draft(context)["text"] = ""
    else:
        draft(context)["text"] = message.text_html
    await message.reply_text("Text saved.", reply_markup=editor_keyboard())
    return WAIT_TEXT


async def set_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    msg = update.effective_message
    d = draft(context)
    if msg.text == "/skip":
        d["media"] = None
    elif msg.photo:
        d["media"] = {"type": "photo", "file_id": msg.photo[-1].file_id}
    elif msg.video:
        d["media"] = {"type": "video", "file_id": msg.video.file_id}
    elif msg.document:
        d["media"] = {"type": "document", "file_id": msg.document.file_id}
    else:
        await msg.reply_text("Please send a photo, video, or document, or /skip.")
        return WAIT_MEDIA
    await msg.reply_text("Media saved.", reply_markup=editor_keyboard())
    return WAIT_TEXT


async def set_button_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    label = (update.effective_message.text or "").strip()
    if not label or len(label) > 64:
        await update.effective_message.reply_text("Button text must be 1–64 characters. Try again.")
        return WAIT_BUTTON_TEXT
    context.user_data["pending_button_text"] = label
    await update.effective_message.reply_text("Now send the full URL, including https://")
    return WAIT_BUTTON_URL


async def set_button_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    url = (update.effective_message.text or "").strip()
    if not (url.startswith("https://") or url.startswith("http://")):
        await update.effective_message.reply_text("URL must start with https:// or http://. Try again.")
        return WAIT_BUTTON_URL
    label = context.user_data.pop("pending_button_text", "Open")
    d = draft(context)
    d["buttons"].append([{"text": label, "url": url}])
    await update.effective_message.reply_text(
        f"Button added: {label}\nEach new button is placed on a separate row.",
        reply_markup=editor_keyboard(),
    )
    return WAIT_TEXT


async def send_preview(message, d: dict):
    markup = format_button_rows(d.get("buttons", []))
    media = d.get("media")
    text = preview_caption(d)
    try:
        if media:
            typ, fid = media["type"], media["file_id"]
            if typ == "photo":
                await message.reply_photo(fid, caption=text, parse_mode=ParseMode.HTML, reply_markup=markup)
            elif typ == "video":
                await message.reply_video(fid, caption=text, parse_mode=ParseMode.HTML, reply_markup=markup)
            else:
                await message.reply_document(fid, caption=text, parse_mode=ParseMode.HTML, reply_markup=markup)
        else:
            await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except TelegramError as exc:
        await message.reply_text(f"Preview failed. Check your HTML formatting.\n\nDetails: {exc}")


async def set_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    target = (update.effective_message.text or "").strip()
    if not target:
        await update.effective_message.reply_text("Please send a chat ID or @username.")
        return WAIT_TARGET
    draft(context)["target"] = target
    await update.effective_message.reply_text(
        f"Destination: <code>{escape(target)}</code>\n"
        "Send /confirm to publish or /back to return to the editor.",
        parse_mode=ParseMode.HTML,
    )
    return WAIT_CONFIRM


async def confirm_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    d = draft(context)
    target = d.get("target")
    if not target:
        await update.effective_message.reply_text("No destination set. Start again with /start.")
        return ConversationHandler.END
    markup = format_button_rows(d.get("buttons", []))
    text = d.get("text") or ""
    media = d.get("media")
    try:
        if media:
            typ, fid = media["type"], media["file_id"]
            if typ == "photo":
                await context.bot.send_photo(target, fid, caption=text or None, parse_mode=ParseMode.HTML, reply_markup=markup)
            elif typ == "video":
                await context.bot.send_video(target, fid, caption=text or None, parse_mode=ParseMode.HTML, reply_markup=markup)
            else:
                await context.bot.send_document(target, fid, caption=text or None, parse_mode=ParseMode.HTML, reply_markup=markup)
        else:
            await context.bot.send_message(target, text, parse_mode=ParseMode.HTML, reply_markup=markup)
        await update.effective_message.reply_text("✅ Post published successfully!")
        context.user_data.pop("draft", None)
        return ConversationHandler.END
    except TelegramError as exc:
        log.exception("Publishing failed")
        await update.effective_message.reply_text(
            "❌ Telegram could not publish the post.\n"
            f"Reason: {exc}\n\n"
            "Check that the bot is in the destination chat and has permission to post."
        )
        return WAIT_CONFIRM


async def back_to_editor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    await update.effective_message.reply_text("Back to editor:", reply_markup=editor_keyboard())
    return WAIT_TEXT


async def skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    await update.effective_message.reply_text("Skipped.", reply_markup=editor_keyboard())
    return WAIT_TEXT


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message:
        await update.effective_message.reply_text("Cancelled.", reply_markup=ReplyKeyboardRemove())
    context.user_data.pop("draft", None)
    return ConversationHandler.END


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message:
        await update.effective_message.reply_text("Use the buttons in the post editor, or /start.")


def main():
    if not TOKEN:
        raise SystemExit("BOT_TOKEN is missing. Set it as an environment variable before starting.")
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(begin_new, pattern="^new$")],
        states={
            WAIT_TEXT: [
                CallbackQueryHandler(menu_action, pattern="^(text|media|nomedia|addbutton|clearbuttons|preview|publish|cancel)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_text),
                CommandHandler("skip", skip),
            ],
            WAIT_MEDIA: [
                MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, set_media),
                CommandHandler("skip", set_media),
            ],
            WAIT_BUTTON_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_button_text)],
            WAIT_BUTTON_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_button_url)],
            WAIT_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_target)],
            WAIT_CONFIRM: [
                CommandHandler("confirm", confirm_publish),
                CommandHandler("back", back_to_editor),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        allow_reentry=True,
        per_user=True,
        per_chat=True,
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    log.info("Post Maker bot is running...")
    # Python 3.14 no longer creates a default event loop automatically.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
