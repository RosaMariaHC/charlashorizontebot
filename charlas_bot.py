import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# --------------------------- Configuración ---------------------------

# TOKEN desde entorno (Render: TELEGRAM_TOKEN)
TOKEN = os.getenv("TELEGRAM_TOKEN")  # O fija aquí: TOKEN = "8414398447:AAEJDvaNfFXCrzYtolI2Rbti1uk832XnRh8"

# Límite global por chat (default 50)
MSG_LIMIT = int(os.getenv("MSG_LIMIT", "50"))

# Ventana de reinicio automático (en horas)
MSG_WINDOW_HOURS = float(os.getenv("MSG_WINDOW_HOURS", "3"))

# Archivo donde se guarda el contador global
COUNTER_FILE = os.getenv("COUNTER_FILE", "counters.json")

# Retraso antes de borrar mensajes que superan el límite
DELETE_DELAY_SEC = float(os.getenv("DELETE_DELAY_SEC", "1"))

# Palabras clave a vigilar
KEYWORDS = [
    "kerem",
    "bursin", "bürsin",
    "inombrable",
    "hülya", "hulya",
    "aslı", "asli",
    "reyhan",
    "aras",
    "çarpinti", "çarpıntı"
]

# --------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("charlas_bot")

_counters = {}
_lock = asyncio.Lock()


# ------------------------ Funciones auxiliares -----------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _now_iso() -> str:
    return _now_utc().isoformat()

def _load_counters():
    global _counters
    try:
        if os.path.exists(COUNTER_FILE):
            with open(COUNTER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _counters = data if isinstance(data, dict) else {}
        else:
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

def _needs_reset(updated_at_iso: str) -> bool:
    try:
        last = datetime.fromisoformat(updated_at_iso)
    except Exception:
        return True
    return _now_utc() - last >= timedelta(hours=MSG_WINDOW_HOURS)

async def _inc_and_get(chat_id: int) -> int:
    async with _lock:
        key = str(chat_id)
        data = _counters.get(key, {"count": 0, "updated_at": _now_iso()})

        if _needs_reset(data.get("updated_at", _now_iso())):
            data["count"] = 0

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

async def _check_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Verifica si el usuario es administrador o si el chat es privado."""
    try:
        # En chat privado (chat_id > 0), el usuario siempre es "admin" para el bot
        if chat_id > 0:
            return True
        
        # En grupos/supergrupos, verificar el estado
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ("creator", "administrator")
    except Exception as e:
        logger.error(f"Error al verificar admin: {e}")
        return False

def _text_of(update: Update) -> str:
    msg = update.effective_message
    return (msg.text or msg.caption or "").lower() if msg else ""

def _matches_keyword(text: str) -> bool:
    if not text:
        return False
    return any(k in text for k in KEYWORDS)


# ----------------------------- Handlers ------------------------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Charlas Bot operativo.\n"
        f"• Contador global (ventana {MSG_WINDOW_HOURS:g} h)\n"
        f"• Límite: {MSG_LIMIT} mensajes con palabras clave.\n"
        "• Luego se borran automáticamente."
    )

async def count_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Usamos la nueva función asíncrona para la verificación de administrador
    if not await _check_admin(chat_id, user_id, context):
        return
        
    current = await _get_count(chat_id)
    await update.message.reply_text(f"📊 Mensajes con keywords: {current}/{MSG_LIMIT}")

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Usamos la nueva función asíncrona para la verificación de administrador
    if not await _check_admin(chat_id, user_id, context):
        return
        
    await _reset_counter(chat_id)
    await update.message.reply_text("🔄 Contador reiniciado.")

async def group_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat

    if not msg or not chat:
        return
    if msg.from_user and msg.from_user.is_bot:
        return
    # Asegura que solo funcione en grupos/supergrupos
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    text = _text_of(update)
    if not _matches_keyword(text):
        return

    current = await _inc_and_get(chat.id)

    if current > MSG_LIMIT:
        try:
            # Es importante que el bot tenga permisos de administrador para borrar
            await asyncio.sleep(DELETE_DELAY_SEC)
            await context.bot.delete_message(chat_id=chat.id, message_id=msg.message_id)
            logger.info(f"🗑️ Borrado (chat {chat.id}, count={current}).")
        except Exception as e:
            # Esto puede fallar si el bot no es admin
            logger.warning(f"No se pudo borrar mensaje: {e}")
    else:
        logger.info(f"Keyword detectada. Count={current}/{MSG_LIMIT}.")


# ------------------------------ App ---------------------------------

# Cambiado de "async def main()" a "def main()" para evitar el error del bucle de eventos
def main():
    if not TOKEN:
        # Se detiene si no hay token de Telegram
        raise RuntimeError("Falta la variable de entorno TELEGRAM_TOKEN.")

    _load_counters()

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("count", count_cmd))
    application.add_handler(CommandHandler("resetcounter", reset_cmd))

    group_filter = (
        (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)
        & ~filters.StatusUpdate.ALL
    )
    application.add_handler(MessageHandler(group_filter, group_message_handler))

    logger.info("🤖 Charlas Bot escuchando mensajes...")
    
    # USAMOS run_polling() SIN ASYNCIO.RUN() EXTERNO PARA RESOLVER EL ERROR EN RENDER.
    # Eliminamos parámetros como close_loop=False, stop_signals=None
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
    )

if __name__ == "__main__":
    # La ejecución síncrona llama a la función principal síncrona
    main()
