"""
Кастомные заказы браслетов - индивидуальный подбор под клиента.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime

from src.database.db import db
from src.database.models import UserModel
from src.config import Config

logger = logging.getLogger(__name__)
router = Router()


class CustomOrderStates(StatesGroup):
    q1_purpose = State()
    q2_stones = State()
    q3_size = State()
    q4_notes = State()
    photo1 = State()
    photo2 = State()


@router.callback_query(F.data == "custom_order")
async def custom_order_start(callback: CallbackQuery, state: FSMContext):
    """Начало кастомного заказа."""
    await state.set_state(CustomOrderStates.q1_purpose)
    await callback.message.edit_text(
        "💍 *ИНДИВИДУАЛЬНЫЙ ЗАКАЗ БРАСЛЕТА*\n\n"
        "Ответьте на несколько вопросов, и мастер подберёт для вас идеальный браслет.\n\n"
        "1/5: Для какой цели вам нужен браслет?\n"
        "(например: защита, привлечение любви, спокойствие, удача в делах)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="menu")]
        ])
    )
    await callback.answer()


@router.message(CustomOrderStates.q1_purpose)
async def custom_order_purpose(message: Message, state: FSMContext):
    await state.update_data(purpose=message.text)
    await state.set_state(CustomOrderStates.q2_stones)
    await message.answer(
        "2/5: Какие камни вам нравятся? Если не знаете, напишите 'не знаю'.\n"
        "(перечислите через запятую или опишите цвета/ощущения)"
    )


@router.message(CustomOrderStates.q2_stones)
async def custom_order_stones(message: Message, state: FSMContext):
    await state.update_data(stones=message.text)
    await state.set_state(CustomOrderStates.q3_size)
    await message.answer(
        "3/5: Какой у вас размер запястья?\n"
        "(можно в сантиметрах или указать 'средний' / 'маленький' / 'большой')"
    )


@router.message(CustomOrderStates.q3_size)
async def custom_order_size(message: Message, state: FSMContext):
    await state.update_data(size=message.text)
    await state.set_state(CustomOrderStates.q4_notes)
    await message.answer(
        "4/5: Есть ли дополнительные пожелания?\n"
        "(стиль, цвет, особые требования) - или отправьте /skip"
    )


@router.message(CustomOrderStates.q4_notes)
async def custom_order_notes(message: Message, state: FSMContext):
    if message.text == "/skip":
        notes = ""
    else:
        notes = message.text
    await state.update_data(notes=notes)
    await state.set_state(CustomOrderStates.photo1)
    
    await message.answer(
        "5/5: Загрузите фото для примера (если есть)\n"
        "Можно загрузить фото браслета, который нравится, или пропустить.\n\n"
        "Отправьте фото или /skip"
    )


@router.message(CustomOrderStates.photo1, F.photo)
async def custom_order_photo1(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo1=photo_id)
    await state.set_state(CustomOrderStates.photo2)
    await message.answer(
        "Можно загрузить ещё одно фото (или /skip)"
    )


@router.message(CustomOrderStates.photo1)
async def custom_order_photo1_skip(message: Message, state: FSMContext):
    if message.text == "/skip":
        await state.update_data(photo1=None)
        await state.set_state(CustomOrderStates.photo2)
        await message.answer(
            "Можно загрузить фото (или /skip)"
        )
    else:
        await message.answer("Пожалуйста, загрузите фото или отправьте /skip")


@router.message(CustomOrderStates.photo2)
async def custom_order_photo2(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    
    if message.photo:
        photo2 = message.photo[-1].file_id
    else:
        photo2 = None
    
    # Сохраняем заказ в БД
    with db.cursor() as c:
        c.execute("""
            INSERT INTO custom_orders 
                (user_id, purpose, stones, size, notes, photo1, photo2, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (message.from_user.id, data['purpose'], data['stones'], data['size'],
              data.get('notes', ''), data.get('photo1'), photo2, datetime.now()))
        order_id = c.lastrowid
    
    await state.clear()
    await message.answer(
        "✅ *ЗАЯВКА ПРИНЯТА!*\n\n"
        "Мастер свяжется с вами в ближайшее время для обсуждения деталей и стоимости."
    )
    
    # Уведомление админу
    user = UserModel.get(message.from_user.id)
    name = user['first_name'] or user['username'] or str(message.from_user.id)
    
    text = (
        f"💍 *НОВЫЙ КАСТОМНЫЙ ЗАКАЗ #{order_id}*\n\n"
        f"👤 *Клиент:* {name} (@{user['username']})\n"
        f"🎯 *Цель:* {data['purpose']}\n"
        f"💎 *Камни:* {data['stones']}\n"
        f"📏 *Размер:* {data['size']}\n"
        f"📝 *Пожелания:* {data.get('notes', 'нет')}\n"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Написать клиенту", url=f"tg://user?id={message.from_user.id}")],
        [InlineKeyboardButton(text="✅ Взять в работу", callback_data=f"custom_take_{order_id}")]
    ])
    
    await bot.send_message(Config.ADMIN_ID, text, reply_markup=kb)
    if data.get('photo1'):
        await bot.send_photo(Config.ADMIN_ID, data['photo1'], caption="📸 Фото 1")
    if photo2:
        await bot.send_photo(Config.ADMIN_ID, photo2, caption="📸 Фото 2")