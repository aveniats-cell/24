"""Автоматический шуточный мут за точное слово «абракадабра»."""

import asyncio
import logging
from time import monotonic

from telegram import ChatPermissions, Update
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

MUTE_SECONDS = 10
REPLY_TEXT = "Ты что, куку? 🥴 Ну вот тебе мут на 10 сек — наколдовала! 🪄"


def is_gibberish(text: str) -> bool:
    """Только отдельное слово «абракадабра», без учёта регистра."""
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


async def _restore_after_delay(
    bot, chat_id: int, user_id: int, permissions: ChatPermissions
) -> None:
    await asyncio.sleep(MUTE_SECONDS)
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=permissions,
        )
        logger.info(
            "Абракадабра-мут снят: chat_id=%s user_id=%s",
            chat_id, user_id,
        )
    except TelegramError:
        logger.exception(
            "Не удалось снять абракадабра-мут: chat_id=%s user_id=%s",
            chat_id, user_id,
        )


async def check_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Быстро ограничивает отправителя точного слова на 10 секунд."""
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user or user.is_bot:
        return
    if chat.type not in ("group", "supergroup"):
        return
    if not is_gibberish(message.text or ""):
        return

    started = monotonic()
    try:
        # Единственный обязательный запрос до мута: проверяем, что это не админ.
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
            ChatMemberStatus.RESTRICTED,
        ):
            logger.info(
                "Абракадабра пропущена: статус=%s chat_id=%s user_id=%s",
                member.status, chat.id, user.id,
            )
            return

        # В объекте чата из Update обычно уже есть стандартные права.
        # get_chat вызываем только если Telegram не прислал их в Update.
        restore_permissions = chat.permissions
        if restore_permissions is None:
            chat_info = await context.bot.get_chat(chat.id)
            restore_permissions = chat_info.permissions or ChatPermissions(
                can_send_messages=True
            )

        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=user.id,
            permissions=ChatPermissions(can_send_messages=False),
        )

        # Сразу планируем снятие мута, чтобы оно не зависело от отправки ответа.
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

        logger.info(
            "Абракадабра-мут выдан: chat_id=%s user_id=%s elapsed=%.2fs",
            chat.id, user.id, monotonic() - started,
        )

        # Ответ отправляется сразу после успешной выдачи мута.
        try:
            await message.reply_text(REPLY_TEXT)
        except TelegramError:
            logger.exception(
                "Мут выдан, но ответ не отправлен: chat_id=%s user_id=%s",
                chat.id, user.id,
            )

    except TelegramError:
        logger.exception(
            "Не удалось обработать абракадабру: chat_id=%s user_id=%s elapsed=%.2fs",
            chat.id, user.id, monotonic() - started,
        )
