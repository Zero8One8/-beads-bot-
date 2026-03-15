"""
Админ-панель: управление камнями в базе знаний.
"""
import logging
import os
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

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
    # Редактирование
    editing_field = State()
    editing_value = State()


# ──────────────────────────────────────────────────────────────
# СПИСОК КАМНЕЙ
# ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_stones")
async def admin_stones_list(callback: CallbackQuery):
    """Список камней в базе знаний."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    stones = ContentLoader.load_all_stones()

    text = "📚 *УПРАВЛЕНИЕ КАМНЯМИ*\n\n"

    if stones:
        text += f"Всего камней: *{len(stones)}*\n\nВыберите камень для просмотра/редактирования:"
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

        if len(stones) > 20:
            text += f"\n_(показано 20 из {len(stones)})_"

        buttons.append([
            InlineKeyboardButton(text="➕ ДОБАВИТЬ КАМЕНЬ", callback_data="admin_stone_add")
        ])
        buttons.append([
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


# ──────────────────────────────────────────────────────────────
# ПРОСМОТР КАМНЯ
# ──────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_stone_view_"))
async def admin_stone_view(callback: CallbackQuery):
    """Просмотр конкретного камня."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    stone_id = callback.data.replace("admin_stone_view_", "")
    stone = ContentLoader.load_stone(stone_id)

    if not stone:
        await callback.answer("❌ Камень не найден", show_alert=True)
        return

    emoji = stone.get('EMOJI', '💎')
    title = stone.get('TITLE', stone_id)
    short_desc = stone.get('SHORT_DESC', '—')
    properties = stone.get('PROPERTIES', '—')
    chakra = stone.get('CHAKRA', '—')
    zodiac = stone.get('ZODIAC', '—')
    price = stone.get('PRICE_PER_BEAD', '—')
    color = stone.get('COLOR', '—')
    forms = stone.get('FORMS', '—')

    text = (
        f"{emoji} *{title}*\n\n"
        f"📝 *Краткое описание:* {short_desc}\n\n"
        f"✨ *Свойства:* {properties}\n"
        f"🎨 *Цвет:* {color}\n"
        f"🌀 *Чакры:* {chakra}\n"
        f"♈ *Зодиак:* {zodiac}\n"
        f"💰 *Цена/бусина:* {price} руб.\n"
        f"📏 *Размеры:* {forms}\n\n"
        f"_ID: {stone_id}_"
    )

    buttons = [
        [
            InlineKeyboardButton(text="✏️ РЕДАКТИРОВАТЬ", callback_data=f"admin_stone_edit_{stone_id}"),
            InlineKeyboardButton(text="🗑 УДАЛИТЬ", callback_data=f"admin_stone_delete_{stone_id}")
        ],
        [InlineKeyboardButton(text="🔙 К СПИСКУ", callback_data="admin_stones")]
    ]

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


