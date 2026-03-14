"""
Админ-панель: управление камнями в базе знаний.
"""
import logging
import os
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime

from src.config import Config
from src.database.models import UserModel
from src.utils.text_loader import ContentLoader

logger = logging.getLogger(__name__)
router = Router()


class StoneStates(StatesGroup):
    waiting_stone_id = State()
    waiting_title = State()
    waiting_short_desc = State()
    waiting_full_desc = State()
    waiting_properties = State()
    waiting_emoji = State()
    waiting_zodiac = State()
    waiting_chakra = State()
    waiting_price = State()
    waiting_forms = State()
    waiting_color = State()
    waiting_notes = State()


@router.callback_query(F.data == "admin_stones")
async def admin_stones_list(callback: CallbackQuery):
    """Список камней в базе знаний."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    stones = ContentLoader.load_all_stones()
    
    text = "📚 *УПРАВЛЕНИЕ КАМНЯМИ*\n\n"
    
    if stones:
        text += f"Всего камней: {len(stones)}\n\n"
        buttons = []
        for stone_id in list(stones.keys())[:20]:
            stone_data = stones[stone_id]
            title = stone_data.get('TITLE', stone_id)
            emoji = stone_data.get('EMOJI', '💎')
            buttons.append([
                InlineKeyboardButton(
                    text=f"{emoji} {title}",
                    callback_data=f"admin_stone_view_{stone_id}"
                )
            ])
        buttons.append([
            InlineKeyboardButton(text="➕ ДОБАВИТЬ КАМЕНЬ", callback_data="admin_stone_add"),
            InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_content")
        ])
    else:
        text += "В базе пока нет камней."
        buttons = [
            [InlineKeyboardButton(text="➕ ДОБАВИТЬ КАМЕНЬ", callback_data="admin_stone_add")],
            [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_content")]
        ]
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data == "admin_stone_add")
async def admin_stone_add(callback: CallbackQuery, state: FSMContext):
    """Начало добавления нового камня."""
    await state.set_state(StoneStates.waiting_stone_id)
    await callback.message.edit_text(
        "➕ *ДОБАВЛЕНИЕ НОВОГО КАМНЯ*\n\n"
        "Введите ID камня (латиницей, без пробелов):\n"
        "Например: `ametist` или `rozoviy_kvarts`\n\n"
        "Это будет имя файла.",
        parse_mode="Markdown"
    )
    await callback.answer()


@router.message(StoneStates.waiting_stone_id)
async def stone_id_received(message: Message, state: FSMContext):
    stone_id = message.text.strip().lower()
    
    # Проверка на допустимые символы
    if not stone_id.replace('_', '').isalnum():
        await message.answer("❌ ID должен содержать только буквы, цифры и нижнее подчеркивание. Попробуйте ещё раз:")
        return
    
    # Проверяем, не существует ли уже такой камень
    file_path = Config.KNOWLEDGE_BASE_PATH / f"{stone_id}.txt"
    if file_path.exists():
        await message.answer(f"❌ Камень с ID `{stone_id}` уже существует. Введите другой ID:")
        return
    
    await state.update_data(stone_id=stone_id)
    await state.set_state(StoneStates.waiting_title)
    await message.answer("✏️ Введите название камня (например: `Аметист`):")


@router.message(StoneStates.waiting_title)
async def stone_title_received(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(StoneStates.waiting_emoji)
    await message.answer("😊 Введите эмодзи для камня (например: `💎`):")


@router.message(StoneStates.waiting_emoji)
async def stone_emoji_received(message: Message, state: FSMContext):
    await state.update_data(emoji=message.text)
    await state.set_state(StoneStates.waiting_short_desc)
    await message.answer("📝 Введите краткое описание камня (1-2 предложения):")


@router.message(StoneStates.waiting_short_desc)
async def stone_short_desc_received(message: Message, state: FSMContext):
    await state.update_data(short_desc=message.text)
    await state.set_state(StoneStates.waiting_full_desc)
    await message.answer("📖 Введите полное описание камня (можно несколько абзацев):")


@router.message(StoneStates.waiting_full_desc)
async def stone_full_desc_received(message: Message, state: FSMContext):
    await state.update_data(full_desc=message.text)
    await state.set_state(StoneStates.waiting_properties)
    await message.answer("✨ Введите свойства камня через запятую (например: `Защита, Любовь, Спокойствие`):")


@router.message(StoneStates.waiting_properties)
async def stone_properties_received(message: Message, state: FSMContext):
    await state.update_data(properties=message.text)
    await state.set_state(StoneStates.waiting_zodiac)
    await message.answer("♈ Введите знаки зодиака через запятую (или /skip):")


@router.message(StoneStates.waiting_zodiac)
async def stone_zodiac_received(message: Message, state: FSMContext):
    if message.text == "/skip":
        await state.update_data(zodiac="")
    else:
        await state.update_data(zodiac=message.text)
    await state.set_state(StoneStates.waiting_chakra)
    await message.answer("🌀 Введите чакры через запятую (или /skip):")


@router.message(StoneStates.waiting_chakra)
async def stone_chakra_received(message: Message, state: FSMContext):
    if message.text == "/skip":
        await state.update_data(chakra="")
    else:
        await state.update_data(chakra=message.text)
    await state.set_state(StoneStates.waiting_price)
    await message.answer("💰 Введите цену за бусину (только число, или /skip):")


@router.message(StoneStates.waiting_price)
async def stone_price_received(message: Message, state: FSMContext):
    if message.text == "/skip":
        await state.update_data(price=0)
    else:
        try:
            price = int(message.text)
            await state.update_data(price=price)
        except:
            await message.answer("❌ Введите число или /skip")
            return
    await state.set_state(StoneStates.waiting_forms)
    await message.answer("📏 Введите доступные размеры бусин через запятую (например: `6mm, 8mm, 10mm`, или /skip):")


@router.message(StoneStates.waiting_forms)
async def stone_forms_received(message: Message, state: FSMContext):
    if message.text == "/skip":
        await state.update_data(forms="")
    else:
        await state.update_data(forms=message.text)
    await state.set_state(StoneStates.waiting_color)
    await message.answer("🎨 Введите цвет камня (или /skip):")


@router.message(StoneStates.waiting_color)
async def stone_color_received(message: Message, state: FSMContext):
    if message.text == "/skip":
        await state.update_data(color="")
    else:
        await state.update_data(color=message.text)
    await state.set_state(StoneStates.waiting_notes)
    await message.answer("📝 Введите дополнительные заметки (или /skip):")


@router.message(StoneStates.waiting_notes)
async def stone_notes_received(message: Message, state: FSMContext):
    data = await state.get_data()
    
    if message.text == "/skip":
        notes = ""
    else:
        notes = message.text
    
    # Формируем содержимое файла
    content = f"""[TITLE]
{data.get('title', '')}

