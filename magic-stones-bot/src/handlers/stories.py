"""
Истории клиентов - отзывы и личные истории.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime

from src.database.db import db
from src.database.models import StoryModel, UserModel
from src.config import Config

logger = logging.getLogger(__name__)
router = Router()


class StoryStates(StatesGroup):
    waiting_text = State()
    waiting_photo = State()


@router.callback_query(F.data == "stories")
async def stories_list(callback: CallbackQuery):
    """Показать одобренные истории."""
    stories = StoryModel.get_approved(limit=5)
    
    if not stories:
        await callback.message.edit_text(
            "📖 *ИСТОРИИ КЛИЕНТОВ*\n\n"
            "Пока нет историй. Будьте первым, кто поделится!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✏️ НАПИСАТЬ ИСТОРИЮ", callback_data="story_create")],
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await callback.answer()
        return
    
    # Отправляем каждую историю отдельным сообщением
    for story in stories:
        text = f"📖 *История от {story['first_name']}*\n\n{story['story_text']}"
        if story['photo_file_id']:
            await callback.message.answer_photo(
                photo=story['photo_file_id'],
                caption=text,
                parse_mode="Markdown"
            )
        else:
            await callback.message.answer(text, parse_mode="Markdown")
    
    await callback.message.answer(
        "Хотите поделиться своей историей?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ НАПИСАТЬ ИСТОРИЮ", callback_data="story_create")],
            [InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "story_create")
async def story_create(callback: CallbackQuery, state: FSMContext):
    """Написать историю."""
    await state.set_state(StoryStates.waiting_text)
    await callback.message.edit_text(
        "📝 *НАПИШИТЕ ВАШУ ИСТОРИЮ*\n\n"
        "Поделитесь своим опытом: как камни помогли вам, что изменилось в жизни.\n\n"
        "Расскажите подробно, это вдохновит других!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="stories")]
        ])
    )
    await callback.answer()


@router.message(StoryStates.waiting_text)
async def story_text_received(message: Message, state: FSMContext):
    """Текст истории получен."""
    await state.update_data(story_text=message.text)
    await state.set_state(StoryStates.waiting_photo)
    
    await message.answer(
        "📸 Хотите добавить фото? Отправьте его сейчас, или /skip"
    )


@router.message(StoryStates.waiting_photo)
async def story_photo_received(message: Message, state: FSMContext, bot: Bot):
    """Фото получено или пропущено."""
    data = await state.get_data()
    story_text = data['story_text']
    user_id = message.from_user.id
    
    if message.photo:
        photo_id = message.photo[-1].file_id
    else:
        photo_id = None
    
    # Сохраняем историю
    story_id = StoryModel.create(user_id, story_text, photo_id)
    
    await state.clear()
    await message.answer(
        "✅ *ИСТОРИЯ ОТПРАВЛЕНА НА МОДЕРАЦИЮ!*\n\n"
        "После проверки она появится в общем доступе.\n"
        "Спасибо, что делитесь!"
    )
    
    # Уведомление админу
    user = UserModel.get(user_id)
    name = user['first_name'] or user['username'] or str(user_id)
    
    admin_text = (
        f"📖 *НОВАЯ ИСТОРИЯ НА МОДЕРАЦИЮ #{story_id}*\n\n"
        f"👤 *Автор:* {name} (@{user['username']})\n"
        f"🆔 *ID:* {user_id}\n\n"
        f"{story_text}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ОДОБРИТЬ", callback_data=f"story_approve_{story_id}"),
         InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"story_reject_{story_id}")],
        [InlineKeyboardButton(text="✍️ Написать автору", url=f"tg://user?id={user_id}")]
    ])
    
    await bot.send_message(Config.ADMIN_ID, admin_text, reply_markup=kb)
    if photo_id:
        await bot.send_photo(Config.ADMIN_ID, photo_id)


@router.callback_query(F.data.startswith("story_approve_"))
async def story_approve(callback: CallbackQuery, bot: Bot):
    """Админ одобряет историю."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    story_id = int(callback.data.replace("story_approve_", ""))
    StoryModel.approve(story_id)
    
    await callback.message.edit_text("✅ История одобрена и опубликована.")
    await callback.answer()


@router.callback_query(F.data.startswith("story_reject_"))
async def story_reject(callback: CallbackQuery):
    """Админ отклоняет историю."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    story_id = int(callback.data.replace("story_reject_", ""))
    StoryModel.reject(story_id)
    
    await callback.message.edit_text("❌ История отклонена и удалена.")
    await callback.answer()