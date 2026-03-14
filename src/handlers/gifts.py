"""
Подарочные сертификаты.
"""
import logging
import random
import string
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta

from src.database.db import db
from src.database.models import GiftModel, UserModel
from src.services.stars_payment import StarsPayment
from src.utils.helpers import format_price

logger = logging.getLogger(__name__)
router = Router()


class GiftStates(StatesGroup):
    waiting_amount = State()
    waiting_recipient = State()
    waiting_message = State()
    waiting_code = State()


@router.callback_query(F.data == "gifts")
async def gifts_menu(callback: CallbackQuery):
    """Меню подарочных сертификатов."""
    text = (
        "🎁 *ПОДАРОЧНЫЕ СЕРТИФИКАТЫ*\n\n"
        "Подарите близким возможность выбрать свой камень!\n\n"
        "• Номинал от 500 до 50000⭐\n"
        "• Срок действия 1 год\n"
        "• Активация в боте по коду\n\n"
        "Выберите действие:"
    )
    
    buttons = [
        [InlineKeyboardButton(text="🎁 КУПИТЬ СЕРТИФИКАТ", callback_data="gift_buy")],
        [InlineKeyboardButton(text="🎫 АКТИВИРОВАТЬ СЕРТИФИКАТ", callback_data="gift_activate")],
        [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "gift_buy")
async def gift_buy(callback: CallbackQuery, state: FSMContext):
    """Покупка сертификата."""
    await state.set_state(GiftStates.waiting_amount)
    await callback.message.edit_text(
        "🎁 *ПОКУПКА СЕРТИФИКАТА*\n\n"
        "Введите номинал сертификата в Telegram Stars (от 500 до 50000):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="gifts")]
        ])
    )
    await callback.answer()


@router.message(GiftStates.waiting_amount)
async def gift_amount_received(message: Message, state: FSMContext, bot: Bot):
    try:
        amount = int(message.text)
        if amount < 500 or amount > 50000:
            raise ValueError
    except:
        await message.answer("❌ Введите число от 500 до 50000")
        return
    
    await state.update_data(amount=amount)
    await state.set_state(GiftStates.waiting_recipient)
    
    await message.answer(
        "Введите имя получателя (как его назвать в сертификате):"
    )


@router.message(GiftStates.waiting_recipient)
async def gift_recipient_received(message: Message, state: FSMContext):
    recipient = message.text
    await state.update_data(recipient=recipient)
    await state.set_state(GiftStates.waiting_message)
    
    await message.answer(
        "Введите поздравительное сообщение (или отправьте /skip):"
    )


@router.message(GiftStates.waiting_message)
async def gift_message_received(message: Message, state: FSMContext, bot: Bot):
    if message.text == "/skip":
        msg_text = ""
    else:
        msg_text = message.text
    
    data = await state.get_data()
    amount = data['amount']
    recipient = data['recipient']
    
    await StarsPayment.create_invoice(
        bot=bot,
        user_id=message.from_user.id,
        title=f"Подарочный сертификат на {amount}⭐",
        description=f"Для {recipient}",
        payload=f"gift_{amount}_{recipient}_{message.from_user.id}",
        amount_rub=amount
    )
    
    await state.update_data(gift_message=msg_text)
    await state.set_state("waiting_gift_payment")


@router.message(F.successful_payment)
async def gift_payment_success(message: Message, state: FSMContext):
    """Обработка успешной оплаты сертификата."""
    payment = message.successful_payment
    payload = payment.invoice_payload
    
    if payload.startswith("gift_"):
        _, amount, recipient, buyer_id_str = payload.split("_", 3)
        amount = int(amount)
        buyer_id = int(buyer_id_str)
        
        if buyer_id != message.from_user.id:
            return
        
        data = await state.get_data()
        gift_message = data.get('gift_message', '')
        
        # Генерируем код
        code = GiftModel.generate_code()
        
        # Сохраняем в БД
        expires_at = datetime.now() + timedelta(days=365)
        with db.cursor() as c:
            c.execute("""
                INSERT INTO gift_certificates 
                    (code, amount, buyer_id, recipient_name, message, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (code, amount, buyer_id, recipient, gift_message, datetime.now(), expires_at))
        
        await state.clear()
        
        # Отправляем код покупателю
        await message.answer(
            f"✅ *СЕРТИФИКАТ СОЗДАН!*\n\n"
            f"Код: `{code}`\n"
            f"Номинал: {amount}⭐\n"
            f"Получатель: {recipient}\n\n"
            f"Перешлите этот код получателю. "
            f"Сертификат действителен 1 год.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")]
            ])
        )


@router.callback_query(F.data == "gift_activate")
async def gift_activate(callback: CallbackQuery, state: FSMContext):
    """Активация сертификата по коду."""
    await state.set_state(GiftStates.waiting_code)
    await callback.message.edit_text(
        "🎫 *АКТИВАЦИЯ СЕРТИФИКАТА*\n\n"
        "Введите код сертификата:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="gifts")]
        ])
    )
    await callback.answer()


@router.message(GiftStates.waiting_code)
async def gift_code_received(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    
    amount = GiftModel.apply(code, message.from_user.id)
    
    if amount:
        await state.clear()
        await message.answer(
            f"✅ *СЕРТИФИКАТ АКТИВИРОВАН!*\n\n"
            f"На ваш бонусный счёт зачислено {amount}⭐\n"
            f"Их можно использовать при оплате заказов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 ПЕРЕЙТИ В МАГАЗИН", callback_data="showcase")],
                [InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")]
            ])
        )
    else:
        await message.answer(
            "❌ Недействительный или уже использованный код.\n"
            "Проверьте код и попробуйте снова."
        )