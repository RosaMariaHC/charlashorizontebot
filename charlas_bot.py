# charlas_bot.py
# Bot para "Charlas en HORIZONTE 🌍"
# - Cuenta mensajes con ciertas palabras
# - Al llegar a 50, bloquea ese tema por 3 horas (borra cualquier mensaje con esas palabras)
# - No sanciona ni expulsa a nadie
#
# Requisitos:
#   pip install python-telegram-bot==20.7

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Set

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)
from telegram.error import NetworkError, TimedOut

# === CONFIGURACIÓN ===
TOKEN = "8414398447:AAEJDvaNfFXCrzYtolI2Rbti1uk832XnRh8"  # token de BotFather
KEYWORDS: Set[str] = {"kerem", "bürsin", "bursin", "çarpıntı", "çarpinti", "inombrable"}
THRESHOLD = 50          # cantidad de mensajes antes de bloquear
COOLDOWN_HOURS = 3      # duración del bloqueo (en horas)
ADMINS_ONLY_CMDS = True # limitar /tema_estado y /tema_reset a admins

# === LOGS ===
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("charlas_bot")

# === ESTADO EN MEMORIA ===
chat_state: Dict[int, Dict[str, datetime | int | None]] = {}


def _normalize(text: str) -> str:
    return text.lower()


def _contains_keyword(text: str) -> bool:
    t = _normalize(text)
    return any(k in t for k in KEYWORDS)


def _get_state(chat_id: int) -> Dict[str, datetime | int | None]:
    s = chat_state.get(chat_id)
    if not s:
        s = {"count": 0, "blocked_until": None}
        chat_state[chat_id] = s
    return s


async def _is_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.effective_chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return
    if update.effective_user is None or update.message is None or update.message.text is None:
        return

    chat_id = update.effective_chat.id
    text = update.message.text

    if not _contains_keyword(text):
        return

    state = _get_state(chat_id)
    now = datetime.utcnow()

    blocked_until = state["blocked_until"]
    if isinstance(blocked_until, datetime) and now < blocked_until:
        try:
            await update.message.delete()
            log.info(f"[{chat_id}] Borrado (tema bloqueado hasta {blocked_until}).")
        except Exception as e:
            log.warning(f"[{chat_id}] No se pudo borrar mensaje durante bloqueo: {e}")
        return

    state["count"] = int(state["count"]) + 1
    log.debug(f"[{chat_id}] Conteo: {state['count']}/{THRESHOLD}")

    if state["count"] >= THRESHOLD:
        state["blocked_until"] = now + timedelta(hours=COOLDOWN_HOURS)
        try:
            await update.message.delete()
        except Exception as e:
            log.warning(f"[{chat_id}] No se pudo borrar al alcanzar umbral: {e}")
        log.info(f"[{chat_id}] Umbral {THRESHOLD} alcanzado. Bloqueado por {COOLDOWN_HOURS}h.")
        return


async def cmd_tema_estado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None:
        return
    chat_id = update.effective_chat.id

    if ADMINS_ONLY_CMDS and update.effective_user:
        if not await _is_admin(context, chat_id, update.effective_user.id):
            return

    s = _get_state(chat_id)
    count = int(s["count"])
    blocked_until = s["blocked_until"]
    if isinstance(blocked_until, datetime):
        mins = max(0, int((blocked_until - datetime.utcnow()).total_seconds() // 60))
        msg = f"Estado del tema: BLOQUEADO. Quedan ~{mins} min. Conteo {count}/{THRESHOLD}."
    else:
        msg = f"Estado del tema: ACTIVO. Conteo {count}/{THRESHOLD}. Se bloqueará al llegar al umbral."

    try:
        await update.message.reply_text(msg, quote=False)
    except Exception:
        pass


async def cmd_tema_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None:
        return
    chat_id = update.effective_chat.id

    if ADMINS_ONLY_CMDS and update.effective_user:
        if not await _is_admin(context, chat_id, update.effective_user.id):
            return

    s = _get_state(chat_id)
    s["count"] = 0
    s["blocked_until"] = None
    try:
        await update.message.reply_text("Tema reiniciado: conteo 0 y bloqueo levantado.", quote=False)
    except Exception:
        pass


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat and update.effective_chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return
    await update.message.reply_text("✅ Charlas Bot listo. Añádeme como admin (Eliminar mensajes) y con Group Privacy OFF.")


def build_app() -> Application:
    return Application.builder().token(TOKEN).build()


def run_forever():
    while True:
        try:
            app = build_app()

            app.add_handler(CommandHandler("start", start_cmd))
            app.add_handler(CommandHandler("tema_estado", cmd_tema_estado))
            app.add_handler(CommandHandler("tema_reset", cmd_tema_reset))

            app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

            log.info("Charlas Bot iniciado. Escuchando mensajes...")

            # Corrección: solo una instancia, limpia pendientes
            app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                close_loop=False,
                drop_pending_updates=True
            )

        except (NetworkError, TimedOut) as e:
            log.warning(f"Problema de red: {e}. Reintentando en 10s...")
            time.sleep(10)
        except Exception as e:
            log.exception(f"Fallo inesperado: {e}. Reintentando en 15s...")
            time.sleep(15)


if __name__ == "__main__":
    run_forever()
