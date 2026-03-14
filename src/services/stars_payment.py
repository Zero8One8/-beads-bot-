"""
Модуль для работы с Telegram Stars.
"""
import logging
from typing import Optional
from datetime import datetime

from aiogram import Bot
from aiogram.types import LabeledPrice, PreCheckoutQuery

from src.database.db import db

logger = logging.getLogger(__name__)

class StarsPayment:
    """
    Обработка платежей через Telegram Stars.
    """
    
    STARS_TO_RUB = 1.0  # 1 Star = 1 рубль (примерно)
    
    @staticmethod
    def rub_to_stars(rub_amount: float) -> int:
        """Конвертировать рубли в Stars."""
        return max(1, int(rub_amount / StarsPayment.STARS_TO_RUB))
    
    @staticmethod
    async def create_invoice(
        bot: Bot,
        user_id: int,
        title: str,
        description: str,
        payload: str,
        amount_rub: float,
        photo_url: Optional[str] = None
    ) -> bool:
        """
        Создать счет на оплату Stars.
        """
        stars_amount = StarsPayment.rub_to_stars(amount_rub)
        
        prices = [LabeledPrice(label=title, amount=stars_amount)]
        
        try:
            await bot.send_invoice(
                chat_id=user_id,
                title=title,
                description=description,
                payload=payload,
                provider_token="",
                currency="XTR",
                prices=prices,
                photo_url=photo_url,
                photo_size=512,
                photo_width=512,
                photo_height=512,
                need_name=False,
                need_email=False,
                need_phone_number=False,
                need_shipping_address=False,
                is_flexible=False
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка создания счета Stars: {e}")
            return False
    
    @staticmethod
    async def process_pre_checkout(pre_checkout: PreCheckoutQuery) -> bool:
        """
        Проверить данные перед оплатой.
        """
        return True
    
    @staticmethod
    async def save_stars_order(
        user_id: int,
        order_id: int,
        charge_id: str,
        stars_amount: int,
        item_name: str
    ) -> bool:
        """
        Сохранить информацию о платеже Stars.
        """
        with db.cursor() as c:
            c.execute("""
                INSERT INTO stars_orders 
                    (user_id, order_id, item_name, stars_amount, charge_id, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'paid', ?)
            """, (user_id, order_id, item_name, stars_amount, charge_id, datetime.now()))
            return True