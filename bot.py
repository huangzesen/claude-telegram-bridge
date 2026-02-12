#!/usr/bin/env python3
"""Telegram bot that bridges messages to the Claude CLI."""

import asyncio
import json
import logging
import os
import uuid
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_IDS = {
    int(uid.strip())
    for uid in os.getenv("ALLOWED_USER_IDS", "").split(",")
    if uid.strip()
}
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL")  # None = CLI default
CLAUDE_WORKING_DIR = os.getenv("CLAUDE_WORKING_DIR")
CLAUDE_ALLOWED_TOOLS = os.getenv("CLAUDE_ALLOWED_TOOLS")
CLAUDE_MAX_BUDGET_USD = float(os.getenv("CLAUDE_MAX_BUDGET_USD", "1.00"))
CLAUDE_TIMEOUT_SECONDS = int(os.getenv("CLAUDE_TIMEOUT_SECONDS", "300"))

SESSIONS_FILE = Path(__file__).parent / "sessions.json"
MAX_TELEGRAM_MESSAGE_LENGTH = 4096


# ---------------------------------------------------------------------------
# Session manager — maps Telegram user_id to Claude session UUID
# ---------------------------------------------------------------------------


class SessionManager:
    """Persist {user_id: {session_id, model}} in a JSON file."""

    def __init__(self, path: Path = SESSIONS_FILE):
        self._path = path
        self._data: dict[str, dict] = {}
        self._load()

    # -- persistence --

    def _load(self):
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError):
                logger.warning("Corrupt sessions file, starting fresh")
                self._data = {}

    def _save(self):
        self._path.write_text(json.dumps(self._data, indent=2))

    # -- public API --

    def get(self, user_id: int) -> dict | None:
        return self._data.get(str(user_id))

    def ensure(self, user_id: int) -> dict:
        """Return existing session or create a new one."""
        key = str(user_id)
        if key not in self._data:
            self._data[key] = {
                "session_id": str(uuid.uuid4()),
                "model": CLAUDE_MODEL,
                "message_count": 0,
            }
            self._save()
        return self._data[key]

    def reset(self, user_id: int) -> dict:
        """Create a fresh session for the user."""
        key = str(user_id)
        old_model = self._data.get(key, {}).get("model", CLAUDE_MODEL)
        self._data[key] = {
            "session_id": str(uuid.uuid4()),
            "model": old_model,
            "message_count": 0,
        }
        self._save()
        return self._data[key]

    def set_model(self, user_id: int, model: str):
        session = self.ensure(user_id)
        session["model"] = model
        self._save()

    def increment(self, user_id: int):
        session = self.ensure(user_id)
        session["message_count"] = session.get("message_count", 0) + 1
        self._save()


sessions = SessionManager()


# ---------------------------------------------------------------------------
# Claude CLI runner
# ---------------------------------------------------------------------------


class ClaudeRunner:
    """Run the claude CLI as an async subprocess."""

    @staticmethod
    async def run(prompt: str, session: dict) -> dict:
        """Send a prompt to Claude CLI, return parsed JSON response."""
        cmd = ["claude", "-p", "--output-format", "json"]

        # Session: first message uses --session-id, subsequent use --resume
        if session.get("message_count", 0) == 0:
            cmd += ["--session-id", session["session_id"]]
        else:
            cmd += ["--resume", session["session_id"]]

        # Model
        model = session.get("model") or CLAUDE_MODEL
        if model:
            cmd += ["--model", model]

        # Tool restrictions
        if CLAUDE_ALLOWED_TOOLS:
            cmd += ["--allowedTools", CLAUDE_ALLOWED_TOOLS]

        # Budget cap
        cmd += ["--max-turns", "50"]

        # Prompt goes last
        cmd.append(prompt)

        logger.info("Running: %s", " ".join(cmd))

        cwd = CLAUDE_WORKING_DIR or None
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=CLAUDE_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"error": f"Claude timed out after {CLAUDE_TIMEOUT_SECONDS}s"}

        if proc.returncode != 0:
            err = stderr.decode(errors="replace").strip()
            logger.error("Claude CLI error (rc=%d): %s", proc.returncode, err)
            return {"error": f"Claude CLI error: {err or 'unknown error'}"}

        raw = stdout.decode(errors="replace").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # CLI may have printed non-JSON (e.g. a plain text fallback)
            return {"result": raw}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def authorized(func):
    """Decorator: reject users not in ALLOWED_USER_IDS."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in ALLOWED_USER_IDS:
            logger.warning("Unauthorized access from user %d", user_id)
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return
        return await func(update, context)

    return wrapper


def chunk_message(text: str, limit: int = MAX_TELEGRAM_MESSAGE_LENGTH) -> list[str]:
    """Split text into chunks that fit Telegram's message limit.

    Tries to split at paragraph boundaries, then line boundaries,
    then hard-cuts at the limit.
    """
    if len(text) <= limit:
        return [text]

    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break

        # Try to split at a paragraph boundary
        cut = text.rfind("\n\n", 0, limit)
        if cut == -1:
            # Try line boundary
            cut = text.rfind("\n", 0, limit)
        if cut == -1:
            # Try space
            cut = text.rfind(" ", 0, limit)
        if cut == -1:
            # Hard cut
            cut = limit

        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")

    return chunks


def extract_response_text(response: dict) -> str:
    """Pull the text reply out of Claude CLI's JSON output."""
    if "error" in response:
        return f"Error: {response['error']}"

    # --output-format json returns {"result": "...", ...}
    result = response.get("result", "")
    if isinstance(result, str):
        return result

    # Sometimes result is a list of content blocks
    if isinstance(result, list):
        parts = []
        for block in result:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)

    return str(result)


