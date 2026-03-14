"""
Админ-панель: управление товарами (категории, браслеты, витрина).
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime

from src.database.db import db
from src.database.models import UserModel, CategoryModel, BraceletModel, ShowcaseCollectionModel, ShowcaseItemModel
from src.utils.helpers import format_price

logger = logging.getLogger(__name__)
router = Router()


class AdminProductStates(StatesGroup):
    # Категории
    category_create_name = State()
    category_create_emoji = State()
    category_create_desc = State()
    category_edit = State()
    category_edit_field = State()
    
    # Браслеты
    bracelet_create_name = State()
    bracelet_create_price = State()
    bracelet_create_category = State()
    bracelet_create_desc = State()
    bracelet_create_photo = State()
    bracelet_edit = State()
    bracelet_edit_field = State()
    
    # Коллекции витрины
    collection_create_name = State()
    collection_create_emoji = State()
    collection_create_desc = State()
    
    # Товары витрины
    showcase_create_name = State()
    showcase_create_price = State()
    showcase_create_stars = State()
    showcase_create_collection = State()
    showcase_create_desc = State()
    showcase_create_photo = State()


@router.callback_query(F.data == "admin_products")
async def admin_products(callback: CallbackQuery):
    """Главное меню управления товарами."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    text = (
        "💎 *УПРАВЛЕНИЕ ТОВАРАМИ*\n\n"
        "Выберите раздел:"
    )
    
    buttons = [
        [InlineKeyboardButton(text="📋 КАТЕГОРИИ", callback_data="admin_categories")],
        [InlineKeyboardButton(text="💎 БРАСЛЕТЫ", callback_data="admin_bracelets")],
        [InlineKeyboardButton(text="🖼️ КОЛЛЕКЦИИ ВИТРИНЫ", callback_data="admin_collections")],
        [InlineKeyboardButton(text="📦 ТОВАРЫ ВИТРИНЫ", callback_data="admin_showcase")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


# ======================================================
# КАТЕГОРИИ
# ======================================================

@router.callback_query(F.data == "admin_categories")
async def admin_categories(callback: CallbackQuery):
    """Список категорий."""
    categories = CategoryModel.get_all()
    
    text = f"📋 *КАТЕГОРИИ ТОВАРОВ*\n\nВсего: {len(categories)}\n\n"
    
    buttons = []
    for cat in categories:
        text += f"{cat['emoji']} {cat['name']} (ID: {cat['id']})\n"
        buttons.append([InlineKeyboardButton(
            text=f"✏️ {cat['emoji']} {cat['name']}",
            callback_data=f"admin_cat_edit_{cat['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="➕ СОЗДАТЬ", callback_data="admin_cat_create")])
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_products")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "admin_cat_create")
async def admin_cat_create(callback: CallbackQuery, state: FSMContext):
    """Создание категории."""
    await state.set_state(AdminProductStates.category_create_name)
    await callback.message.edit_text(
        "➕ *СОЗДАНИЕ КАТЕГОРИИ*\n\nВведите название категории:"
    )
    await callback.answer()


@router.message(AdminProductStates.category_create_name)
async def admin_cat_create_name(message: Message, state: FSMContext):
    await state.update_data(cat_name=message.text)
    await state.set_state(AdminProductStates.category_create_emoji)
    await message.answer("✏️ Введите эмодзи для категории (например, 📦):")


@router.message(AdminProductStates.category_create_emoji)
async def admin_cat_create_emoji(message: Message, state: FSMContext):
    await state.update_data(cat_emoji=message.text)
    await state.set_state(AdminProductStates.category_create_desc)
    await message.answer("📝 Введите описание категории (или /skip):")


@router.message(AdminProductStates.category_create_desc)
async def admin_cat_create_desc(message: Message, state: FSMContext):
    data = await state.get_data()
    description = message.text if message.text != "/skip" else ""
    
    cat_id = CategoryModel.create(
        name=data['cat_name'],
        emoji=data['cat_emoji'],
        description=description
    )
    
    await state.clear()
    await message.answer(
        f"✅ *КАТЕГОРИЯ СОЗДАНА!*\n\nID: {cat_id}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К КАТЕГОРИЯМ", callback_data="admin_categories")]
        ])
    )


@router.callback_query(F.data.startswith("admin_cat_edit_"))
async def admin_cat_edit(callback: CallbackQuery, state: FSMContext):
    """Редактирование категории."""
    cat_id = int(callback.data.replace("admin_cat_edit_", ""))
    cat = CategoryModel.get_by_id(cat_id)
    
    if not cat:
        await callback.answer("❌ Категория не найдена")
        return
    
    await state.update_data(edit_cat_id=cat_id)
    
    text = (
        f"✏️ *РЕДАКТИРОВАНИЕ КАТЕГОРИИ*\n\n"
        f"{cat['emoji']} {cat['name']}\n"
        f"📝 {cat['description']}\n\n"
        f"Что хотите изменить?"
    )
    
    buttons = [
        [InlineKeyboardButton(text="📝 Название", callback_data="admin_cat_edit_name")],
        [InlineKeyboardButton(text="😊 Эмодзи", callback_data="admin_cat_edit_emoji")],
        [InlineKeyboardButton(text="📄 Описание", callback_data="admin_cat_edit_desc")],
        [InlineKeyboardButton(text="❌ Удалить", callback_data=f"admin_cat_delete_{cat_id}")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_categories")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_cat_edit_"))
async def admin_cat_edit_field(callback: CallbackQuery, state: FSMContext):
    field = callback.data.replace("admin_cat_edit_", "")
    await state.update_data(edit_field=field)
    await state.set_state(AdminProductStates.category_edit_field)
    
    prompts = {
        "name": "Введите новое название:",
        "emoji": "Введите новый эмодзи:",
        "desc": "Введите новое описание:"
    }
    
    await callback.message.edit_text(prompts.get(field, "Введите новое значение:"))
    await callback.answer()


@router.message(AdminProductStates.category_edit_field)
async def admin_cat_edit_save(message: Message, state: FSMContext):
    data = await state.get_data()
    cat_id = data['edit_cat_id']
    field = data['edit_field']
    
    updates = {
        "name": "name",
        "emoji": "emoji",
        "desc": "description"
    }
    
    CategoryModel.update(cat_id, **{updates[field]: message.text})
    await state.clear()
    
    await message.answer(
        "✅ Категория обновлена!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К КАТЕГОРИЯМ", callback_data="admin_categories")]
        ])
    )


