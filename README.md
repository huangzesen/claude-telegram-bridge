# claude-telegram-bridge

Chat with Claude Code from your phone via Telegram.

This bot bridges Telegram messages to the `claude` CLI, giving you persistent multi-turn conversations with Claude Code from anywhere.

## Setup

### Prerequisites

- Python 3.10+
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated (`claude` must be on your PATH)
- A Telegram bot token (create one via [@BotFather](https://t.me/BotFather))
- Your Telegram user ID (get it from [@userinfobot](https://t.me/userinfobot))

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

## Usage

Open Telegram and send a message to your bot. It forwards the message to `claude` and sends back the response.

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
