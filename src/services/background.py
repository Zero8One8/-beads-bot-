"""
Фоновые задачи.
"""
import asyncio
import logging
from datetime import datetime, timedelta

from src.database.db import db
from src.database.models import OrderModel, ClubModel
from src.services.notifications import AdminNotifier
from src.config import Config

logger = logging.getLogger(__name__)


async def check_pending_orders():
    """Проверка неоплаченных заказов (отмена через 24 часа)."""
    while True:
        try:
            await asyncio.sleep(3600)  # каждый час
            
            with db.cursor() as c:
                c.execute("""
                    SELECT id, user_id FROM orders
                    WHERE status = 'pending'
                    AND created_at < datetime('now', '-24 hours')
                """)
                old_orders = c.fetchall()
                
                for order in old_orders:
                    c.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order['id'],))
                    logger.info(f"Заказ #{order['id']} отменён (не оплачен 24ч)")
                    
        except Exception as e:
            logger.error(f"Ошибка в check_pending_orders: {e}")


async def check_birthdays():
    """Проверка дней рождений и отправка промокодов."""
    while True:
        try:
            await asyncio.sleep(3600)
            
            today = datetime.now().strftime('%m-%d')
            with db.cursor() as c:
                c.execute("""
                    SELECT user_id, first_name FROM users
                    WHERE birthday IS NOT NULL
                    AND strftime('%m-%d', birthday) = ?
                """, (today,))
                birthday_users = c.fetchall()
                
                for user in birthday_users:
                    c.execute("""
                        SELECT 1 FROM birthday_promos
                        WHERE user_id = ? AND date = date('now')
                    """, (user['user_id'],))
                    if c.fetchone():
                        continue
                    
                    promo_code = f"BDAY{user['user_id']}{datetime.now().strftime('%d%m')}"
                    
                    c.execute("""
                        INSERT INTO promocodes (code, discount_pct, max_uses, created_at)
                        VALUES (?, 15, 1, ?)
                    """, (promo_code, datetime.now()))
                    
                    c.execute("""
                        INSERT INTO birthday_promos (user_id, promo_code, date)
                        VALUES (?, ?, date('now'))
                    """, (user['user_id'], promo_code))
                    
                    logger.info(f"Создан birthday-промокод {promo_code} для {user['user_id']}")
                    
        except Exception as e:
            logger.error(f"Ошибка в check_birthdays: {e}")


async def check_expired_subscriptions():
    """Проверка истекших подписок клуба."""
    while True:
        try:
            await asyncio.sleep(3600)
            ClubModel.expire_subscriptions()
            logger.info("Проверка истекших подписок выполнена")
        except Exception as e:
            logger.error(f"Ошибка в check_expired_subscriptions: {e}")
