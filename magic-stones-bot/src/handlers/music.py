"""
Музыкальная библиотека - исцеляющие частоты, мантры, медитации.
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

from src.database.db import db
from src.database.models import MusicModel
from src.keyboards.music import get_music_keyboard

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "music")
async def music_list(callback: CallbackQuery):
    """Список музыкальных треков."""
    tracks = MusicModel.get_all()
    
    if not tracks:
        await callback.message.edit_text(
            "🎵 *МУЗЫКАЛЬНАЯ БИБЛИОТЕКА*\n\n"
            "Раздел находится в наполнении. Скоро здесь появятся исцеляющие частоты и мантры.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await callback.answer()
        return
    
    text = "🎵 *МУЗЫКАЛЬНАЯ БИБЛИОТЕКА*\n\n"
    text += "Исцеляющие частоты, мантры, медитации:\n\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_music_keyboard(tracks)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("music_"))
async def music_play(callback: CallbackQuery):
    """Отправка аудиофайла."""
    track_id = int(callback.data.replace("music_", ""))
    
    with db.cursor() as c:
        c.execute("SELECT * FROM music WHERE id = ?", (track_id,))
        track = c.fetchone()
    
    if not track:
        await callback.answer("❌ Трек не найден", show_alert=True)
        return
    
    text = f"*{track['name']}*\n\n{track['description']}"
    
    if track.get('audio_url'):
        # Если есть ссылка на файл
        await callback.message.answer_audio(
            audio=track['audio_url'],
            caption=text,
            parse_mode="Markdown"
        )
    else:
        # Если только текст
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← К СПИСКУ", callback_data="music")]
            ])
        )
    
    await callback.answer()