# ──────────────────────────────────────────────────────────────
# РЕДАКТИРОВАНИЕ КАМНЯ
# ──────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_stone_edit_"))
async def admin_stone_edit_menu(callback: CallbackQuery):
    """Меню редактирования камня."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    stone_id = callback.data.replace("admin_stone_edit_", "")
    stone = ContentLoader.load_stone(stone_id)

    if not stone:
        await callback.answer("❌ Камень не найден", show_alert=True)
        return

    title = stone.get('TITLE', stone_id)
    emoji = stone.get('EMOJI', '💎')

    text = f"✏️ *РЕДАКТИРОВАНИЕ: {emoji} {title}*\n\nВыберите поле для изменения:"

    buttons = [
        [InlineKeyboardButton(text="📝 Название", callback_data=f"admin_stone_field_{stone_id}__TITLE")],
        [InlineKeyboardButton(text="😊 Эмодзи", callback_data=f"admin_stone_field_{stone_id}__EMOJI")],
        [InlineKeyboardButton(text="📋 Краткое описание", callback_data=f"admin_stone_field_{stone_id}__SHORT_DESC")],
        [InlineKeyboardButton(text="📖 Полное описание", callback_data=f"admin_stone_field_{stone_id}__FULL_DESC")],
        [InlineKeyboardButton(text="✨ Свойства", callback_data=f"admin_stone_field_{stone_id}__PROPERTIES")],
        [InlineKeyboardButton(text="🌀 Чакры", callback_data=f"admin_stone_field_{stone_id}__CHAKRA")],
        [InlineKeyboardButton(text="♈ Зодиак", callback_data=f"admin_stone_field_{stone_id}__ZODIAC")],
        [InlineKeyboardButton(text="💰 Цена/бусина", callback_data=f"admin_stone_field_{stone_id}__PRICE_PER_BEAD")],
        [InlineKeyboardButton(text="📏 Размеры", callback_data=f"admin_stone_field_{stone_id}__FORMS")],
        [InlineKeyboardButton(text="🎨 Цвет", callback_data=f"admin_stone_field_{stone_id}__COLOR")],
        [InlineKeyboardButton(text="📝 Заметки", callback_data=f"admin_stone_field_{stone_id}__NOTES")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data=f"admin_stone_view_{stone_id}")]
    ]

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stone_field_"))
async def admin_stone_edit_field(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование конкретного поля."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    # Формат: admin_stone_field_{stone_id}__{FIELD}
    data_str = callback.data.replace("admin_stone_field_", "")
    parts = data_str.split("__")
    if len(parts) < 2:
        await callback.answer("❌ Ошибка формата", show_alert=True)
        return

    stone_id = parts[0]
    field = parts[1]

    stone = ContentLoader.load_stone(stone_id)
    if not stone:
        await callback.answer("❌ Камень не найден", show_alert=True)
        return

    current_value = stone.get(field, '')

    field_names = {
        'TITLE': 'Название',
        'EMOJI': 'Эмодзи',
        'SHORT_DESC': 'Краткое описание',
        'FULL_DESC': 'Полное описание',
        'PROPERTIES': 'Свойства',
        'CHAKRA': 'Чакры',
        'ZODIAC': 'Зодиак',
        'PRICE_PER_BEAD': 'Цена/бусина',
        'FORMS': 'Размеры',
        'COLOR': 'Цвет',
        'NOTES': 'Заметки',
    }

    await state.set_state(StoneStates.editing_value)
    await state.update_data(stone_id=stone_id, field=field)

    await callback.message.edit_text(
        f"✏️ *Редактирование поля «{field_names.get(field, field)}»*\n\n"
        f"Текущее значение:\n_{current_value or 'не задано'}_\n\n"
        f"Введите новое значение:",
        parse_mode="Markdown"
    )
    await callback.answer()


@router.message(StoneStates.editing_value)
async def stone_edit_value_received(message: Message, state: FSMContext):
    """Сохранить новое значение поля."""
    data = await state.get_data()
    stone_id = data.get('stone_id')
    field = data.get('field')

    if not stone_id or not field:
        await message.answer("❌ Ошибка сессии. Начните заново.")
        await state.clear()
        return

    stone = ContentLoader.load_stone(stone_id)
    if not stone:
        await message.answer("❌ Камень не найден")
        await state.clear()
        return

    # Обновляем данные
    stone[field] = message.text.strip()

    # Перезаписываем файл
    _save_stone_file(stone_id, stone)
    ContentLoader.clear_cache()

    await state.clear()
    await message.answer(
        f"✅ *Поле обновлено!*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👁 ПРОСМОТР КАМНЯ", callback_data=f"admin_stone_view_{stone_id}")],
            [InlineKeyboardButton(text="✏️ ПРОДОЛЖИТЬ РЕДАКТИРОВАНИЕ", callback_data=f"admin_stone_edit_{stone_id}")],
            [InlineKeyboardButton(text="📚 К СПИСКУ", callback_data="admin_stones")]
        ])
    )


# ──────────────────────────────────────────────────────────────
# УДАЛЕНИЕ КАМНЯ
# ──────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_stone_delete_"))
async def admin_stone_delete_confirm(callback: CallbackQuery):
    """Подтверждение удаления камня."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    stone_id = callback.data.replace("admin_stone_delete_", "")
    stone = ContentLoader.load_stone(stone_id)

    if not stone:
        await callback.answer("❌ Камень не найден", show_alert=True)
        return

    title = stone.get('TITLE', stone_id)
    emoji = stone.get('EMOJI', '💎')

    await callback.message.edit_text(
        f"⚠️ *УДАЛЕНИЕ КАМНЯ*\n\n"
        f"Вы уверены, что хотите удалить:\n"
        f"{emoji} *{title}* (`{stone_id}`)\n\n"
        f"Это действие нельзя отменить!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ДА, УДАЛИТЬ", callback_data=f"admin_stone_delete_ok_{stone_id}")],
            [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data=f"admin_stone_view_{stone_id}")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stone_delete_ok_"))
