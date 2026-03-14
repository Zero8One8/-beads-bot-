"""
Менеджер уведомлений для администратора.
"""
import logging
from typing import Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.config import Config
from src.database.db import db
from src.database.models import UserModel, OrderModel
from src.utils.helpers import format_price, format_datetime

logger = logging.getLogger(__name__)

class AdminNotifier:
    """Отправка уведомлений админу о событиях в боте."""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.admin_id = Config.ADMIN_ID
    
    async def send(self, text: str, keyboard: Optional[InlineKeyboardMarkup] = None, photo: Optional[str] = None):
        """Отправить сообщение админу."""
        if not self.admin_id:
            logger.warning("ADMIN_ID не задан, уведомление не отправлено")
            return
        
        try:
            if photo:
                await self.bot.send_photo(self.admin_id, photo, caption=text, reply_markup=keyboard)
            else:
                await self.bot.send_message(self.admin_id, text, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления админу: {e}")
    
    async def new_order(self, order_id: int):
        """Уведомление о новом заказе."""
        order = OrderModel.get_by_id(order_id)
        if not order:
            return
        
        user = UserModel.get(order['user_id'])
        name = user['first_name'] or user['username'] or f"ID{order['user_id']}"
        
        items = OrderModel.get_items(order_id)
        items_text = "\n".join([
            f"• {it['item_name']} x{it['quantity']} = {format_price(it['price'] * it['quantity'])}"
            for it in items
        ]) or "—"
        
        text = (
            f"🛒 *НОВЫЙ ЗАКАЗ #{order_id}*\n\n"
            f"👤 *Клиент:* {name} (@{user['username']})\n"
            f"🆔 *ID:* {order['user_id']}\n"
            f"💰 *Сумма:* {format_price(order['total_price'])}\n"
            f"💳 *Метод:* {order['payment_method']}\n"
            f"🎟️ *Промокод:* {order['promo_code'] or '—'}\n\n"
            f"📦 *Состав:*\n{items_text}"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 Перейти к заказу", callback_data=f"order_view_{order_id}")],
            [InlineKeyboardButton(text="✍️ Написать клиенту", url=f"tg://user?id={order['user_id']}")]
        ])
        
        await self.send(text, kb)
    
    async def new_user(self, user_id: int, referred_by: Optional[int] = None):
        """Уведомление о новом пользователе."""
        user = UserModel.get(user_id)
        name = user['first_name'] or user['username'] or f"ID{user_id}"
        
        text = (
            f"👋 *НОВЫЙ ПОЛЬЗОВАТЕЛЬ*\n\n"
            f"👤 *Имя:* {name}\n"
            f"🆔 *ID:* {user_id}\n"
            f"📅 *Дата:* {format_datetime(user['created_at'])}\n"
        )
        if referred_by:
            ref_user = UserModel.get(referred_by)
            ref_name = ref_user['first_name'] if ref_user else str(referred_by)
            text += f"👥 *Пригласил:* {ref_name} (ID: {referred_by})"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Написать", url=f"tg://user?id={user_id}")]
        ])
        
        await self.send(text, kb)
    
    async def new_booking(self, consult_id: int):
        """Уведомление о новой записи на услугу."""
        from src.database.models import ConsultationModel, ServiceModel, ScheduleModel
        
        with db.cursor() as c:
            c.execute("""
                SELECT c.*, u.first_name, u.username, s.name as service_name, s.price, sl.slot_date, sl.time_slot
                FROM consultations c
                JOIN users u ON c.user_id = u.user_id
                JOIN services s ON c.service_id = s.id
                JOIN schedule_slots sl ON c.slot_id = sl.id
                WHERE c.id = ?
            """, (consult_id,))
            consult = c.fetchone()
        
        if not consult:
            return
        
        name = consult['first_name'] or consult['username'] or f"ID{consult['user_id']}"
        
        text = (
            f"📅 *НОВАЯ ЗАПИСЬ НА УСЛУГУ*\n\n"
            f"👤 *Клиент:* {name} (@{consult['username']})\n"
            f"🆔 *ID:* {consult['user_id']}\n"
            f"✨ *Услуга:* {consult['service_name']}\n"
            f"💰 *Стоимость:* {format_price(consult['price'])}\n"
            f"📅 *Дата:* {consult['slot_date']}\n"
            f"⏰ *Время:* {consult['time_slot']}\n"
        )
        if consult['comment']:
            text += f"📝 *Комментарий:* {consult['comment']}"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Написать клиенту", url=f"tg://user?id={consult['user_id']}")]
        ])
        
        await self.send(text, kb)
    
    async def new_story(self, story_id: int, user_id: int, text: str, photo_id: Optional[str] = None):
        """Уведомление о новой истории на модерацию."""
        user = UserModel.get(user_id)
        name = user['first_name'] or user['username'] or f"ID{user_id}"
        
        msg_text = (
            f"📖 *НОВАЯ ИСТОРИЯ НА МОДЕРАЦИЮ*\n\n"
            f"👤 *Автор:* {name} (@{user['username']})\n"
            f"🆔 *ID:* {user_id}\n\n"
            f"{text}"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin_story_approve_{story_id}"),
             InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_story_reject_{story_id}")]
        ])
        
        await self.send(msg_text, kb, photo=photo_id)