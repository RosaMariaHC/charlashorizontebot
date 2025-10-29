import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from telegram import Update
from telegram.constants import ChatType
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# ----------------------------------------------------------------------
# CONFIGURACIÓN
# ----------------------------------------------------------------------

TOKEN = "8414398447:AAEJDvaNfFXCrzYtolI2Rbti1uk832XnRh8"  # Token fijo del bot
MSG_LIMIT = 50  # Límite global total de mensajes por chat
COUNTER_FILE = "counters.json"  # Archivo donde se guardan los contadores
DELETE_DELAY_SEC = 1.0  # Segundos antes de borrar mensaje extra

# Palabras clave a vigilar
KEYWORDS = [
    "kerem", "bursin", "bürsin", "inombrable",
    "hülya", "hulya", "aslı", "asli",
    "reyhan", "aras", "çarpinti", "çarpıntı"
]

# ----------------------------------------------------------------------
# LOGGING
# ----------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("charlas_bot")

_counters = {}
_lock = asyncio.Lock()

# ----------------------------------------------------------------------
# FUNCIONES AUXILIARES
# ----------------------------------------------------------------------

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _load_counters():
    global _counters
    try:
        if os.path.exists(COUNTER_FILE):
            with open(COUNTER_FILE, "r", encoding="utf-8") as f:
                _counters = json.load(f)
                if not isinstance(_counters, dict):
                    _counters = {}
    except Exception as e:
        logger.warning(f"No se pudieron cargar contadores: {e}")
        _counters = {}

def _save_counters():
    try:
        tmp = COUNTER_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_counters, f, ensure_ascii=False, indent=2)
        os.replace(tmp, COUNTER_FILE)
    except Exception as e:
        logger.warning(f"No se pudieron guardar contadores: {e}")

async def _inc_and_get(chat_id: int) -> int:
    async with _lock:
        key = str(chat_id)
        data = _counters.get(key, {"count": 0, "updated_at": _now_iso()})
        data["count"] = int(data.get("count", 0)) + 1
        data["updated_at"] = _now_iso()
        _counters[key] = data
        _save_counters()
        return data["count"]

async def _get_count(chat_id: int) -> int:
    async with _lock:
        return int(_counters.get(str(chat_id), {}).get("count", 0))

async def _reset_counter(chat_id: int):
    async with _lock:
        _counters[str(chat_id)] = {"count": 0, "updated_at": _now_iso()}
        _save_counters()

# ----------------------------------------------------------------------
# HANDLERS
# ----------------------------------------------------------------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Charlas Bot operativo.\n"
        f"• Límite global: {MSG_LIMIT} mensajes.\n"
        "• Si se supera, los mensajes se borran automáticamente.\n"
        "• Palabras vigiladas: " + ", ".join(KEYWORDS)
    )

async def count_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    current = await _get_count(chat_id)
    await update.message.reply_text(f"📊 Total actual: {current}/{MSG_LIMIT}")

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await _reset_counter(chat_id)
    await update.message.reply_text("🔄 Contador reiniciado a 0.")

async def group_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    text = (msg.text or "").lower()

    if msg.from_user and msg.from_user.is_bot:
        return

    if not any(k in text for k in KEYWORDS):
        return

    current = await _inc_and_get(chat.id)

    if current > MSG_LIMIT:
        try:
            await asyncio.sleep(DELETE_DELAY_SEC)
            await context.bot.delete_message(chat.id, msg.message_id)
            logger.info(f"🗑️ Mensaje eliminado (superó {MSG_LIMIT}) en chat {chat.id}")
        except Exception as e:
            logger.warning(f"No se pudo borrar mensaje {msg.message_id}: {e}")

# ----------------------------------------------------------------------
# APP PRINCIPAL
# ----------------------------------------------------------------------

def main():
    _load_counters()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("count", count_cmd))
    app.add_handler(CommandHandler("resetcounter", reset_cmd))

    group_filter = (
        (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)
        & ~filters.StatusUpdate.ALL
    )
    app.add_handler(MessageHandler(group_filter, group_message_handler))

    logger.info("🚀 Charlas Bot iniciado y escuchando mensajes...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)

if __name__ == "__main__":
    main()
