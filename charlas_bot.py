import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# Configurar el registro (para Render)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Token del bot
TOKEN = "8414398447:AAEJDvaNfFXCrzYtolI2Rbti1uk832XnRh8"

# Palabras a vigilar
KEYWORDS = {"kerem", "bürsin", "hulya", "hülya", "asli", "reyhan", "aras"}

# Configuración del límite
MAX_MESSAGES = 50
TIME_WINDOW = timedelta(hours=3)

# Contadores globales
message_log = []


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global message_log

    message_text = update.message.text.lower()

    if any(keyword in message_text for keyword in KEYWORDS):
        now = datetime.utcnow()
        # Agregar mensaje a log
        message_log.append(now)
        # Limpiar mensajes antiguos fuera de la ventana de tiempo
        message_log = [msg_time for msg_time in message_log if now - msg_time <= TIME_WINDOW]

        logger.info(f"Mensaje detectado. Total en ventana: {len(message_log)}")

        # Si ya hay más de 50, borrar el mensaje
        if len(message_log) > MAX_MESSAGES:
            try:
                await update.message.delete()
                logger.info("Mensaje eliminado por exceso de 50 menciones globales.")
            except Exception as e:
                logger.error(f"No se pudo eliminar el mensaje: {e}")


async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Charlas Bot iniciado. Escuchando mensajes...")
    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
