# Telegram Post Maker Bot

A Telegram bot for creating and publishing formatted posts to groups and channels.

## Features
- Telegram HTML-formatted text
- Photo, video, and document posts
- Custom URL inline buttons
- Preview before publishing
- Publish to public or private groups/channels
- Optional Telegram user ID allowlist

## Requirements
- Python 3.10+
- A bot token from [@BotFather](https://t.me/BotFather)
- Add the bot to each destination chat. In channels, make it an administrator with permission to post.

## Install (Termux)
```bash
pkg update -y
pkg install python -y
git clone https://github.com/Dk-Hunterx/Dk-postbot.git
cd Dk-postbot
pip install -r requirements.txt
cp .env.example .env
nano .env
```

Set `BOT_TOKEN` in your environment (and optionally `ALLOWED_USERS`, a comma-separated list of numeric Telegram user IDs).

Run:
```bash
export BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
# Optional:
export ALLOWED_USERS="123456789,987654321"
python bot.py
```

## Use
1. Open the bot and send `/start`.
2. Tap **Create post**.
3. Set text, optionally add media, and add URL buttons.
4. Preview the post.
5. Tap **Publish**, enter `@channelusername` or a numeric chat ID.
6. Send `/confirm` to publish. Use `/back` to return to the editor.

Telegram HTML examples: `<b>bold</b>`, `<i>italic</i>`, `<u>underline</u>`, `<code>code</code>`, and `<a href="https://example.com">link</a>`.

## Configuration
- `BOT_TOKEN`: required Telegram bot token.
- `ALLOWED_USERS`: optional comma-separated Telegram user IDs. Leave empty to allow any user.

## Security
- Never commit your real bot token or `.env` file.
- If a token is exposed, revoke it with @BotFather.
- Drafts are kept in memory and are lost when the bot restarts.
- Run only one polling instance for a given bot token.
