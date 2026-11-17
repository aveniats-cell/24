"""Автоматический шуточный мут за явную абракадабру."""

import asyncio
import logging
import re
from datetime import timedelta

from telegram import ChatPermissions, Update
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

MUTE_SECONDS = 10
REPLY_TEXT = "Ты что, куку? 🥴 Ну вот тебе мут на 10 сек — наколдовал! 🪄"

# Очевидные случаи бессмысленного набора: длинные цепочки согласных
# или очень длинное слово почти без гласных. Короткие сообщения не трогаем.
_LETTERS_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+")
_VOWELS = set("аеёиоуыэюяaeiouy")
_LONG_CONSONANTS_RE = re.compile(r"(?i)[бвгджзйклмнпрстфхцчшщbcdfghjklmnpqrstvwxz]{6,}")


def is_gibberish(text: str) -> bool:
    """Срабатывает только на отдельное слово «абракадабра», без учёта регистра."""
    return (text or "").strip().casefold() == "абракадабра"


async def _restore_permissions(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    try:
        await context.bot.restrict_chat_member(
            chat_id=data["chat_id"],
            user_id=data["user_id"],
            permissions=data["permissions"],
        )
        logger.info(
            "Абракадабра-мут снят: chat_id=%s user_id=%s",
            data["chat_id"], data["user_id"],
        )
    except TelegramError:
        logger.exception(
            "Не удалось снять абракадабра-мут: chat_id=%s user_id=%s",
            data["chat_id"], data["user_id"],
        )


async def _restore_after_delay(bot, chat_id: int, user_id: int,
                               permissions: ChatPermissions) -> None:
    await asyncio.sleep(MUTE_SECONDS)
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=permissions,
        )
    except TelegramError:
        logger.exception(
            "Не удалось снять абракадабра-мут: chat_id=%s user_id=%s",
            chat_id, user_id,
        )


async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выдаёт короткий мут за сообщение, похожее на случайный набор букв."""
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user or user.is_bot:
        return
    if chat.type not in ("group", "supergroup"):
        return
    if not is_gibberish(message.text or ""):
        return

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        # Не трогаем администраторов, владельца и пользователей,
        # которые уже находятся под ограничением.
        if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER,
                             ChatMemberStatus.RESTRICTED):
            return

        chat_info = await context.bot.get_chat(chat.id)
        restore_permissions = chat_info.permissions or ChatPermissions(
            can_send_messages=True
        )

        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=user.id,
            permissions=ChatPermissions(can_send_messages=False),
        )
        await message.reply_text(REPLY_TEXT)

        if context.job_queue:
            context.job_queue.run_once(
                _restore_permissions,
                when=MUTE_SECONDS,
                data={
                    "chat_id": chat.id,
                    "user_id": user.id,
                    "permissions": restore_permissions,
                },
                name=f"abrakadabra:{chat.id}:{user.id}",
            )
        else:
            asyncio.create_task(
                _restore_after_delay(
                    context.bot, chat.id, user.id, restore_permissions
                )
            )

    except TelegramError as exc:
        logger.warning(
            "Не удалось выдать абракадабра-мут: chat_id=%s user_id=%s error=%s",
            chat.id, user.id, exc,
        )