async def admin_stone_delete_do(callback: CallbackQuery):
    """Удаление файла камня."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    stone_id = callback.data.replace("admin_stone_delete_ok_", "")
    file_path = Config.KNOWLEDGE_BASE_PATH / f"{stone_id}.txt"

    if file_path.exists():
        file_path.unlink()
        ContentLoader.clear_cache()
        await callback.answer(f"✅ Камень '{stone_id}' удалён", show_alert=True)
    else:
        await callback.answer("❌ Файл не найден", show_alert=True)

    await admin_stones_list(callback)


# ──────────────────────────────────────────────────────────────
# ДОБАВЛЕНИЕ НОВОГО КАМНЯ
# ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_stone_add")
async def admin_stone_add(callback: CallbackQuery, state: FSMContext):
    """Начало добавления нового камня."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

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

    if not stone_id.replace('_', '').isalnum():
        await message.answer("❌ ID должен содержать только буквы, цифры и нижнее подчёркивание:")
        return

    file_path = Config.KNOWLEDGE_BASE_PATH / f"{stone_id}.txt"
    if file_path.exists():
        await message.answer(f"❌ Камень с ID `{stone_id}` уже существует. Введите другой ID:")
        return

    await state.update_data(stone_id=stone_id)
    await state.set_state(StoneStates.waiting_title)
    await message.answer(
        f"✅ ID: `{stone_id}`\n\n✏️ Введите название камня (например: `Аметист`):",
        parse_mode="Markdown"
    )


