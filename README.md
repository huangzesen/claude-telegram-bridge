# claude-telegram-bridge

> Born in a bathtub. Deployed to production. No regrets.

Chat with Claude Code from your phone via Telegram — because sometimes your best ideas happen when you're nowhere near a keyboard.

This bot bridges Telegram messages to the `claude` CLI, giving you persistent multi-turn conversations with Claude Code from anywhere. Yes, including the bath. That's literally how this project was built: the author chatted with Claude on Telegram and told it to write, commit, and publish itself. The AI did the coding while the human did the soaking.

## Setup

### Prerequisites

- Python 3.10+
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated (`claude` must be on your PATH)
- A Telegram bot token (see below)
- Your Telegram user ID (see below)

### Create a Telegram Bot

1. Open Telegram and search for [@BotFather](https://t.me/BotFather) — he's the bot that makes bots. Very meta.
2. Send `/newbot`
3. Choose a **name** for your bot (e.g. "My Claude Bridge")
4. Choose a **username** for your bot (must end in `bot`, e.g. `my_claude_bridge_bot`)
5. BotFather will reply with your **bot token** — a string like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`. Save this for later. Guard it like you guard your rubber duck.

### Get Your Telegram User ID

The bot uses a whitelist so random strangers can't run up your API bill. You need your numeric Telegram user ID:

1. Open Telegram and search for [@userinfobot](https://t.me/userinfobot)
2. Send `/start` or any message
3. It will reply with your **user ID** — a number like `123456789`. Save this for later.

To allow multiple users, collect each person's user ID the same way. Or don't. More users = more API costs = fewer bath bombs in the budget.

### Get a Claude API Key

1. Go to the [Anthropic Console](https://console.anthropic.com/)
2. Sign up or log in
3. Navigate to **API Keys** and create a new key
4. Install the Claude CLI: `npm install -g @anthropic-ai/claude-code`
5. Run `claude` once to authenticate with your API key

### Install

```bash
git clone https://github.com/huangzesen/claude-telegram-bridge.git
cd claude-telegram-bridge
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Edit .env with your bot token and Telegram user ID
```

Required settings:
- `TELEGRAM_BOT_TOKEN` — from BotFather
- `ALLOWED_USER_IDS` — comma-separated Telegram user IDs (whitelist)

Optional settings:
- `CLAUDE_MODEL` — `sonnet`, `opus`, or `haiku` (default: CLI default)
- `CLAUDE_WORKING_DIR` — working directory for Claude subprocess
- `CLAUDE_ALLOWED_TOOLS` — restrict tools, e.g. `Read,Grep,Glob`
- `CLAUDE_MAX_BUDGET_USD` — per-invocation spending cap (default: 1.00)
- `CLAUDE_TIMEOUT_SECONDS` — subprocess timeout (default: 300)

### Run

```bash
python bot.py
```

Then go take a bath and code from there. That's the whole point.

## Usage

Open Telegram and send a message to your bot. It forwards the message to `claude` and sends back the response. It's like texting a very smart friend who never judges you for coding in the tub.

### Commands

| Command | Description |
|---------|-------------|
| `/start`, `/help` | Show welcome message and usage |
| `/reset` | Start a fresh conversation (new session) |
| `/model <name>` | Switch Claude model (sonnet/opus/haiku) |
| `/status` | Show current session info |

### How it works

- Each Telegram user gets a persistent Claude session (stored in `sessions.json`)
- Messages are sent to Claude via `claude -p --output-format json`
- First message creates a new session; subsequent messages resume it
- Long responses are automatically split to fit Telegram's 4096 char limit
- A typing indicator shows while Claude is thinking
- Only whitelisted user IDs can use the bot

## Security

- **User whitelist**: Only Telegram user IDs listed in `ALLOWED_USER_IDS` can interact with the bot
- **Tool restrictions**: Optionally limit which tools Claude can use via `CLAUDE_ALLOWED_TOOLS`
- **Budget cap**: Set `CLAUDE_MAX_BUDGET_USD` to limit spending per invocation
- **Timeout**: `CLAUDE_TIMEOUT_SECONDS` prevents runaway processes

## Origin Story

This entire project was built by a human in a bathtub telling Claude what to do via Telegram. Claude wrote the code, committed it to git, created the GitHub repo, and made it public — all while the human stayed warm and pruney. The future is now.