@router.callback_query(F.data.startswith("admin_cat_delete_"))
async def admin_cat_delete(callback: CallbackQuery):
    """Удаление категории."""
    cat_id = int(callback.data.replace("admin_cat_delete_", ""))
    
    # Проверяем, есть ли товары
    products = CategoryModel.get_products(cat_id)
    if products:
        await callback.message.edit_text(
            f"❌ *НЕЛЬЗЯ УДАЛИТЬ*\n\nВ этой категории есть товары ({len(products)} шт.)",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data=f"admin_cat_edit_{cat_id}")]
            ])
        )
        await callback.answer()
        return
    
    success = CategoryModel.delete(cat_id)
    if success:
        await callback.message.edit_text(
            "✅ Категория удалена",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К КАТЕГОРИЯМ", callback_data="admin_categories")]
            ])
        )
    else:
        await callback.message.edit_text(
            "❌ Ошибка при удалении",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_categories")]
            ])
        )
    await callback.answer()


# ======================================================
# БРАСЛЕТЫ
# ======================================================

@router.callback_query(F.data == "admin_bracelets")
async def admin_bracelets(callback: CallbackQuery):
    """Список браслетов."""
    bracelets = BraceletModel.get_all()
    
    text = f"💎 *БРАСЛЕТЫ*\n\nВсего: {len(bracelets)}\n\n"
    
    buttons = []
    for b in bracelets[:20]:
        text += f"• {b['name']} — {format_price(b['price'])}\n"
        buttons.append([InlineKeyboardButton(
            text=f"✏️ {b['name'][:20]}",
            callback_data=f"admin_bracelet_edit_{b['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="➕ СОЗДАТЬ", callback_data="admin_bracelet_create")])
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_products")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "admin_bracelet_create")
async def admin_bracelet_create(callback: CallbackQuery, state: FSMContext):
    """Создание браслета."""
    await state.set_state(AdminProductStates.bracelet_create_name)
    await callback.message.edit_text(
        "➕ *СОЗДАНИЕ БРАСЛЕТА*\n\nВведите название:"
    )
    await callback.answer()


@router.message(AdminProductStates.bracelet_create_name)
async def admin_bracelet_create_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AdminProductStates.bracelet_create_price)
    await message.answer("💰 Введите цену в рублях:")


@router.message(AdminProductStates.bracelet_create_price)
async def admin_bracelet_create_price(message: Message, state: FSMContext):
    try:
        price = float(message.text)
        await state.update_data(price=price)
    except:
        await message.answer("❌ Введите число")
        return
    
    # Получаем список категорий для выбора
    categories = CategoryModel.get_all()
    if not categories:
        await message.answer("❌ Сначала создайте категорию")
        await state.clear()
        return
    
    await state.update_data(categories=categories)
    await state.set_state(AdminProductStates.bracelet_create_category)
    
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(
            text=f"{cat['emoji']} {cat['name']}",
            callback_data=f"admin_bracelet_cat_{cat['id']}"
        )])
    
    await message.answer(
        "📋 Выберите категорию:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(AdminProductStates.bracelet_create_category, F.data.startswith("admin_bracelet_cat_"))
async def admin_bracelet_create_category(callback: CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.replace("admin_bracelet_cat_", ""))
    await state.update_data(category_id=cat_id)
    await state.set_state(AdminProductStates.bracelet_create_desc)
    
    await callback.message.edit_text(
        "📝 Введите описание браслета (или /skip):"
    )
    await callback.answer()


@router.message(AdminProductStates.bracelet_create_desc)
async def admin_bracelet_create_desc(message: Message, state: FSMContext):
    description = message.text if message.text != "/skip" else ""
    await state.update_data(description=description)
    await state.set_state(AdminProductStates.bracelet_create_photo)
    
    await message.answer(
        "🖼️ Отправьте фото браслета (или /skip):"
    )


@router.message(AdminProductStates.bracelet_create_photo)
async def admin_bracelet_create_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    
    if message.photo:
        photo_id = message.photo[-1].file_id
    else:
        photo_id = ""
    
    bracelet_id = BraceletModel.create(
        name=data['name'],
        price=data['price'],
        category_id=data['category_id'],
        description=data['description'],
        image_url=photo_id
    )
    
    await state.clear()
    await message.answer(
        f"✅ *БРАСЛЕТ СОЗДАН!*\n\nID: {bracelet_id}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К БРАСЛЕТАМ", callback_data="admin_bracelets")]
        ])
    )


