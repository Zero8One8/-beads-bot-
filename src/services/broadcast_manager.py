"""
Менеджер рассылок.
Отправка сообщений пользователям с защитой от блокировок.
"""
import asyncio
import logging
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from src.database.db import db
from src.config import Config

logger = logging.getLogger(__name__)

class BroadcastManager:
    """
    Управление массовыми рассылками.
    """
    
    DELAY_BETWEEN_MESSAGES = 0.04  # 40 ms между сообщениями
    
    @staticmethod
    async def get_all_users() -> List[int]:
        """Получить список всех пользователей бота."""
        with db.cursor() as c:
            c.execute("SELECT user_id FROM users")
            return [row['user_id'] for row in c.fetchall()]
    
    @staticmethod
    async def get_active_users(days: int = 30) -> List[int]:
        """Получить активных пользователей (за последние N дней)."""
        with db.cursor() as c:
            c.execute("""
                SELECT DISTINCT user_id FROM funnel_stats 
                WHERE created_at > datetime('now', ?)
            """, (f'-{days} days',))
            return [row['user_id'] for row in c.fetchall()]
    
    @staticmethod
    async def get_subscribed_to_new() -> List[int]:
        """Получить подписанных на новинки."""
        with db.cursor() as c:
            c.execute("SELECT user_id FROM new_item_subscribers")
            return [row['user_id'] for row in c.fetchall()]
    
    @staticmethod
    async def get_users_with_purchase() -> List[int]:
        """Получить пользователей, которые хоть раз что-то купили."""
        with db.cursor() as c:
            c.execute("SELECT DISTINCT user_id FROM orders WHERE status = 'paid'")
            return [row['user_id'] for row in c.fetchall()]
    
    @staticmethod
    async def send_broadcast(
        bot: Bot,
        user_ids: List[int],
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, int]:
        """
        Отправляет сообщение списку пользователей.
        Возвращает статистику: отправлено, ошибок, заблокировали.
        """
        sent = 0
        failed = 0
        blocked = 0
        total = len(user_ids)
        
        for i, user_id in enumerate(user_ids):
            try:
                await bot.send_message(
                    user_id,
                    text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
                sent += 1
            except Exception as e:
                error_str = str(e).lower()
                if "blocked" in error_str or "forbidden" in error_str:
                    blocked += 1
                else:
                    failed += 1
                logger.warning(f"Ошибка отправки пользователю {user_id}: {e}")
            
            if progress_callback and (i + 1) % 10 == 0:
                progress_callback(i + 1, total)
            
            await asyncio.sleep(BroadcastManager.DELAY_BETWEEN_MESSAGES)
        
        BroadcastManager.save_broadcast_stats(text, sent, failed, blocked, total)
        
        return {
            'total': total,
            'sent': sent,
            'failed': failed,
            'blocked': blocked
        }
    
    @staticmethod
    def save_broadcast_stats(text: str, sent: int, failed: int, blocked: int, total: int):
        """Сохраняет информацию о рассылке в БД."""
        with db.cursor() as c:
            c.execute("""
                INSERT INTO broadcasts 
                    (broadcast_text, sent_count, failed_count, blocked_count, total_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (text[:500], sent, failed, blocked, total, datetime.now()))
    
    @staticmethod
    def get_broadcast_history(limit: int = 10) -> List[Dict[str, Any]]:
        """Получить историю рассылок."""
        with db.cursor() as c:
            c.execute("""
                SELECT * FROM broadcasts 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in c.fetchall()]