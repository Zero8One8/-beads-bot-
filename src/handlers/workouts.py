"""
Тренировки и практики - ежедневные упражнения для удержания аудитории.
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from src.database.db import db
from src.database.models import WorkoutModel

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "workouts")
async def workouts_list(callback: CallbackQuery):
    """Список тренировок."""
    workouts = WorkoutModel.get_all()
    
    if not workouts:
        await callback.message.edit_text(
            "🏋️ *ТРЕНИРОВКИ И ПРАКТИКИ*\n\n"
            "Раздел находится в наполнении. Скоро здесь появятся ежедневные упражнения.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await callback.answer()
        return
    
    text = "🏋️ *ТРЕНИРОВКИ И ПРАКТИКИ*\n\n"
    
    buttons = []
    for w in workouts:
        difficulty_emoji = {
            'beginner': '🌱',
            'intermediate': '⭐',
            'advanced': '🔥'
        }.get(w['difficulty'], '•')
        
        text += f"{difficulty_emoji} *{w['name']}* — {w['duration']} мин\n"
        buttons.append([InlineKeyboardButton(
            text=f"{w['name']} ({w['duration']} мин)",
            callback_data=f"workout_{w['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("workout_"))
async def workout_detail(callback: CallbackQuery):
    """Детальная информация о тренировке."""
    workout_id = int(callback.data.replace("workout_", ""))
    
    with db.cursor() as c:
        c.execute("SELECT * FROM workouts WHERE id = ?", (workout_id,))
        workout = c.fetchone()
    
    if not workout:
        await callback.answer("❌ Тренировка не найдена", show_alert=True)
        return
    
    difficulty_emoji = {
        'beginner': '🌱',
        'intermediate': '⭐',
        'advanced': '🔥'
    }.get(workout['difficulty'], '•')
    
    text = (
        f"{difficulty_emoji} *{workout['name']}*\n\n"
        f"⏱️ *Длительность:* {workout['duration']} мин\n"
        f"📊 *Уровень:* {workout['difficulty']}\n\n"
        f"📝 *Описание:*\n{workout['description']}"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← К СПИСКУ", callback_data="workouts")]
        ])
    )
    await callback.answer()