# ======================================================
# КОЛЛЕКЦИИ ВИТРИНЫ
# ======================================================

@router.callback_query(F.data == "admin_collections")
async def admin_collections(callback: CallbackQuery):
    """Список коллекций витрины."""
    collections = ShowcaseCollectionModel.get_all()
    
    text = f"🖼️ *КОЛЛЕКЦИИ ВИТРИНЫ*\n\nВсего: {len(collections)}\n\n"
    
    buttons = []
    for col in collections:
        text += f"{col['emoji']} {col['name']}\n"
        buttons.append([InlineKeyboardButton(
            text=f"✏️ {col['emoji']} {col['name']}",
            callback_data=f"admin_collection_edit_{col['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="➕ СОЗДАТЬ", callback_data="admin_collection_create")])
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_products")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "admin_collection_create")
async def admin_collection_create(callback: CallbackQuery, state: FSMContext):
    """Создание коллекции."""
    await state.set_state(AdminProductStates.collection_create_name)
    await callback.message.edit_text(
        "➕ *СОЗДАНИЕ КОЛЛЕКЦИИ*\n\nВведите название:"
    )
    await callback.answer()


@router.message(AdminProductStates.collection_create_name)
async def admin_collection_create_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AdminProductStates.collection_create_emoji)
    await message.answer("✏️ Введите эмодзи для коллекции:")


@router.message(AdminProductStates.collection_create_emoji)
async def admin_collection_create_emoji(message: Message, state: FSMContext):
    await state.update_data(emoji=message.text)
    await state.set_state(AdminProductStates.collection_create_desc)
    await message.answer("📝 Введите описание коллекции (или /skip):")


@router.message(AdminProductStates.collection_create_desc)
async def admin_collection_create_desc(message: Message, state: FSMContext):
    data = await state.get_data()
    description = message.text if message.text != "/skip" else ""
    
    col_id = ShowcaseCollectionModel.create(
        name=data['name'],
        emoji=data['emoji'],
        description=description
    )
    
    await state.clear()
    await message.answer(
        f"✅ *КОЛЛЕКЦИЯ СОЗДАНА!*\n\nID: {col_id}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К КОЛЛЕКЦИЯМ", callback_data="admin_collections")]
        ])
    )


# ======================================================
# ТОВАРЫ ВИТРИНЫ
# ======================================================

@router.callback_query(F.data == "admin_showcase")
async def admin_showcase(callback: CallbackQuery):
    """Список товаров витрины."""
    items = ShowcaseItemModel.get_all()
    
    text = f"📦 *ТОВАРЫ ВИТРИНЫ*\n\nВсего: {len(items)}\n\n"
    
    buttons = []
    for item in items[:20]:
        text += f"• {item['name']} — {format_price(item['price'])} ({item.get('stars_price', 0)}⭐)\n"
        buttons.append([InlineKeyboardButton(
            text=f"✏️ {item['name'][:20]}",
            callback_data=f"admin_showcase_edit_{item['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="➕ СОЗДАТЬ", callback_data="admin_showcase_create")])
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_products")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "admin_showcase_create")
async def admin_showcase_create(callback: CallbackQuery, state: FSMContext):
    """Создание товара витрины."""
    await state.set_state(AdminProductStates.showcase_create_name)
    await callback.message.edit_text(
        "➕ *СОЗДАНИЕ ТОВАРА ВИТРИНЫ*\n\nВведите название:"
    )
    await callback.answer()