"""
Ежедневная случайная статья УК РФ.

Одна статья на аккаунт бота в каждый календарный день по Москве.
Результат хранится в Turso и не сбрасывается при перезапуске приложения.
"""
import logging
import random
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import db
import accounts

logger = logging.getLogger(__name__)

# Москва постоянно UTC+3. Используем фиксированный часовой пояс,
# чтобы результат не зависел от часового пояса сервера Render.
_MSK = timezone(timedelta(hours=3), name="MSK")

# Большой пул основных номеров статей УК РФ.
# Исключены статьи, которые заведомо утратили силу.
_REPEALED = {"16", "52", "77", "129", "130", "152", "173", "182", "188", "200"}
ARTICLES = [str(number) for number in range(1, 362) if str(number) not in _REPEALED]

CONSULTANT_URL = "https://www.consultant.ru/document/cons_doc_LAW_10699/"


async def init_db() -> None:
    """Создаёт постоянное хранилище ежедневных статей."""
    rs = await db._exec("""
        CREATE TABLE IF NOT EXISTS daily_criminal_articles (
            account_owner_id INTEGER NOT NULL,
            moscow_day TEXT NOT NULL,
            article_number TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (account_owner_id, moscow_day)
        )
    """)
    if getattr(rs, "error", False):
        raise RuntimeError("Не удалось создать таблицу daily_criminal_articles")


async def get_daily_article(account_owner_id: int, day: str | None = None) -> str:
    """
    Возвращает одну статью на аккаунт и день.
    INSERT OR IGNORE защищает от повторной выдачи при двух одновременных запросах.
    """
    day = day or datetime.now(_MSK).date().isoformat()

    existing = await db._exec(
        """SELECT article_number
           FROM daily_criminal_articles
           WHERE account_owner_id = ? AND moscow_day = ?
           LIMIT 1""",
        [int(account_owner_id), day],
    )
    if getattr(existing, "error", False):
        raise RuntimeError("Ошибка чтения ежедневной статьи")
    if existing.rows:
        return str(existing.rows[0][0])

    previous = await db._exec(
        """SELECT article_number
           FROM daily_criminal_articles
           WHERE account_owner_id = ?
           ORDER BY moscow_day DESC
           LIMIT 1""",
        [int(account_owner_id)],
    )
    if getattr(previous, "error", False):
        raise RuntimeError("Ошибка чтения предыдущей статьи")

    previous_article = str(previous.rows[0][0]) if previous.rows else None
    candidates = [a for a in ARTICLES if a != previous_article] or ARTICLES
    selected = random.choice(candidates)

    inserted = await db._exec(
        """INSERT OR IGNORE INTO daily_criminal_articles
           (account_owner_id, moscow_day, article_number)
           VALUES (?, ?, ?)""",
        [int(account_owner_id), day, selected],
    )
    if getattr(inserted, "error", False):
        raise RuntimeError("Ошибка сохранения ежедневной статьи")

    # В случае параллельных запросов читаем победившую запись.
    saved = await db._exec(
        """SELECT article_number
           FROM daily_criminal_articles
           WHERE account_owner_id = ? AND moscow_day = ?
           LIMIT 1""",
        [int(account_owner_id), day],
    )
    if getattr(saved, "error", False) or not saved.rows:
        raise RuntimeError("Не удалось получить сохранённую статью")
    return str(saved.rows[0][0])


async def cmd_my_article(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик фразы «Моя статья»."""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    try:
        # Учитываем привязку нескольких Telegram-сессий к одному аккаунту.
        owner_id = await accounts.data_id_for(int(user.id))
        day = datetime.now(_MSK).date().isoformat()
        article = await get_daily_article(owner_id, day)
    except Exception:
        logger.exception(
            "my_article: не удалось выдать статью user_id=%s",
            getattr(user, "id", None),
        )
        await msg.reply_text("⚠️ Не удалось получить статью. Попробуй ещё раз позже.")
        return

    await msg.reply_text(
        "⚖️ <b>ТВОЯ СТАТЬЯ НА СЕГОДНЯ</b>\n"
        "━━━━━━━━━━━━━━━\n"
        f"📜 <b>Статья {article} УК РФ</b>\n\n"
        "Эта статья закреплена за твоим аккаунтом до 00:00 по Москве.\n"
        "Повторные запросы сегодня будут показывать тот же номер.\n\n"
        f'📖 <a href="{CONSULTANT_URL}">Открыть УК РФ</a>',
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