def format_cost(response: dict) -> str:
    """Format cost info if present."""
    cost = response.get("cost_usd")
    if cost is not None:
        return f"\n[cost: ${cost:.4f}]"
    return ""


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


@authorized
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sessions.ensure(update.effective_user.id)
    await update.message.reply_text(
        "Hello! I'm a bridge to Claude Code.\n\n"
        "Send me any message and I'll forward it to Claude.\n\n"
        "Commands:\n"
        "/reset - Start a new conversation\n"
        "/model <name> - Switch model (sonnet/opus/haiku)\n"
        "/status - Show session info\n"
        "/help - Show this message"
    )


@authorized
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


@authorized
async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = sessions.reset(update.effective_user.id)
    await update.message.reply_text(
        f"Session reset. New session ID: {session['session_id'][:8]}..."
    )


@authorized
async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        session = sessions.ensure(update.effective_user.id)
        current = session.get("model") or CLAUDE_MODEL or "default"
        await update.message.reply_text(f"Current model: {current}\nUsage: /model <name>")
        return

    model = context.args[0]
    sessions.set_model(update.effective_user.id, model)
    await update.message.reply_text(f"Model set to: {model}")


@authorized
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = sessions.ensure(update.effective_user.id)
    lines = [
        f"Session ID: {session['session_id'][:8]}...",
        f"Model: {session.get('model') or CLAUDE_MODEL or 'default'}",
        f"Messages: {session.get('message_count', 0)}",
    ]
    if CLAUDE_WORKING_DIR:
        lines.append(f"Working dir: {CLAUDE_WORKING_DIR}")
    if CLAUDE_ALLOWED_TOOLS:
        lines.append(f"Allowed tools: {CLAUDE_ALLOWED_TOOLS}")
    await update.message.reply_text("\n".join(lines))


@authorized
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward user message to Claude CLI and send back the response."""
    user_id = update.effective_user.id
    text = update.message.text
    if not text:
        return

    session = sessions.ensure(user_id)

    # Send typing indicator periodically while waiting
    typing_task = asyncio.create_task(_keep_typing(update))

    try:
        response = await ClaudeRunner.run(text, session)
    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

    sessions.increment(user_id)

    reply = extract_response_text(response)
    cost_info = format_cost(response)

    if not reply:
        reply = "(empty response from Claude)"

    full_reply = reply + cost_info

    for chunk in chunk_message(full_reply):
        await update.message.reply_text(chunk)


async def _keep_typing(update: Update, interval: float = 4.0):
    """Send 'typing' action every few seconds until cancelled."""
    try:
        while True:
            await update.message.chat.send_action("typing")
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set. Copy .env.example to .env and fill it in.")
        return
    if not ALLOWED_USER_IDS:
        print("Error: ALLOWED_USER_IDS not set. Add your Telegram user ID to .env.")
        return

    logger.info("Starting bot with %d allowed user(s)", len(ALLOWED_USER_IDS))
    logger.info("Claude model: %s", CLAUDE_MODEL or "default")
    if CLAUDE_WORKING_DIR:
        logger.info("Working dir: %s", CLAUDE_WORKING_DIR)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