[SHORT_DESC]
{data.get('short_desc', '')}

[FULL_DESC]
{data.get('full_desc', '')}

[PROPERTIES]
{data.get('properties', '')}

[ELEMENTS]

[ZODIAC]
{data.get('zodiac', '')}

[CHAKRA]
{data.get('chakra', '')}

[PRICE_PER_BEAD]
{data.get('price', 0)}

[FORMS]
{data.get('forms', '')}

[COLOR]
{data.get('color', '')}

[STONE_ID]
{data.get('stone_id', '')}

[TASKS]

[NOTES]
{notes}
"""
    
    # Сохраняем файл
    stone_id = data['stone_id']
    file_path = Config.KNOWLEDGE_BASE_PATH / f"{stone_id}.txt"
    file_path.write_text(content, encoding='utf-8')
    
    # Очищаем кэш
    ContentLoader.clear_cache()
    
    await state.clear()
    await message.answer(
        f"✅ *Камень успешно создан!*\n\n"
        f"ID: `{stone_id}`\n"
        f"Название: {data.get('title', '')}\n\n"
        f"Файл сохранён в базе знаний.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📚 К СПИСКУ КАМНЕЙ", callback_data="admin_stones")],
            [InlineKeyboardButton(text="➕ ДОБАВИТЬ ЕЩЁ", callback_data="admin_stone_add")]
        ])
    )