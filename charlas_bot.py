# charlas_bot.py — Charlas Horizonte Bot
# Requiere python-telegram-bot==20.3 (ya en requirements.txt)
# TOKEN se toma de la variable de entorno TELEGRAM_TOKEN (Render)

import os
import logging
from collections import deque
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)

# ----------------- Config -----------------
# Palabras clave a vigilar (insensible a mayúsculas)
KEYWORDS = [
    "kerem",
    "hulya", "hülya",
    "asli",
    "reyhan",
    "aras",
]

# Límite global de mensajes que contienen las palabras clave
MAX_MESSAGES = 50

# Ventana de tiempo para el conteo (ajústala si lo necesitas)
# Ahora: 1 hora. Todos los mensajes con keywords en la última hora cuentan.
TIME_WINDOW = timedelta(hours=1)

# ------------------------------------------

# Log legible en Render
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("charlas_bot")

# Cola de marcas de tiempo (mensajes válidos dentro de la ventana)
message_log: deque[datetime] = deque()


def _prune_old():
    """Elimina del log los mensajes fuera de la ventana temporal."""
    cutoff = datetime.now(timezone.utc) - TIME_WINDOW
    while message_log and message_log[0] < cutoff:
        message_log.popleft()


def _has_keyword(text: str) -> bool:
    """Devuelve True si el texto contiene alguna keyword (case-insensitive)."""
    if not text:
        return False
    low = text.lower()
    return any(k in low for k in KEYWORDS)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja CUALQUIER mensaje de texto en el chat.
    Si contiene una keyword, lo cuenta en el global.
    A partir del 51 dentro de la ventana, lo borra inmediatamente.
    """
    msg = update.effective_message
    if not msg:
        return

    # Solo operamos en grupos/supergrupos
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        return

    text = msg.text or msg.caption or ""
    if not _has_keyword(text):
        return

    # Mantenimiento del log
    _prune_old()

    # ¿Ya alcanzamos el límite global?
    if len(message_log) >= MAX_MESSAGES:
        # Intentar borrar el mensaje que rebasa el límite
        try:
            await msg.delete()
            logger.info("Mensaje eliminado por exceder el límite global de %s.", MAX_MESSAGES)
        except Exception as e:
            logger.error("No pude eliminar el mensaje que supera el límite: %s", e)
        return

    # Aún dentro del cupo: registrar el mensaje
    message_log.append(datetime.now(timezone.utc))
    logger.info("Keyword detectada. Total en ventana: %s", len(message_log))


# ---- Comandos útiles (opcionales) ----
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "✅ Charlas Bot listo. Asegúrame permisos para *eliminar mensajes* y "
        "mantén *Privacy Mode* en OFF.",
        parse_mode="Markdown",
    )


async def cmd_contador(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _prune_old()
    await update.effective_message.reply_text(
        f"🧮 Contador global (últimas {int(TIME_WINDOW.total_seconds() // 60)} min): "
        f"{len(message_log)}/{MAX_MESSAGES}"
    )


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vacía manualmente el contador (por si lo necesitas)."""
    message_log.clear()
    await update.effective_message.reply_text("🔁 Contador global reiniciado.")


def main() -> None:
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("Falta la variable de entorno TELEGRAM_TOKEN")

    app = Application.builder().token(token).build()

    # Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("contador", cmd_contador))
    app.add_handler(CommandHandler("resetcontador", cmd_reset))

    # Cualquier mensaje de texto (no comandos)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Charlas Bot iniciado. Escuchando mensajes…")
    # Importante: versión sin asyncio.run() para evitar el error del event loop
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