@router.message(StoneStates.waiting_title)
async def stone_title_received(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(StoneStates.waiting_emoji)
    await message.answer("😊 Введите эмодзи для камня (например: `💎`):")


@router.message(StoneStates.waiting_emoji)
async def stone_emoji_received(message: Message, state: FSMContext):
    await state.update_data(emoji=message.text.strip())
    await state.set_state(StoneStates.waiting_short_desc)
    await message.answer("📝 Введите краткое описание камня (1-2 предложения):")


@router.message(StoneStates.waiting_short_desc)
async def stone_short_desc_received(message: Message, state: FSMContext):
    await state.update_data(short_desc=message.text.strip())
    await state.set_state(StoneStates.waiting_full_desc)
    await message.answer("📖 Введите полное описание камня:")


@router.message(StoneStates.waiting_full_desc)
async def stone_full_desc_received(message: Message, state: FSMContext):
    await state.update_data(full_desc=message.text.strip())
    await state.set_state(StoneStates.waiting_properties)
    await message.answer("✨ Введите свойства камня через запятую:\n_Например: Защита, Любовь, Спокойствие_", parse_mode="Markdown")


@router.message(StoneStates.waiting_properties)
async def stone_properties_received(message: Message, state: FSMContext):
    await state.update_data(properties=message.text.strip())
    await state.set_state(StoneStates.waiting_zodiac)
    await message.answer("♈ Введите знаки зодиака через запятую (или /skip):")


@router.message(StoneStates.waiting_zodiac)
async def stone_zodiac_received(message: Message, state: FSMContext):
    await state.update_data(zodiac="" if message.text == "/skip" else message.text.strip())
    await state.set_state(StoneStates.waiting_chakra)
    await message.answer("🌀 Введите чакры через запятую (или /skip):")


@router.message(StoneStates.waiting_chakra)
async def stone_chakra_received(message: Message, state: FSMContext):
    await state.update_data(chakra="" if message.text == "/skip" else message.text.strip())
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
        except ValueError:
            await message.answer("❌ Введите число или /skip:")
            return
    await state.set_state(StoneStates.waiting_forms)
    await message.answer("📏 Введите доступные размеры бусин через запятую\n_Например: 6mm, 8mm, 10mm_\nИли /skip:", parse_mode="Markdown")


@router.message(StoneStates.waiting_forms)
async def stone_forms_received(message: Message, state: FSMContext):
    await state.update_data(forms="" if message.text == "/skip" else message.text.strip())
    await state.set_state(StoneStates.waiting_color)
    await message.answer("🎨 Введите цвет камня (или /skip):")


@router.message(StoneStates.waiting_color)
async def stone_color_received(message: Message, state: FSMContext):
    await state.update_data(color="" if message.text == "/skip" else message.text.strip())
    await state.set_state(StoneStates.waiting_notes)
    await message.answer("📝 Введите дополнительные заметки (или /skip):")


@router.message(StoneStates.waiting_notes)
async def stone_notes_received(message: Message, state: FSMContext):
    data = await state.get_data()
    notes = "" if message.text == "/skip" else message.text.strip()
    stone_id = data['stone_id']

    stone_data = {
        'TITLE': data.get('title', ''),
        'EMOJI': data.get('emoji', '💎'),
        'SHORT_DESC': data.get('short_desc', ''),
        'FULL_DESC': data.get('full_desc', ''),
        'PROPERTIES': data.get('properties', ''),
        'ELEMENTS': '',
        'ZODIAC': data.get('zodiac', ''),
        'CHAKRA': data.get('chakra', ''),
        'PRICE_PER_BEAD': str(data.get('price', 0)),
        'FORMS': data.get('forms', ''),
        'COLOR': data.get('color', ''),
        'STONE_ID': stone_id,
        'TASKS': '',
        'NOTES': notes,
    }

    _save_stone_file(stone_id, stone_data)
    ContentLoader.clear_cache()

    await state.clear()
    await message.answer(
        f"✅ *Камень успешно создан!*\n\n"
        f"ID: `{stone_id}`\n"
        f"Название: {data.get('title', '')}\n\n"
        f"Файл сохранён в базе знаний.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👁 ПРОСМОТРЕТЬ", callback_data=f"admin_stone_view_{stone_id}")],
            [InlineKeyboardButton(text="📚 К СПИСКУ КАМНЕЙ", callback_data="admin_stones")],
            [InlineKeyboardButton(text="➕ ДОБАВИТЬ ЕЩЁ", callback_data="admin_stone_add")]
        ])
    )


# ──────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: СОХРАНЕНИЕ ФАЙЛА КАМНЯ
# ──────────────────────────────────────────────────────────────

def _save_stone_file(stone_id: str, data: dict) -> None:
    """Сохраняет данные камня в файл формата [MARKER]."""
    content = f"""[TITLE]
{data.get('TITLE', '')}

[SHORT_DESC]
{data.get('SHORT_DESC', '')}

[FULL_DESC]
{data.get('FULL_DESC', '')}

[PROPERTIES]
{data.get('PROPERTIES', '')}

[ELEMENTS]
{data.get('ELEMENTS', '')}

[ZODIAC]
{data.get('ZODIAC', '')}

[CHAKRA]
{data.get('CHAKRA', '')}

[PRICE_PER_BEAD]
{data.get('PRICE_PER_BEAD', 0)}

[FORMS]
{data.get('FORMS', '')}

[COLOR]
{data.get('COLOR', '')}

[STONE_ID]
{stone_id}

[TASKS]
{data.get('TASKS', '')}

[NOTES]
{data.get('NOTES', '')}
"""
    file_path = Config.KNOWLEDGE_BASE_PATH / f"{stone_id}.txt"
    file_path.write_text(content, encoding='utf-8')
    logger.info(f"Сохранён файл камня: {file_path}")
