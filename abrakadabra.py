
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
    return (text or "").strip().casefold() == "абракадабра"


def _is_privileged(member) -> bool:
    return member.status in (
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    )


async def _restore_permissions(
    bot,
    chat_id: int,
    user_id: int,
    permissions: ChatPermissions,
) -> None:
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=permissions,
        )
        logger.info(
            "Абракадабра: мут снят chat=%s user=%s",
            chat_id, user_id,
        )
    except Exception:
        logger.exception(
            "Абракадабра: ошибка снятия мута chat=%s user=%s",
            chat_id, user_id,
        )


async def _restore_after_delay(
    bot,
    chat_id: int,
    user_id: int,
    permissions: ChatPermissions,
) -> None:
    await asyncio.sleep(MUTE_SECONDS)
    await _restore_permissions(
        bot, chat_id, user_id, permissions
    )


def _get_restore_permissions(chat, member) -> ChatPermissions:
    """Возвращает права, действовавшие до временного мута."""

    # Обычный участник наследует разрешения группы.
    permissions = getattr(chat, "permissions", None)

    if permissions is not None:
        return permissions

    # Без известных исходных прав нельзя безопасно восстановить
    # полный набор разрешений. Используем консервативный вариант.
    logger.warning(
        "Абракадабра: у чата %s отсутствуют permissions",
        chat.id,
    )
    return ChatPermissions(can_send_messages=True)


async def check_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    member=None,
) -> None:
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    try:
        import accounts
        user = accounts.actual_user(update) or message.from_user
    except Exception:
        logger.exception("Абракадабра: ошибка получения реального пользователя")
        user = message.from_user

    if not user or user.is_bot:
        return

    if chat.type not in ("group", "supergroup"):
        return

    if not is_gibberish(message.text or ""):
        return

    started = monotonic()

    try:
        if member is None:
            member = await context.bot.get_chat_member(
                chat_id=chat.id,
                user_id=user.id,
            )

        if _is_privileged(member):
            logger.info(
                "Абракадабра: пропуск администратора chat=%s user=%s",
                chat.id, user.id,
            )
            return

        if member.status in (
            ChatMemberStatus.LEFT,
            ChatMemberStatus.BANNED,
        ):
            logger.info(
                "Абракадабра: пользователь не участник chat=%s user=%s",
                chat.id, user.id,
            )
            return

        if member.status == ChatMemberStatus.RESTRICTED:
            logger.info(
                "Абракадабра: пользователь уже ограничен chat=%s user=%s",
                chat.id, user.id,
            )
            return

        restore_permissions = _get_restore_permissions(chat, member)

        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=user.id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            ),
        )

        if context.job_queue:
            context.job_queue.run_once(
                lambda ctx: _restore_permissions(
                    ctx.bot,
                    chat.id,
                    user.id,
                    restore_permissions,
                ),
                when=MUTE_SECONDS,
                name=f"abrakadabra:{chat.id}:{user.id}",
            )
        else:
            task = asyncio.create_task(
                _restore_after_delay(
                    context.bot,
                    chat.id,
                    user.id,
                    restore_permissions,
                )
            )
            task.add_done_callback(
                lambda t: logger.error(
                    "Абракадабра: задача восстановления завершилась ошибкой",
                    exc_info=t.exception(),
                ) if not t.cancelled() and t.exception() else None
            )

        logger.info(
            "Абракадабра: мут выдан chat=%s user=%s duration=%s elapsed=%.3f",
            chat.id, user.id, MUTE_SECONDS, monotonic() - started,
        )

        await message.reply_text(REPLY_TEXT)

    except Exception:
        logger.exception(
            "Абракадабра: обработка завершилась ошибкой "
            "chat=%s user=%s elapsed=%.3f",
            chat.id, user.id, monotonic() - started,
        )
