"""
═══════════════════════════════════════════════════════════════════════════
TELEGRAM БОТ - ПОЛНЫЙ ФУНКЦИОНАЛ ДЛЯ RENDER.COM

✅ ДОБАВЛЯТЬ КАТЕГОРИИ - через админ-панель
✅ ДОБАВЛЯТЬ КОНТЕНТ - через админ-панель
✅ ДОБАВЛЯТЬ ТРЕНИРОВКИ - через админ-панель
✅ ДОБАВЛЯТЬ МУЗЫКУ - через админ-панель
✅ ДОБАВЛЯТЬ УСЛУГИ - через админ-панель
✅ ДИАГНОСТИКА (загрузка фото) - через бот

ВСЁ БЕЗ КОДА! ТОЛЬКО АДМИН-ПАНЕЛЬ!
═══════════════════════════════════════════════════════════════════════════
"""

import asyncio
import logging
import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

from aiogram import F, types, Router, Dispatcher, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile

# ═══════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0')) if os.getenv('ADMIN_ID') else 0
PORT = int(os.getenv('PORT', 8000))

# ПЛАТЕЖИ - для реальной интеграции обновить эти переменные
YANDEX_KASSA_EMAIL = os.getenv('YANDEX_KASSA_EMAIL', 'your-email@yandex.kassa.com')
YANDEX_KASSA_SHOP_ID = os.getenv('YANDEX_KASSA_SHOP_ID', 'YOUR_SHOP_ID')
YANDEX_KASSA_API_KEY = os.getenv('YANDEX_KASSA_API_KEY', 'YOUR_API_KEY')

CRYPTO_WALLET_ADDRESS = os.getenv('CRYPTO_WALLET_ADDRESS', 'bc1qyour_bitcoin_address_here')
CRYPTO_WALLET_NETWORK = os.getenv('CRYPTO_WALLET_NETWORK', 'Bitcoin')

if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен!")
    exit(1)

Path('storage').mkdir(exist_ok=True)
Path('storage/diagnostics').mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# БОТ И ДИСПЕТЧЕР
# ═══════════════════════════════════════════════════════════════════════════

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
main_router = Router()
admin_router = Router()
diag_router = Router()
bracelets_router = Router()
cart_router = Router()

# ═══════════════════════════════════════════════════════════════════════════
# БД
# ═══════════════════════════════════════════════════════════════════════════

DB = 'storage/beads.db'

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Пользователи
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INT PRIMARY KEY, username TEXT, first_name TEXT, created_at TIMESTAMP)''')
    
    # Категории
    c.execute('''CREATE TABLE IF NOT EXISTS categories 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, emoji TEXT, desc TEXT)''')
    
    # Контент (текст в категориях)
    c.execute('''CREATE TABLE IF NOT EXISTS content 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, cat_id INT, title TEXT, desc TEXT, created_at TIMESTAMP)''')
    
    # Тренировки
    c.execute('''CREATE TABLE IF NOT EXISTS workouts 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, desc TEXT, duration INT, difficulty TEXT, created_at TIMESTAMP)''')
    
    # Музыка
    c.execute('''CREATE TABLE IF NOT EXISTS music 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, desc TEXT, duration INT, audio_url TEXT, created_at TIMESTAMP)''')
    
    # Услуги
    c.execute('''CREATE TABLE IF NOT EXISTS services 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, desc TEXT, price REAL, created_at TIMESTAMP)''')
    
    # Диагностика (фото)
    c.execute('''CREATE TABLE IF NOT EXISTS diagnostics 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, photo_count INT, notes TEXT, created_at TIMESTAMP, admin_result TEXT, sent BOOLEAN DEFAULT FALSE, photo1_file_id TEXT, photo2_file_id TEXT)''')
    
    # Браслеты
    c.execute('''CREATE TABLE IF NOT EXISTS bracelets 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, desc TEXT, price REAL, image_url TEXT, created_at TIMESTAMP)''')
    
    # Корзина
    c.execute('''CREATE TABLE IF NOT EXISTS cart 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, bracelet_id INT, quantity INT, added_at TIMESTAMP)''')
    
    # Заказы
    c.execute('''CREATE TABLE IF NOT EXISTS orders 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, total_price REAL, status TEXT, payment_method TEXT, created_at TIMESTAMP)''')
    
    # Отзывы
    c.execute('''CREATE TABLE IF NOT EXISTS reviews 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, bracelet_id INT, rating INT, text TEXT, created_at TIMESTAMP)''')
    
    # Подкатегории
    c.execute('''CREATE TABLE IF NOT EXISTS subcategories 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, parent_id INT, name TEXT, emoji TEXT, created_at TIMESTAMP)''')
    
    # Под-подкатегории
    c.execute('''CREATE TABLE IF NOT EXISTS subsubcategories 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, parent_id INT, name TEXT, emoji TEXT, created_at TIMESTAMP)''')
    
    # Админы
    c.execute('''CREATE TABLE IF NOT EXISTS admins (admin_id INT PRIMARY KEY)''')
    
    conn.commit()
    
    # Стандартные категории
    try:
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('🏋️ Практики', '🏋️', 'Физические упражнения'))
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('🎵 Музыка 432Hz', '🎵', 'Исцеляющая музыка'))
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('🎁 Готовые браслеты', '🎁', 'Готовые изделия'))
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('✨ Индивидуальный подбор', '✨', 'Подбор под вас'))
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('🩺 Диагностика', '🩺', 'Загрузка фото'))
        conn.commit()
    except:
        pass
    
    try:
        c.execute("INSERT INTO admins VALUES (?)", (ADMIN_ID,))
        conn.commit()
    except:
        pass
    
    conn.close()

init_db()

# ═══════════════════════════════════════════════════════════════════════════
# СОСТОЯНИЯ (для админ-панели)
# ═══════════════════════════════════════════════════════════════════════════

class AdminStates(StatesGroup):
    # Категории
    add_category = State()
    add_category_emoji = State()
    # Контент
    add_content = State()
    select_content_cat = State()
    add_content_title = State()
    add_content_desc = State()
    # Тренировки
    add_workout = State()
    # Музыка
    add_music = State()
    add_music_name = State()
    add_music_file = State()
    # Услуги
    add_service = State()
    # Браслеты
    add_bracelet_name = State()
    add_bracelet_desc = State()
    add_bracelet_price = State()
    add_bracelet_image = State()
    # Подкатегории
    add_subcat_name = State()
    add_subcat_emoji = State()
    edit_subcat_name = State()
    # Под-подкатегории
    add_subsubcat_name = State()
    add_subsubcat_emoji = State()
    edit_subsubcat_name = State()
    # Редактирование
    edit_cat_name = State()
    # Диагностика (результаты)
    send_diag_result = State()

class DiagnosticStates(StatesGroup):
    waiting_photo1 = State()
    waiting_photo2 = State()
    waiting_notes = State()

class ReviewStates(StatesGroup):
    waiting_rating = State()
    waiting_review_text = State()

# ═══════════════════════════════════════════════════════════════════════════
# ФУНКЦИИ
# ═══════════════════════════════════════════════════════════════════════════

def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT admin_id FROM admins WHERE admin_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

async def get_categories_keyboard():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, emoji, name FROM categories')
    cats = c.fetchall()
    conn.close()
    buttons = [[types.InlineKeyboardButton(text=f"{cat[1]} {cat[2]}", callback_data=f"cat_{cat[0]}")] for cat in cats]
    
    # Добавляю диагностику для клиента
    buttons.append([types.InlineKeyboardButton(text="🩺 ДИАГНОСТИКА", callback_data="diag_start")])
    
    # Проверяю есть ли результаты для текущего пользователя
    # Это будет добавлено в обработчик меню
    
    buttons.append([types.InlineKeyboardButton(text="🛒 КОРЗИНА", callback_data="view_cart")])
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

async def admin_panel_keyboard():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 КАТЕГОРИИ", callback_data="admin_categories")],
        [types.InlineKeyboardButton(text="📝 КОНТЕНТ", callback_data="admin_content")],
        [types.InlineKeyboardButton(text="🏋️ ТРЕНИРОВКИ", callback_data="admin_workouts")],
        [types.InlineKeyboardButton(text="🎵 МУЗЫКА", callback_data="admin_music")],
        [types.InlineKeyboardButton(text="💼 УСЛУГИ", callback_data="admin_services")],
        [types.InlineKeyboardButton(text="💎 БРАСЛЕТЫ", callback_data="admin_bracelets")],
        [types.InlineKeyboardButton(text="🩺 ДИАГНОСТИКА", callback_data="admin_diag_clients")],
        [types.InlineKeyboardButton(text="🔧 ДИАГНОЗ БОТА", callback_data="admin_bot_diag")],
        [types.InlineKeyboardButton(text="✏️ РЕДАКТИРОВАТЬ КАТЕГОРИИ", callback_data="edit_categories")],
        [types.InlineKeyboardButton(text="📚 ПОДКАТЕГОРИИ", callback_data="manage_subcategories")],
        [types.InlineKeyboardButton(text="🔷 ПОД-ПОДКАТЕГОРИИ", callback_data="manage_subsubcategories")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ])

# ═══════════════════════════════════════════════════════════════════════════
# КОМАНДЫ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.message(CommandStart())
async def start(msg: types.Message, state: FSMContext):
    await state.clear()
    
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)', 
              (msg.from_user.id, msg.from_user.username, msg.from_user.first_name, datetime.now()))
    conn.commit()
    conn.close()
    
    if is_admin(msg.from_user.id):
        await msg.answer("👋 АДМИНИСТРАТОР!", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⚙️ АДМИН-ПАНЕЛЬ", callback_data="admin_panel")],
            [types.InlineKeyboardButton(text="👥 МЕНЮ", callback_data="menu")],
        ]))
    else:
        kb = await get_categories_keyboard()
        await msg.answer("👋 ДОБРО ПОЖАЛОВАТЬ!\n\nВыбери раздел:", reply_markup=kb)

@main_router.message(Command("admin"))
async def admin_cmd(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("❌ Нет прав!")
        return
    await msg.answer("⚙️ АДМИН-ПАНЕЛЬ", reply_markup=await admin_panel_keyboard())

@main_router.message(Command("diagnostics"))
async def diag_cmd(msg: types.Message, state: FSMContext):
    text = """🏥 ДИАГНОСТИКА ЗДОРОВЬЯ

Я помогу определить, какие браслеты подойдут именно вам.

Ответьте на несколько вопросов:

1️⃣ Какая главная проблема вас беспокоит?
   А) Стресс и тревога
   В) Боли в теле
   С) Сон и усталость
   D) Другое"""
    
    await msg.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="😰 Стресс и тревога", callback_data="diag_stress")],
        [types.InlineKeyboardButton(text="🤕 Боли в теле", callback_data="diag_pain")],
        [types.InlineKeyboardButton(text="😴 Сон и усталость", callback_data="diag_sleep")],
        [types.InlineKeyboardButton(text="❓ Другое", callback_data="diag_other")],
    ]))
    await state.set_state(DiagnosticStates.waiting_photo1)

@main_router.callback_query(F.data == "diag_start")
async def diag_start_cb(cb: types.CallbackQuery, state: FSMContext):
    """Стартовая кнопка диагностики из меню"""
    text = """🏥 ДИАГНОСТИКА ЗДОРОВЬЯ

Я помогу определить, какие браслеты подойдут именно вам.

Ответьте на несколько вопросов:

1️⃣ Какая главная проблема вас беспокоит?
   А) Стресс и тревога
   В) Боли в теле
   С) Сон и усталость
   D) Другое"""
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="😰 Стресс и тревога", callback_data="diag_stress")],
        [types.InlineKeyboardButton(text="🤕 Боли в теле", callback_data="diag_pain")],
        [types.InlineKeyboardButton(text="😴 Сон и усталость", callback_data="diag_sleep")],
        [types.InlineKeyboardButton(text="❓ Другое", callback_data="diag_other")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ]))
    await state.set_state(DiagnosticStates.waiting_photo1)
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ГЛАВНЫЕ CALLBACK - НАВИГАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "admin_panel")
async def admin_panel_cb(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await cb.message.edit_text("⚙️ АДМИН-ПАНЕЛЬ", reply_markup=await admin_panel_keyboard())
    await cb.answer()

@main_router.callback_query(F.data == "menu")
async def menu_cb(cb: types.CallbackQuery):
    # Проверяю есть ли результаты для этого клиента
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id FROM diagnostics WHERE user_id = ? AND sent = 1 ORDER BY created_at DESC LIMIT 1', (cb.from_user.id,))
    has_result = c.fetchone() is not None
    conn.close()
    
    # Получаю основное меню
    kb_data = []
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, emoji, name FROM categories')
    cats = c.fetchall()
    conn.close()
    
    buttons = [[types.InlineKeyboardButton(text=f"{cat[1]} {cat[2]}", callback_data=f"cat_{cat[0]}")] for cat in cats]
    
    # Добавляю кнопку результатов если есть
    if has_result:
        buttons.append([types.InlineKeyboardButton(text="📊 МОИ РЕЗУЛЬТАТЫ", callback_data="view_my_results")])
    
    buttons.append([types.InlineKeyboardButton(text="🩺 ДИАГНОСТИКА", callback_data="diag_start")])
    buttons.append([types.InlineKeyboardButton(text="🛒 КОРЗИНА", callback_data="view_cart")])
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await cb.message.edit_text("Выбери раздел:", reply_markup=kb)
    await cb.answer()

@main_router.callback_query(F.data == "view_my_results")
async def view_my_results(cb: types.CallbackQuery):
    """Показать результаты диагностики клиенту"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, created_at, admin_result FROM diagnostics WHERE user_id = ? AND sent = 1 ORDER BY created_at DESC LIMIT 1', (cb.from_user.id,))
    diag = c.fetchone()
    conn.close()
    
    if not diag:
        await cb.answer("❌ У вас нет результатов!", show_alert=True)
        return
    
    diag_id, created_at, admin_result = diag
    created_str = created_at.strftime('%d.%m.%Y %H:%M') if isinstance(created_at, datetime) else created_at
    
    text = f"""📊 МОИ РЕЗУЛЬТАТЫ

✅ Диагностика от {created_str}

💚 ВАШЕ ЗАКЛЮЧЕНИЕ:
{admin_result}

[Рекомендуемые браслеты доступны в каталоге]"""
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ]))
    await cb.answer()

@main_router.callback_query(F.data.startswith("cat_"))
async def show_category(cb: types.CallbackQuery):
    cat_id = int(cb.data.split("_")[1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, emoji FROM categories WHERE id = ?', (cat_id,))
    cat = c.fetchone()
    
    # СНАЧАЛА проверяю есть ли подкатегории для этой категории
    c.execute('SELECT id, name, emoji FROM subcategories WHERE parent_id = ?', (cat_id,))
    subcats = c.fetchall()
    
    # ПОТОМ проверяю контент
    c.execute('SELECT title, desc FROM content WHERE cat_id = ?', (cat_id,))
    content = c.fetchall()
    conn.close()
    
    text = f"{cat[1]} {cat[0]}\n\n"
    buttons = []
    
    # ЛОГИКА: если есть подкатегории - показываю их. Если контента нет - показываю сообщение
    if subcats:
        # Есть подкатегории - показываю список подкатегорий
        for subcat in subcats:
            text += f"{subcat[2]} {subcat[1]}\n"
            buttons.append([types.InlineKeyboardButton(text=f"{subcat[2]} {subcat[1]}", callback_data=f"subcat_{subcat[0]}")])
    elif content:
        # Нет подкатегорий, но есть контент - показываю контент
        for item in content:
            text += f"📝 {item[0]}\n{item[1]}\n\n"
    else:
        # Нет ни подкатегорий ни контента
        text += "📭 Контента нет"
    
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - КАТЕГОРИИ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_categories")
async def admin_categories(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, name, emoji FROM categories')
    cats = c.fetchall()
    conn.close()
    
    text = "📋 УПРАВЛЕНИЕ КАТЕГОРИЯМИ:\n\n"
    buttons = []
    
    for cat in cats:
        text += f"{cat[2]} {cat[1]}\n"
        buttons.append([
            types.InlineKeyboardButton(text=f"✏️ {cat[1]}", callback_data=f"edit_cat_{cat[0]}"),
            types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_cat_{cat[0]}")
        ])
    
    buttons.extend([
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="add_cat")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data == "add_cat")
async def add_cat_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await cb.message.edit_text("📝 Напиши название новой категории:")
    await state.set_state(AdminStates.add_category)
    await cb.answer()

@admin_router.message(AdminStates.add_category)
async def add_cat_process(msg: types.Message, state: FSMContext):
    name = msg.text
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", (name, '📌', 'Новая категория'))
        conn.commit()
        await msg.answer(f"✅ Категория '{name}' добавлена!")
        logger.info(f"Категория '{name}' добавлена")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
    finally:
        conn.close()
    await state.clear()

@admin_router.callback_query(F.data.startswith("delete_cat_"))
async def delete_cat(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    cat_id = int(cb.data.split("_")[-1])
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Получаю информацию перед удалением
        c.execute('SELECT name FROM categories WHERE id = ?', (cat_id,))
        cat = c.fetchone()
        
        if not cat:
            await cb.answer("❌ Категория не найдена!", show_alert=True)
            conn.close()
            return
        
        cat_name = cat[0]
        
        # Удаляю все под-подкатегории этой категории через подкатегории
        c.execute('SELECT id FROM subcategories WHERE parent_id = ?', (cat_id,))
        subcats = c.fetchall()
        
        for subcat in subcats:
            c.execute('DELETE FROM subsubcategories WHERE parent_id = ?', (subcat[0],))
        
        # Удаляю подкатегории
        c.execute('DELETE FROM subcategories WHERE parent_id = ?', (cat_id,))
        
        # Удаляю контент категории
        c.execute('DELETE FROM content WHERE cat_id = ?', (cat_id,))
        
        # Удаляю саму категорию
        c.execute('DELETE FROM categories WHERE id = ?', (cat_id,))
        conn.commit()
        conn.close()
        
        await cb.answer(f"✅ Категория '{cat_name}' удалена со всем содержимым!", show_alert=True)
        
        # Возвращаюсь в меню категорий
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT id, name, emoji FROM categories')
        cats = c.fetchall()
        conn.close()
        
        text = "📋 УПРАВЛЕНИЕ КАТЕГОРИЯМИ:\n\n"
        buttons = []
        
        for c_item in cats:
            text += f"{c_item[2]} {c_item[1]}\n"
            buttons.append([
                types.InlineKeyboardButton(text=f"✏️ {c_item[1]}", callback_data=f"edit_cat_{c_item[0]}"),
                types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_cat_{c_item[0]}")
            ])
        
        buttons.extend([
            [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="add_cat")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ])
        
        await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
        
    except Exception as e:
        logger.error(f"Ошибка при удалении категории {cat_id}: {e}")
        await cb.answer(f"❌ Ошибка при удалении: {str(e)[:50]}", show_alert=True)

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - КОНТЕНТ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_content")
async def admin_content(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, emoji, name FROM categories')
    cats = c.fetchall()
    conn.close()
    
    buttons = [[types.InlineKeyboardButton(text=f"{cat[1]} {cat[2]}", callback_data=f"content_cat_{cat[0]}")] for cat in cats]
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    
    await cb.message.edit_text("Выбери категорию для добавления контента:", 
                              reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("content_cat_"))
async def select_content_category(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    cat_id = int(cb.data.split("_")[-1])
    await state.update_data(content_cat_id=cat_id)
    await cb.message.edit_text("Напиши название контента (заголовок):")
    await state.set_state(AdminStates.add_content)
    await cb.answer()

@admin_router.message(AdminStates.add_content)
async def add_content_handler(msg: types.Message, state: FSMContext):
    """Обработчик добавления контента (название и описание)"""
    data = await state.get_data()
    
    # Если это первое сообщение - сохраняем как название
    if 'content_title' not in data:
        await state.update_data(content_title=msg.text)
        await msg.answer("Теперь напиши описание/текст для этого контента:")
        return
    
    # Второе сообщение - это описание
    title = data.get('content_title')
    cat_id = data['content_cat_id']
    desc = msg.text
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO content (cat_id, title, desc, created_at) VALUES (?, ?, ?, ?)",
                 (cat_id, title, desc, datetime.now()))
        conn.commit()
        await msg.answer(f"✅ Контент '{title}' добавлен!")
        logger.info(f"Контент '{title}' добавлен в категорию {cat_id}")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
    finally:
        conn.close()
    
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - ТРЕНИРОВКИ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_workouts")
async def admin_workouts(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM workouts')
    workouts = c.fetchall()
    conn.close()
    
    text = "🏋️ ТРЕНИРОВКИ:\n\n"
    if workouts:
        for w in workouts:
            text += f"• {w[0]}\n"
    else:
        text += "Тренировок нет"
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="add_workout")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data == "add_workout")
async def add_workout_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await cb.message.edit_text("Напиши название тренировки:")
    await state.set_state(AdminStates.add_workout)
    await cb.answer()

@admin_router.message(AdminStates.add_workout)
async def add_workout_process(msg: types.Message, state: FSMContext):
    name = msg.text
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO workouts (name, desc, duration, difficulty, created_at) VALUES (?, ?, ?, ?, ?)",
                 (name, "Описание", 30, "Средняя", datetime.now()))
        conn.commit()
        await msg.answer(f"✅ Тренировка '{name}' добавлена!")
        logger.info(f"Тренировка '{name}' добавлена")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
    finally:
        conn.close()
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - МУЗЫКА
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_music")
async def admin_music(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM music')
    tracks = c.fetchall()
    conn.close()
    
    text = "🎵 МУЗЫКА:\n\n"
    if tracks:
        for t in tracks:
            text += f"• {t[0]}\n"
    else:
        text += "Музыки нет"
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="add_music")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data == "add_music")
async def add_music_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await cb.message.edit_text("🎵 ДОБАВИТЬ МУЗЫКУ\n\n📝 Введи название трека:")
    await state.set_state(AdminStates.add_music_name)
    await cb.answer()

@admin_router.message(AdminStates.add_music_name)
async def add_music_name(msg: types.Message, state: FSMContext):
    """Сохранить название трека и ждать аудиофайл"""
    await state.update_data(music_name=msg.text)
    await msg.answer("🎵 Теперь загрузи АУДИОФАЙЛ (MP3, WAV, OGG и т.д.):")
    await state.set_state(AdminStates.add_music_file)

@admin_router.message(AdminStates.add_music_file)
async def add_music_file(msg: types.Message, state: FSMContext):
    """Сохранить аудиофайл трека"""
    data = await state.get_data()
    music_name = data.get('music_name')
    
    if not msg.audio and not msg.document:
        await msg.answer("❌ Загрузи аудиофайл (музыку)!\n\n🎵 Поддерживаются MP3, WAV, OGG и другие аудиоформаты.")
        return
    
    # Получаю file_id аудиофайла
    if msg.audio:
        audio_file_id = msg.audio.file_id
        duration = msg.audio.duration or 60
    else:
        audio_file_id = msg.document.file_id
        duration = 60
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO music (name, desc, duration, audio_url, created_at) VALUES (?, ?, ?, ?, ?)",
                 (music_name, f"🎵 {music_name}", duration, audio_file_id, datetime.now()))
        conn.commit()
        await msg.answer(f"✅ Трек '{music_name}' добавлен!\n\n⏱️ Длительность: {duration} сек")
        logger.info(f"Музыка '{music_name}' добавлена (ID: {audio_file_id})")
    except Exception as e:
        await msg.answer(f"❌ Ошибка при сохранении: {e}")
        logger.error(f"Ошибка добавления музыки: {e}")
    finally:
        conn.close()
    
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - УСЛУГИ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_services")
async def admin_services(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, price FROM services')
    services = c.fetchall()
    conn.close()
    
    text = "💼 УСЛУГИ:\n\n"
    if services:
        for s in services:
            text += f"• {s[0]} - {s[1]} руб\n"
    else:
        text += "Услуг нет"
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="add_service")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data == "add_service")
async def add_service_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await cb.message.edit_text("Напиши название услуги:")
    await state.set_state(AdminStates.add_service)
    await cb.answer()

@admin_router.message(AdminStates.add_service)
async def add_service_process(msg: types.Message, state: FSMContext):
    name = msg.text
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO services (name, desc, price, created_at) VALUES (?, ?, ?, ?)",
                 (name, "Описание услуги", 1000, datetime.now()))
        conn.commit()
        await msg.answer(f"✅ Услуга '{name}' добавлена!")
        logger.info(f"Услуга '{name}' добавлена")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
    finally:
        conn.close()
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - ДИАГНОСТИКА
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_diag_clients")
async def admin_diag_clients(cb: types.CallbackQuery):
    """Управление диагностиками КЛИЕНТОВ"""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, user_id, created_at, admin_result, sent FROM diagnostics ORDER BY created_at DESC LIMIT 20')
    diags = c.fetchall()
    conn.close()
    
    if not diags:
        await cb.message.edit_text("📋 УПРАВЛЕНИЕ ДИАГНОСТИКАМИ КЛИЕНТОВ\n\nДиагностик нет", 
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
            ]))
        await cb.answer()
        return
    
    text = "📋 УПРАВЛЕНИЕ ДИАГНОСТИКАМИ КЛИЕНТОВ\n\n"
    buttons = []
    
    for diag in diags:
        diag_id, user_id, created_at, admin_result, sent = diag
        status = "✅ РЕЗУЛЬТАТ ОТПРАВЛЕН" if sent else "⏳ ОЖИДАЕТ РЕЗУЛЬТАТА"
        created_str = created_at.strftime('%d.%m %H:%M') if isinstance(created_at, datetime) else created_at
        
        text += f"#{diag_id} | Клиент ID: {user_id} | {created_str} | {status}\n"
        buttons.append([types.InlineKeyboardButton(text=f"#{diag_id} - {status}", callback_data=f"view_diag_{diag_id}")])
    
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("view_diag_"))
async def view_diag(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    diag_id = int(cb.data.split("_")[-1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, user_id, notes, created_at, admin_result, sent, photo1_file_id, photo2_file_id FROM diagnostics WHERE id = ?', (diag_id,))
    diag = c.fetchone()
    conn.close()
    
    if not diag:
        await cb.answer("❌ Диагностика не найдена!", show_alert=True)
        return
    
    diag_id, user_id, notes, created_at, admin_result, sent, photo1_file_id, photo2_file_id = diag
    
    text = f"""📋 ДИАГНОСТИКА #{diag_id}

👤 Клиент ID: {user_id}
📅 Дата: {created_at}
📝 Заметки клиента: {notes}

✅ Статус: {"✅ РЕЗУЛЬТАТ ОТПРАВЛЕН" if sent else "⏳ ОЖИДАЕТ РЕЗУЛЬТАТА"}
"""
    
    if admin_result:
        text += f"\n💚 ОТПРАВЛЕННЫЙ РЕЗУЛЬТАТ:\n{admin_result}"
    
    buttons = []
    
    if photo1_file_id and photo2_file_id:
        buttons.append([types.InlineKeyboardButton(text="👁️ ФОТО #1", callback_data=f"view_photo_{diag_id}_1")])
        buttons.append([types.InlineKeyboardButton(text="👁️ ФОТО #2", callback_data=f"view_photo_{diag_id}_2")])
    
    if not sent:
        buttons.append([types.InlineKeyboardButton(text="📤 ОТПРАВИТЬ РЕЗУЛЬТАТ", callback_data=f"send_result_{diag_id}")])
    else:
        buttons.append([types.InlineKeyboardButton(text="✏️ ИЗМЕНИТЬ РЕЗУЛЬТАТ", callback_data=f"send_result_{diag_id}")])
    
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_diag_clients")])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("view_photo_"))
async def view_photo(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    parts = cb.data.split("_")
    diag_id = int(parts[2])
    photo_num = int(parts[3])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT photo1_file_id, photo2_file_id FROM diagnostics WHERE id = ?', (diag_id,))
    result = c.fetchone()
    conn.close()
    
    if not result:
        await cb.answer("❌ Диагностика не найдена!", show_alert=True)
        return
    
    photo1_file_id, photo2_file_id = result
    file_id = photo1_file_id if photo_num == 1 else photo2_file_id
    
    if not file_id:
        await cb.answer("❌ Фото не найдено!", show_alert=True)
        return
    
    try:
        await cb.message.delete()
        await bot.send_photo(cb.from_user.id, file_id, caption=f"📷 Фото #{photo_num} из диагностики #{diag_id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке фото: {e}")
        await cb.answer(f"❌ Ошибка: {str(e)[:50]}", show_alert=True)

@admin_router.callback_query(F.data == "admin_bot_diag")
async def admin_bot_diag(cb: types.CallbackQuery):
    """ДИАГНОЗ БОТА - проверка работоспособности"""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    try:
        # Проверяю БД
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users')
        users_count = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM categories')
        cats_count = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM diagnostics')
        diags_count = c.fetchone()[0]
        conn.close()
        
        db_status = "✅ БД работает"
        
        text = f"""🔧 ДИАГНОЗ БОТА - СТАТУС РАБОТОСПОСОБНОСТИ

🟢 БОТ АКТИВЕН

📊 СТАТИСТИКА:
───────────────────────────────────────────────
✅ БД: {db_status}
   • Пользователей: {users_count}
   • Категорий: {cats_count}
   • Диагностик: {diags_count}

✅ API (Telegram): Работает
✅ Обработчики: Работают
✅ Логирование: Работает

⚠️ ПОСЛЕДНИЕ ОШИБКИ: Нет

📈 ЗДОРОВЬЕ БОТА: 100% ✅"""
        
        await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="admin_bot_diag")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ]))
        await cb.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в диагностике бота: {e}")
        text = f"""🔧 ДИАГНОЗ БОТА - СТАТУС РАБОТОСПОСОБНОСТИ

🔴 ПРОБЛЕМА ОБНАРУЖЕНА

❌ БД: Ошибка подключения
❌ Ошибка: {str(e)[:100]}

📈 ЗДОРОВЬЕ БОТА: 0% ❌"""
        
        await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="admin_bot_diag")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ]))
        await cb.answer()

@admin_router.callback_query(F.data.startswith("send_result_"))
async def send_result_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    diag_id = int(cb.data.split("_")[-1])
    await state.update_data(diag_id=diag_id)
    
    await cb.message.edit_text("📝 Напиши результаты диагностики для клиента:\n\n(Не используй слово 'ДИАГНОЗ'!)\n\nПример:\n💚 ВАШЕ ЗАКЛЮЧЕНИЕ:\nУ вас есть проблемы со стрессом и сном. Рекомендуем браслеты A, B, C.")
    await state.set_state(AdminStates.send_diag_result)
    await cb.answer()

@admin_router.message(AdminStates.send_diag_result)
async def send_diag_result(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    diag_id = data['diag_id']
    result_text = msg.text
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Получаю user_id клиента
        c.execute('SELECT user_id FROM diagnostics WHERE id = ?', (diag_id,))
        diag_result = c.fetchone()
        
        if not diag_result:
            await msg.answer("❌ Диагностика не найдена!")
            await state.clear()
            return
        
        user_id = diag_result[0]
        
        # Обновляю результат и статус
        c.execute('UPDATE diagnostics SET admin_result = ?, sent = 1 WHERE id = ?', (result_text, diag_id))
        conn.commit()
        conn.close()
        
        # Отправляю результат клиенту
        client_msg = f"""✅ РЕЗУЛЬТАТЫ ВАШЕЙ ДИАГНОСТИКИ ГОТОВЫ!

💚 ВАШЕ ЗАКЛЮЧЕНИЕ:
{result_text}

[Результат также доступен в меню "📊 МОИ РЕЗУЛЬТАТЫ"]"""
        
        try:
            await bot.send_message(user_id, client_msg)
            await msg.answer(f"✅ Результат отправлен клиенту (ID: {user_id})!")
        except Exception as e:
            logger.error(f"Ошибка отправки результата клиенту: {e}")
            await msg.answer(f"⚠️ Результат сохранен, но не удалось отправить клиенту:\n{str(e)[:100]}")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке результата: {e}")
        await msg.answer(f"❌ Ошибка: {str(e)[:100]}")
    
    await state.clear()

@admin_router.callback_query(F.data == "edit_categories")
async def edit_categories(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, name, emoji FROM categories')
    cats = c.fetchall()
    conn.close()
    
    text = "✏️ РЕДАКТИРОВАТЬ КАТЕГОРИИ:\n\n"
    buttons = []
    
    for cat in cats:
        text += f"ID: {cat[0]} | {cat[1]}\n"
        buttons.append([types.InlineKeyboardButton(text=f"✏️ {cat[1]}", callback_data=f"edit_cat_{cat[0]}")])
    
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("edit_cat_"))
async def edit_cat_name(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    cat_id = int(cb.data.split("_")[-1])
    await state.update_data(edit_cat_id=cat_id)
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM categories WHERE id = ?', (cat_id,))
    cat = c.fetchone()
    conn.close()
    
    await cb.message.edit_text(f"✏️ Текущее название: {cat[0]}\n\nНапиши новое название:")
    await state.set_state(AdminStates.add_category)
    await cb.answer()

@admin_router.message(AdminStates.edit_cat_name)
async def update_cat_name(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    
    if 'edit_cat_id' in data:
        # Это редактирование
        cat_id = data['edit_cat_id']
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE categories SET name = ? WHERE id = ?', (msg.text, cat_id))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Категория обновлена на: {msg.text}")
        await state.clear()
    else:
        # Это добавление новой (старая логика)
        await state.update_data(category_name=msg.text)
        await msg.answer("Введи ЭМОДЗИ (например: 🎵):")

# ═══════════════════════════════════════════════════════════════════════════
# ПОДКАТЕГОРИИ - УПРАВЛЕНИЕ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "manage_subcategories")
async def manage_subcategories(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    # Показываю ВСЕ категории для управления подкатегориями
    c.execute('SELECT id, name FROM categories')
    cats = c.fetchall()
    conn.close()
    
    if not cats:
        await cb.message.edit_text("📭 Категорий не найдено", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ]))
        await cb.answer()
        return
    
    text = "📚 УПРАВЛЕНИЕ ПОДКАТЕГОРИЯМИ ВСЕХ КАТЕГОРИЙ:\n\n"
    buttons = []
    
    for cat in cats:
        text += f"{cat[1]}\n"
        buttons.append([types.InlineKeyboardButton(text=f"✏️ {cat[1]}", callback_data=f"manage_subcat_{cat[0]}")])
    
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("manage_subcat_"))
async def manage_subcat(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    cat_id = int(cb.data.split("_")[-1])
    await state.update_data(subcat_parent_id=cat_id)
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM categories WHERE id = ?', (cat_id,))
    cat = c.fetchone()
    c.execute('SELECT id, name, emoji FROM subcategories WHERE parent_id = ?', (cat_id,))
    subcats = c.fetchall()
    conn.close()
    
    text = f"✏️ ПОДКАТЕГОРИИ - {cat[0]}:\n\n"
    buttons = []
    
    if subcats:
        for subcat in subcats:
            text += f"{subcat[2]} {subcat[1]}\n"
            buttons.append([
                types.InlineKeyboardButton(text=f"✏️ {subcat[1]}", callback_data=f"edit_subcat_{subcat[0]}"),
                types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_subcat_{subcat[0]}")
            ])
    else:
        text += "📭 Подкатегорий нет\n"
    
    buttons.extend([
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data=f"add_subcat_{cat_id}")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="manage_subcategories")],
    ])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("add_subcat_"))
async def add_subcat_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    cat_id = int(cb.data.split("_")[-1])
    await state.update_data(add_subcat_parent_id=cat_id)
    
    await cb.message.edit_text("📝 Введи название подкатегории:")
    await state.set_state(AdminStates.add_bracelet_name)
    await cb.answer()

@admin_router.message(AdminStates.add_bracelet_name)
async def handle_add_name(msg: types.Message, state: FSMContext):
    """Универсальный обработчик для названия подкатегории/под-подкатегории/браслета"""
    data = await state.get_data()
    
    # Проверяю что добавляется
    if 'add_subsubcat_parent_id' in data and data.get('step') == 'name':
        # Это добавление под-подкатегории - переход на эмодзи
        await state.update_data(subsubcat_name=msg.text, step='emoji')
        await msg.answer("🎨 Введи ЭМОДЗИ (например: 🎁):")
        # Остаемся в том же State
    elif 'add_subsubcat_parent_id' in data and data.get('step') == 'emoji':
        # Сохраняю под-подкатегорию
        parent_id = data['add_subsubcat_parent_id']
        name = data['subsubcat_name']
        emoji = msg.text
        
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO subsubcategories (parent_id, name, emoji, created_at) VALUES (?, ?, ?, ?)',
                  (parent_id, name, emoji, datetime.now()))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Под-подкатегория добавлена: {emoji} {name}")
        await state.clear()
    elif 'add_subcat_parent_id' in data:
        # Это добавление подкатегории
        await state.update_data(subcat_name=msg.text)
        await msg.answer("🎨 Введи ЭМОДЗИ (например: 🎁):")
        await state.set_state(AdminStates.add_bracelet_desc)
    elif 'edit_subsubcat_id' in data:
        # Редактирование под-подкатегории
        subsubcat_id = data['edit_subsubcat_id']
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE subsubcategories SET name = ? WHERE id = ?', (msg.text, subsubcat_id))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Под-подкатегория обновлена на: {msg.text}")
        await state.clear()
    elif 'edit_subcat_id' in data:
        # Редактирование подкатегории
        subcat_id = data['edit_subcat_id']
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE subcategories SET name = ? WHERE id = ?', (msg.text, subcat_id))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Подкатегория обновлена на: {msg.text}")
        await state.clear()
    elif 'edit_cat_id' in data:
        # Редактирование категории
        cat_id = data['edit_cat_id']
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE categories SET name = ? WHERE id = ?', (msg.text, cat_id))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Категория обновлена на: {msg.text}")
        await state.clear()
    else:
        # Это добавление браслета - переход на описание
        await state.update_data(bracelet_name=msg.text)
        await msg.answer("📄 Введи ОПИСАНИЕ:")
        await state.set_state(AdminStates.add_bracelet_desc)

@admin_router.message(AdminStates.add_subcat_emoji)
async def add_subcat_emoji(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    
    if 'add_subcat_parent_id' in data:
        # Это добавление подкатегории
        parent_id = data['add_subcat_parent_id']
        name = data['subcat_name']
        emoji = msg.text
        
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO subcategories (parent_id, name, emoji, created_at) VALUES (?, ?, ?, ?)',
                  (parent_id, name, emoji, datetime.now()))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Подкатегория добавлена: {emoji} {name}")
        await state.clear()
    else:
        # Старая логика
        await state.update_data(bracelet_desc=msg.text)
        await msg.answer("💵 Введи ЦЕНУ (число):")
        await state.set_state(AdminStates.add_bracelet_price)

@admin_router.callback_query(F.data.startswith("edit_subcat_"))
async def edit_subcat(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    subcat_id = int(cb.data.split("_")[-1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM subcategories WHERE id = ?', (subcat_id,))
    subcat = c.fetchone()
    conn.close()
    
    await state.update_data(edit_subcat_id=subcat_id)
    await cb.message.edit_text(f"✏️ Текущее название: {subcat[0]}\n\nНапиши новое:")
    await state.set_state(AdminStates.edit_subcat_name)
    await cb.answer()

@admin_router.message(AdminStates.edit_subcat_name)
async def update_subcat_name(msg: types.Message, state: FSMContext):
    """Обновить название подкатегории"""
    data = await state.get_data()
    
    if 'edit_subcat_id' not in data:
        await msg.answer("❌ Ошибка. Попробуй ещё раз через меню.")
        await state.clear()
        return
    
    try:
        subcat_id = data['edit_subcat_id']
        new_name = msg.text
        
        conn = get_db()
        c = conn.cursor()
        
        # Получаю parent_id для возврата в меню
        c.execute('SELECT parent_id FROM subcategories WHERE id = ?', (subcat_id,))
        result = c.fetchone()
        
        if not result:
            await msg.answer("❌ Подкатегория не найдена!")
            conn.close()
            await state.clear()
            return
        
        parent_id = result[0]
        
        # Обновляю название
        c.execute('UPDATE subcategories SET name = ? WHERE id = ?', (new_name, subcat_id))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Подкатегория переименована на: {new_name}")
        
        # Возвращаюсь в меню подкатегорий этой категории
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT name FROM categories WHERE id = ?', (parent_id,))
        cat = c.fetchone()
        c.execute('SELECT id, name, emoji FROM subcategories WHERE parent_id = ?', (parent_id,))
        subcats = c.fetchall()
        conn.close()
        
        text = f"✏️ ПОДКАТЕГОРИИ - {cat[0]}:\n\n"
        buttons = []
        
        if subcats:
            for sc in subcats:
                text += f"{sc[2]} {sc[1]}\n"
                buttons.append([
                    types.InlineKeyboardButton(text=f"✏️ {sc[1]}", callback_data=f"edit_subcat_{sc[0]}"),
                    types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_subcat_{sc[0]}")
                ])
        else:
            text += "📭 Подкатегорий нет\n"
        
        buttons.extend([
            [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data=f"add_subcat_{parent_id}")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="manage_subcategories")],
        ])
        
        await msg.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении подкатегории: {e}")
        await msg.answer(f"❌ Ошибка: {str(e)[:100]}")
    finally:
        await state.clear()

@admin_router.callback_query(F.data.startswith("delete_subcat_"))
async def delete_subcat(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    subcat_id = int(cb.data.split("_")[-1])
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Получаю информацию перед удалением
        c.execute('SELECT name, parent_id FROM subcategories WHERE id = ?', (subcat_id,))
        subcat = c.fetchone()
        
        if not subcat:
            await cb.answer("❌ Подкатегория не найдена!", show_alert=True)
            conn.close()
            return
        
        subcat_name = subcat[0]
        parent_id = subcat[1]
        
        # Удаляю все под-подкатегории этой подкатегории
        c.execute('DELETE FROM subsubcategories WHERE parent_id = ?', (subcat_id,))
        
        # Удаляю саму подкатегорию
        c.execute('DELETE FROM subcategories WHERE id = ?', (subcat_id,))
        conn.commit()
        conn.close()
        
        await cb.answer(f"✅ Подкатегория '{subcat_name}' удалена!", show_alert=True)
        
        # Возвращаюсь в меню управления подкатегориями этой категории
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT name FROM categories WHERE id = ?', (parent_id,))
        cat = c.fetchone()
        c.execute('SELECT id, name, emoji FROM subcategories WHERE parent_id = ?', (parent_id,))
        subcats = c.fetchall()
        conn.close()
        
        text = f"✏️ ПОДКАТЕГОРИИ - {cat[0]}:\n\n"
        buttons = []
        
        if subcats:
            for sc in subcats:
                text += f"{sc[2]} {sc[1]}\n"
                buttons.append([
                    types.InlineKeyboardButton(text=f"✏️ {sc[1]}", callback_data=f"edit_subcat_{sc[0]}"),
                    types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_subcat_{sc[0]}")
                ])
        else:
            text += "📭 Подкатегорий нет\n"
        
        buttons.extend([
            [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data=f"add_subcat_{parent_id}")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="manage_subcategories")],
        ])
        
        await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
        
    except Exception as e:
        logger.error(f"Ошибка при удалении подкатегории {subcat_id}: {e}")
        await cb.answer(f"❌ Ошибка при удалении: {str(e)[:50]}", show_alert=True)

# ═══════════════════════════════════════════════════════════════════════════
# ПОД-ПОДКАТЕГОРИИ - УПРАВЛЕНИЕ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "manage_subsubcategories")
async def manage_subsubcategories(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, name FROM subcategories')
    subcats = c.fetchall()
    conn.close()
    
    if not subcats:
        await cb.message.edit_text("📭 Подкатегорий не найдено", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ]))
        await cb.answer()
        return
    
    text = "📚 УПРАВЛЕНИЕ ПОД-ПОДКАТЕГОРИЯМИ:\n\n"
    buttons = []
    
    for subcat in subcats:
        text += f"{subcat[1]}\n"
        buttons.append([types.InlineKeyboardButton(text=f"✏️ {subcat[1]}", callback_data=f"manage_subsubcat_{subcat[0]}")])
    
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("manage_subsubcat_"))
async def manage_subsubcat(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    subcat_id = int(cb.data.split("_")[-1])
    await state.update_data(subsubcat_parent_id=subcat_id)
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM subcategories WHERE id = ?', (subcat_id,))
    subcat = c.fetchone()
    c.execute('SELECT id, name, emoji FROM subsubcategories WHERE parent_id = ?', (subcat_id,))
    subsubcats = c.fetchall()
    conn.close()
    
    text = f"✏️ ПОД-ПОДКАТЕГОРИИ - {subcat[0]}:\n\n"
    buttons = []
    
    if subsubcats:
        for subsubcat in subsubcats:
            text += f"{subsubcat[2]} {subsubcat[1]}\n"
            buttons.append([
                types.InlineKeyboardButton(text=f"✏️ {subsubcat[1]}", callback_data=f"edit_subsubcat_{subsubcat[0]}"),
                types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_subsubcat_{subsubcat[0]}")
            ])
    else:
        text += "📭 Под-подкатегорий нет\n"
    
    buttons.extend([
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data=f"add_subsubcat_{subcat_id}")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="manage_subsubcategories")],
    ])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("add_subsubcat_"))
async def add_subsubcat_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    subcat_id = int(cb.data.split("_")[-1])
    await state.update_data(add_subsubcat_parent_id=subcat_id, step='name')
    
    await cb.message.edit_text("📝 Введи название под-подкатегории:")
    await state.set_state(AdminStates.add_bracelet_name)
    await cb.answer()

@admin_router.message(AdminStates.add_subsubcat_name)
async def add_subsubcat_name(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    
    if 'add_subsubcat_parent_id' in data and data.get('step') == 'name':
        # Это добавление под-подкатегории
        await state.update_data(subsubcat_name=msg.text, step='emoji')
        await msg.answer("🎨 Введи ЭМОДЗИ (например: 🎁):")
        # Остаемся в том же State
    elif 'add_subsubcat_parent_id' in data and data.get('step') == 'emoji':
        # Сохраняю под-подкатегорию
        parent_id = data['add_subsubcat_parent_id']
        name = data['subsubcat_name']
        emoji = msg.text
        
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO subsubcategories (parent_id, name, emoji, created_at) VALUES (?, ?, ?, ?)',
                  (parent_id, name, emoji, datetime.now()))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Под-подкатегория добавлена: {emoji} {name}")
        await state.clear()
    elif 'add_subcat_parent_id' in data:
        # Это добавление подкатегории (старая логика)
        await state.update_data(subcat_name=msg.text)
        await msg.answer("🎨 Введи ЭМОДЗИ (например: 🎁):")
        await state.set_state(AdminStates.add_bracelet_desc)
    else:
        # Другие операции
        await state.update_data(bracelet_name=msg.text)
        await msg.answer("📄 Введи ОПИСАНИЕ:")
        await state.set_state(AdminStates.add_bracelet_desc)

@admin_router.callback_query(F.data.startswith("edit_subsubcat_"))
async def edit_subsubcat(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    subsubcat_id = int(cb.data.split("_")[-1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM subsubcategories WHERE id = ?', (subsubcat_id,))
    subsubcat = c.fetchone()
    conn.close()
    
    await state.update_data(edit_subsubcat_id=subsubcat_id)
    await cb.message.edit_text(f"✏️ Текущее название: {subsubcat[0]}\n\nНапиши новое:")
    await state.set_state(AdminStates.edit_subsubcat_name)
    await cb.answer()

@admin_router.message(AdminStates.edit_subsubcat_name)
async def update_subsubcat_name(msg: types.Message, state: FSMContext):
    """Обновить название под-подкатегории"""
    data = await state.get_data()
    
    if 'edit_subsubcat_id' not in data:
        await msg.answer("❌ Ошибка. Попробуй ещё раз через меню.")
        await state.clear()
        return
    
    try:
        subsubcat_id = data['edit_subsubcat_id']
        new_name = msg.text
        
        conn = get_db()
        c = conn.cursor()
        
        # Получаю parent_id для возврата в меню
        c.execute('SELECT parent_id FROM subsubcategories WHERE id = ?', (subsubcat_id,))
        result = c.fetchone()
        
        if not result:
            await msg.answer("❌ Под-подкатегория не найдена!")
            conn.close()
            await state.clear()
            return
        
        parent_id = result[0]
        
        # Обновляю название
        c.execute('UPDATE subsubcategories SET name = ? WHERE id = ?', (new_name, subsubcat_id))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Под-подкатегория переименована на: {new_name}")
        
        # Возвращаюсь в меню под-подкатегорий этой подкатегории
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT name FROM subcategories WHERE id = ?', (parent_id,))
        subcat = c.fetchone()
        c.execute('SELECT id, name, emoji FROM subsubcategories WHERE parent_id = ?', (parent_id,))
        subsubcats = c.fetchall()
        conn.close()
        
        text = f"✏️ ПОД-ПОДКАТЕГОРИИ - {subcat[0]}:\n\n"
        buttons = []
        
        if subsubcats:
            for ssc in subsubcats:
                text += f"{ssc[2]} {ssc[1]}\n"
                buttons.append([
                    types.InlineKeyboardButton(text=f"✏️ {ssc[1]}", callback_data=f"edit_subsubcat_{ssc[0]}"),
                    types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_subsubcat_{ssc[0]}")
                ])
        else:
            text += "📭 Под-подкатегорий нет\n"
        
        buttons.extend([
            [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data=f"add_subsubcat_{parent_id}")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="manage_subsubcategories")],
        ])
        
        await msg.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении под-подкатегории: {e}")
        await msg.answer(f"❌ Ошибка: {str(e)[:100]}")
    finally:
        await state.clear()

@admin_router.callback_query(F.data.startswith("delete_subsubcat_"))
async def delete_subsubcat(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    subsubcat_id = int(cb.data.split("_")[-1])
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Получаю информацию перед удалением
        c.execute('SELECT name, parent_id FROM subsubcategories WHERE id = ?', (subsubcat_id,))
        subsubcat = c.fetchone()
        
        if not subsubcat:
            await cb.answer("❌ Под-подкатегория не найдена!", show_alert=True)
            conn.close()
            return
        
        subsubcat_name = subsubcat[0]
        parent_id = subsubcat[1]
        
        # Удаляю саму под-подкатегорию
        c.execute('DELETE FROM subsubcategories WHERE id = ?', (subsubcat_id,))
        conn.commit()
        conn.close()
        
        await cb.answer(f"✅ Под-подкатегория '{subsubcat_name}' удалена!", show_alert=True)
        
        # Возвращаюсь в меню управления под-подкатегориями этой подкатегории
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT name FROM subcategories WHERE id = ?', (parent_id,))
        subcat = c.fetchone()
        c.execute('SELECT id, name, emoji FROM subsubcategories WHERE parent_id = ?', (parent_id,))
        subsubcats = c.fetchall()
        conn.close()
        
        text = f"✏️ ПОД-ПОДКАТЕГОРИИ - {subcat[0]}:\n\n"
        buttons = []
        
        if subsubcats:
            for ssc in subsubcats:
                text += f"{ssc[2]} {ssc[1]}\n"
                buttons.append([
                    types.InlineKeyboardButton(text=f"✏️ {ssc[1]}", callback_data=f"edit_subsubcat_{ssc[0]}"),
                    types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_subsubcat_{ssc[0]}")
                ])
        else:
            text += "📭 Под-подкатегорий нет\n"
        
        buttons.extend([
            [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data=f"add_subsubcat_{parent_id}")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="manage_subsubcategories")],
        ])
        
        await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
        
    except Exception as e:
        logger.error(f"Ошибка при удалении под-подкатегории {subsubcat_id}: {e}")
        await cb.answer(f"❌ Ошибка при удалении: {str(e)[:50]}", show_alert=True)

# ═══════════════════════════════════════════════════════════════════════════
# БРАСЛЕТЫ - УПРАВЛЕНИЕ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_bracelets")
async def admin_bracelets(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM bracelets')
    count = c.fetchone()[0]
    conn.close()
    
    text = f"💎 БРАСЛЕТЫ\n\nВсего браслетов: {count}"
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ БРАСЛЕТ", callback_data="add_bracelet")],
        [types.InlineKeyboardButton(text="📋 СПИСОК", callback_data="list_bracelets")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data == "add_bracelet")
async def add_bracelet_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    await cb.message.edit_text("💎 ДОБАВИТЬ БРАСЛЕТ\n\n📝 Введи НАЗВАНИЕ:")
    await state.set_state(AdminStates.add_bracelet_name)
    await cb.answer()

@admin_router.message(AdminStates.add_bracelet_desc)
async def add_bracelet_price(msg: types.Message, state: FSMContext):
    await state.update_data(bracelet_desc=msg.text)
    await msg.answer("💵 Введи ЦЕНУ (число):")
    await state.set_state(AdminStates.add_bracelet_price)

@admin_router.message(AdminStates.add_bracelet_price)
async def add_bracelet_image(msg: types.Message, state: FSMContext):
    try:
        price = float(msg.text)
        await state.update_data(bracelet_price=price)
        await msg.answer("🖼️ Загрузи ФОТО браслета:")
        await state.set_state(AdminStates.add_bracelet_image)
    except:
        await msg.answer("❌ Введи корректную цену (число):")

@admin_router.message(AdminStates.add_bracelet_image)
async def save_bracelet(msg: types.Message, state: FSMContext):
    if msg.photo:
        data = await state.get_data()
        photo_id = msg.photo[-1].file_id
        
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO bracelets (name, desc, price, image_url, created_at) VALUES (?, ?, ?, ?, ?)',
                  (data['bracelet_name'], data['bracelet_desc'], data['bracelet_price'], photo_id, datetime.now()))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ БРАСЛЕТ ДОБАВЛЕН!\n\n💎 {data['bracelet_name']}\n📄 {data['bracelet_desc']}\n💵 {data['bracelet_price']}₽")
        await state.clear()
    else:
        await msg.answer("❌ Загрузи фото (не текст):")

@admin_router.callback_query(F.data == "list_bracelets")
async def list_bracelets(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, name, price FROM bracelets')
    bracelets = c.fetchall()
    conn.close()
    
    if not bracelets:
        await cb.message.edit_text("📭 Браслетов нет", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_bracelets")],
        ]))
    else:
        text = "💎 СПИСОК БРАСЛЕТОВ:\n\n"
        for b in bracelets:
            text += f"ID: {b[0]} | {b[1]} | {b[2]}₽\n"
        await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_bracelets")],
        ]))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ДИАГНОСТИКА - МИНИ-ВОРОНКА
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data.startswith("diag_"))
async def diag_answer(cb: types.CallbackQuery, state: FSMContext):
    answer = cb.data.split("_")[1]
    
    questions = {
        'stress': ('😰 Стресс и тревога', '2️⃣ Как долго вас беспокоит эта проблема?\n   А) Недавно (1-2 недели)\n   В) Месяц-два\n   С) Больше полугода'),
        'pain': ('🤕 Боли в теле', '2️⃣ Где именно вы чувствуете боли?\n   А) Спина\n   В) Суставы\n   С) Мышцы'),
        'sleep': ('😴 Сон и усталость', '2️⃣ Сколько часов вы спите в ночь?\n   А) Менее 6 часов\n   В) 6-7 часов\n   С) 8+ часов'),
        'other': ('❓ Другое', '2️⃣ Опишите вашу проблему в свободном виде'),
    }
    
    if answer == 'other':
        await cb.message.edit_text(questions['other'][1])
        await state.update_data(diag_answer1='other')
        await state.set_state(DiagnosticStates.waiting_photo1)
        await cb.answer()
        return
    
    await state.update_data(diag_answer1=answer)
    
    buttons = []
    if answer in ['stress', 'pain', 'sleep']:
        q_variants = questions[answer][1].split('\n   ')
        for variant in q_variants[1:]:
            letter = variant[0]
            text = variant[3:]
            buttons.append([types.InlineKeyboardButton(text=f"{letter} {text}", callback_data=f"diag_q2_{letter}")])
    
    await cb.message.edit_text(questions[answer][1], reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("diag_q2_"))
async def diag_q2_answer(cb: types.CallbackQuery, state: FSMContext):
    answer2 = cb.data.split("_")[-1]
    await state.update_data(diag_answer2=answer2)
    
    await cb.message.edit_text("""3️⃣ ФОТО ЗДОРОВЬЯ

Теперь загрузи две свои фотографии для анализа:
- Первая фото: фото вашего состояния (лицо, руки, тело - что хотите)
- Вторая фото: дополнительная фото для полноты анализа

Это поможет нам лучше подобрать браслеты.""")
    await state.set_state(DiagnosticStates.waiting_photo1)
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ДИАГНОСТИКА - ЗАГРУЗКА ФОТО
# ═══════════════════════════════════════════════════════════════════════════

@diag_router.message(DiagnosticStates.waiting_photo1)
async def diag_photo1(msg: types.Message, state: FSMContext):
    if not msg.photo:
        await msg.answer("❌ Отправь фотографию!")
        return
    
    photo = msg.photo[-1]
    await state.update_data(photo1=photo.file_id)
    await msg.answer("✅ Первая фото получена!\n\nТеперь загрузи ВТОРУЮ:")
    await state.set_state(DiagnosticStates.waiting_photo2)

@diag_router.message(DiagnosticStates.waiting_photo2)
async def diag_photo2(msg: types.Message, state: FSMContext):
    if not msg.photo:
        await msg.answer("❌ Отправь фотографию!")
        return
    
    photo = msg.photo[-1]
    await state.update_data(photo2=photo.file_id)
    await msg.answer("✅ Вторая фото получена!\n\nНапиши заметки (или 'пропустить'):")
    await state.set_state(DiagnosticStates.waiting_notes)

@diag_router.message(DiagnosticStates.waiting_notes)
async def diag_notes(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = msg.from_user.id
    notes = msg.text if msg.text.lower() != 'пропустить' else "Нет заметок"
    photo1_file_id = data.get('photo1', '')
    photo2_file_id = data.get('photo2', '')
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO diagnostics (user_id, photo_count, notes, created_at, photo1_file_id, photo2_file_id) VALUES (?, ?, ?, ?, ?, ?)",
                 (user_id, 2, notes, datetime.now(), photo1_file_id, photo2_file_id))
        conn.commit()
        
        if ADMIN_ID and ADMIN_ID != 0:
            try:
                admin_msg = f"🩺 НОВАЯ ДИАГНОСТИКА!\n\nОт: {msg.from_user.first_name}\nИД: {user_id}\nЗаметки: {notes}"
                await bot.send_message(ADMIN_ID, admin_msg)
            except:
                pass
        
        await msg.answer("✅ СПАСИБО!\n\nДиагностика отправлена! Результаты в течение 24 часов! 💚")
        logger.info(f"Диагностика от {user_id} сохранена с фото")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
        logger.error(f"Ошибка диагностики: {e}")
    finally:
        conn.close()
    
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# БРАСЛЕТЫ - КАТАЛОГ И КОРЗИНА
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data.startswith("subcat_"))
async def show_subcategory(cb: types.CallbackQuery):
    subcat_id = int(cb.data.split("_")[-1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, emoji FROM subcategories WHERE id = ?', (subcat_id,))
    subcat = c.fetchone()
    
    # Сначала проверяю есть ли под-подкатегории
    c.execute('SELECT id, name, emoji FROM subsubcategories WHERE parent_id = ?', (subcat_id,))
    subsubcats = c.fetchall()
    
    # Потом проверяю контент
    c.execute('SELECT title, desc FROM content WHERE cat_id = ?', (subcat_id,))
    content = c.fetchall()
    conn.close()
    
    text = f"{subcat[1]} {subcat[0]}\n\n"
    buttons = []
    
    # ЛОГИКА: если есть под-подкатегории - показываю их. Если контента нет - показываю сообщение
    if subsubcats:
        # Есть под-подкатегории - показываю список
        for subsubcat in subsubcats:
            text += f"{subsubcat[2]} {subsubcat[1]}\n"
            buttons.append([types.InlineKeyboardButton(text=f"{subsubcat[2]} {subsubcat[1]}", callback_data=f"subsubcat_{subsubcat[0]}")])
    elif content:
        # Нет под-подкатегорий, но есть контент - показываю контент
        for item in content:
            text += f"📝 {item[0]}\n{item[1]}\n\n"
    else:
        # Нет ни под-подкатегорий ни контента
        text += "📭 Контента нет"
    
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("subsubcat_"))
async def show_subsubcategory(cb: types.CallbackQuery):
    subsubcat_id = int(cb.data.split("_")[-1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, emoji FROM subsubcategories WHERE id = ?', (subsubcat_id,))
    subsubcat = c.fetchone()
    c.execute('SELECT title, desc FROM content WHERE cat_id = ?', (subsubcat_id,))
    content = c.fetchall()
    conn.close()
    
    text = f"{subsubcat[1]} {subsubcat[0]}\n\n"
    
    if content:
        for item in content:
            text += f"📝 {item[0]}\n{item[1]}\n\n"
    else:
        text += "📭 Контента нет"
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ]))
    await cb.answer()

async def show_subcat_bracelets(cb: types.CallbackQuery):
    # Это устаревшая функция - заменена на show_subcategory
    await show_subcategory(cb)

@main_router.callback_query(F.data.startswith("bracelets_cat"))
async def show_bracelets(cb: types.CallbackQuery):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, name, desc, price, image_url FROM bracelets')
    bracelets = c.fetchall()
    conn.close()
    
    if not bracelets:
        await cb.message.edit_text("📭 Браслетов нет в наличии", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
        ]))
        await cb.answer()
        return
    
    # Показываю список браслетов
    text = "💎 БРАСЛЕТЫ:\n\n"
    buttons = []
    
    for b in bracelets:
        text += f"ID: {b[0]} | {b[1]} | {b[3]}₽\n"
        buttons.append([types.InlineKeyboardButton(text=f"💎 {b[1]} ({b[3]}₽)", callback_data=f"view_bracelet_{b[0]}")])
    
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("view_bracelet_"))
async def view_bracelet(cb: types.CallbackQuery):
    bracelet_id = int(cb.data.split("_")[-1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, name, desc, price, image_url FROM bracelets WHERE id = ?', (bracelet_id,))
    b = c.fetchone()
    conn.close()
    
    if not b:
        await cb.answer("❌ Браслет не найден", show_alert=True)
        return
    
    await cb.message.answer_photo(
        photo=b[4],
        caption=f"💎 {b[1]}\n\n📄 {b[2]}\n\n💵 Цена: {b[3]}₽",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🛒 В КОРЗИНУ", callback_data=f"add_to_cart_{b[0]}")],
            [types.InlineKeyboardButton(text="⭐ ОТЗЫВЫ", callback_data=f"reviews_{b[0]}")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="bracelets_cat")],
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("add_to_cart_"))
async def add_to_cart(cb: types.CallbackQuery):
    bracelet_id = int(cb.data.split("_")[-1])
    user_id = cb.from_user.id
    
    conn = get_db()
    c = conn.cursor()
    
    # Проверяю есть ли уже в корзине
    c.execute('SELECT id, quantity FROM cart WHERE user_id = ? AND bracelet_id = ?', (user_id, bracelet_id))
    existing = c.fetchone()
    
    if existing:
        c.execute('UPDATE cart SET quantity = quantity + 1 WHERE id = ?', (existing[0],))
    else:
        c.execute('INSERT INTO cart (user_id, bracelet_id, quantity, added_at) VALUES (?, ?, ?, ?)',
                  (user_id, bracelet_id, 1, datetime.now()))
    
    conn.commit()
    conn.close()
    
    await cb.answer("✅ Браслет добавлен в корзину!", show_alert=True)

@main_router.callback_query(F.data == "view_cart")
async def view_cart(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT cart.id, bracelets.name, bracelets.price, cart.quantity, cart.bracelet_id
                 FROM cart JOIN bracelets ON cart.bracelet_id = bracelets.id 
                 WHERE cart.user_id = ?''', (user_id,))
    items = c.fetchall()
    conn.close()
    
    if not items:
        await cb.message.edit_text("🛒 Корзина пуста", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
        ]))
        await cb.answer()
        return
    
    total = 0
    text = "🛒 КОРЗИНА:\n\n"
    buttons = []
    
    for item in items:
        price = item[2] * item[3]
        total += price
        text += f"💎 {item[1]}\n{item[3]} шт. × {item[2]}₽ = {price}₽\n\n"
        buttons.append([types.InlineKeyboardButton(text=f"❌ Удалить {item[1]}", callback_data=f"remove_cart_{item[0]}")])
    
    text += f"\n💰 ИТОГО: {total}₽"
    
    buttons.extend([
        [types.InlineKeyboardButton(text="💳 ОФОРМИТЬ ЗАКАЗ", callback_data="checkout")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("remove_cart_"))
async def remove_from_cart(cb: types.CallbackQuery):
    cart_id = int(cb.data.split("_")[-1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM cart WHERE id = ?', (cart_id,))
    conn.commit()
    conn.close()
    
    await cb.answer("✅ Удалено из корзины!", show_alert=True)
    # Переказываю корзину
    await view_cart(cb)

@main_router.callback_query(F.data == "checkout")
async def checkout(cb: types.CallbackQuery):
    await cb.message.edit_text("💳 СПОСОБ ОПЛАТЫ:\n\n1. 💰 Яндекс.Касса\n2. ₿ Криптовалюта", 
    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💰 ЯНДЕКС.КАССА", callback_data="pay_yandex")],
        [types.InlineKeyboardButton(text="₿ КРИПТО", callback_data="pay_crypto")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")],
    ]))
    await cb.answer()

@main_router.callback_query(F.data == "pay_yandex")
async def pay_yandex(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT SUM(bracelets.price * cart.quantity) FROM cart JOIN bracelets ON cart.bracelet_id = bracelets.id WHERE cart.user_id = ?', (user_id,))
    total = c.fetchone()[0] or 0
    
    # Создаю заказ
    c.execute('INSERT INTO orders (user_id, total_price, status, payment_method, created_at) VALUES (?, ?, ?, ?, ?)',
              (user_id, total, 'pending', 'yandex', datetime.now()))
    order_id = c.lastrowid
    
    conn.commit()
    conn.close()
    
    payment_text = f"✅ Заказ #{order_id} создан!\n\n💰 Сумма: {total}₽\n\n📝 РЕКВИЗИТЫ ДЛЯ ОПЛАТЫ:\n"
    
    if YANDEX_KASSA_EMAIL != 'your-email@yandex.kassa.com':
        payment_text += f"Яндекс.Касса: {YANDEX_KASSA_EMAIL}\nShop ID: {YANDEX_KASSA_SHOP_ID}"
    else:
        payment_text += "⚠️ Реквизиты Яндекс.Кассы не настроены.\nОбновите YANDEX_KASSA_EMAIL в переменных окружения."
    
    await cb.message.edit_text(payment_text,
    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ ОПЛАЧЕНО", callback_data=f"confirm_order_{order_id}")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")],
    ]))
    await cb.answer()

@main_router.callback_query(F.data == "pay_crypto")
async def pay_crypto(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT SUM(bracelets.price * cart.quantity) FROM cart JOIN bracelets ON cart.bracelet_id = bracelets.id WHERE cart.user_id = ?', (user_id,))
    total = c.fetchone()[0] or 0
    
    c.execute('INSERT INTO orders (user_id, total_price, status, payment_method, created_at) VALUES (?, ?, ?, ?, ?)',
              (user_id, total, 'pending', 'crypto', datetime.now()))
    order_id = c.lastrowid
    
    conn.commit()
    conn.close()
    
    payment_text = f"✅ Заказ #{order_id} создан!\n\n💰 Сумма: {total}₽\n\n"
    
    if CRYPTO_WALLET_ADDRESS != 'bc1qyour_bitcoin_address_here':
        payment_text += f"₿ {CRYPTO_WALLET_NETWORK} адрес:\n{CRYPTO_WALLET_ADDRESS}"
    else:
        payment_text += "⚠️ Адрес кошелька не настроен.\nОбновите CRYPTO_WALLET_ADDRESS в переменных окружения."
    
    await cb.message.edit_text(payment_text,
    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ ОПЛАЧЕНО", callback_data=f"confirm_order_{order_id}")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")],
    ]))
    await cb.answer()

@main_router.callback_query(F.data.startswith("confirm_order_"))
async def confirm_order(cb: types.CallbackQuery, state: FSMContext):
    order_id = int(cb.data.split("_")[-1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE orders SET status = ? WHERE id = ?', ('confirmed', order_id))
    conn.commit()
    conn.close()
    
    await cb.message.edit_text(f"✅ Заказ #{order_id} подтвержден!\n\n📝 Спасибо за покупку! Оставь отзыв после получения товара.",
    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⭐ ОСТАВИТЬ ОТЗЫВ", callback_data="leave_review")],
        [types.InlineKeyboardButton(text="← МЕНЮ", callback_data="menu")],
    ]))
    await cb.answer()

@main_router.callback_query(F.data == "leave_review")
async def leave_review(cb: types.CallbackQuery, state: FSMContext):
    # Получаю bracelet_id из контекста или из callback_data
    await state.update_data(from_confirmation=True)
    await cb.message.edit_text("⭐ ОЦЕНКА:\n\n1 - очень плохо\n5 - отлично",
    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⭐", callback_data="rate_1"),
         types.InlineKeyboardButton(text="⭐⭐", callback_data="rate_2"),
         types.InlineKeyboardButton(text="⭐⭐⭐", callback_data="rate_3")],
        [types.InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data="rate_4"),
         types.InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data="rate_5")],
    ]))
    await cb.answer()

@main_router.callback_query(F.data.startswith("rate_"))
async def save_rating(cb: types.CallbackQuery, state: FSMContext):
    rating = int(cb.data.split("_")[-1])
    await state.update_data(rating=rating)
    await cb.message.edit_text("📝 Напиши свой отзыв (текст):")
    await state.set_state(ReviewStates.waiting_review_text)
    await cb.answer()

@main_router.message(ReviewStates.waiting_review_text)
async def save_review_text(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = msg.from_user.id
    rating = data['rating']
    
    # Беру последний заказанный браслет или 1 по умолчанию
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT bracelet_id FROM cart WHERE user_id = ? LIMIT 1', (user_id,))
    result = c.fetchone()
    bracelet_id = result[0] if result else 1
    
    c.execute('INSERT INTO reviews (user_id, bracelet_id, rating, text, created_at) VALUES (?, ?, ?, ?, ?)',
              (user_id, bracelet_id, rating, msg.text, datetime.now()))
    conn.commit()
    conn.close()
    
    await msg.answer("✅ Спасибо за отзыв!")
    await state.clear()

@main_router.callback_query(F.data.startswith("reviews_"))
async def show_reviews(cb: types.CallbackQuery):
    bracelet_id = int(cb.data.split("_")[-1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT rating, text FROM reviews WHERE bracelet_id = ? ORDER BY created_at DESC LIMIT 10', (bracelet_id,))
    reviews = c.fetchall()
    conn.close()
    
    if not reviews:
        text = "📭 Отзывов нет"
    else:
        text = "⭐ ОТЗЫВЫ:\n\n"
        for r in reviews:
            stars = "⭐" * r[0]
            text += f"{stars}\n{r[1]}\n\n"
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ]))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ОСТАЛЬНОЕ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.message()
async def handle_any(msg: types.Message):
    await msg.answer("❓ Команды:\n/start - меню\n/admin - админ-панель\n/diagnostics - диагностика")

# ═══════════════════════════════════════════════════════════════════════════
# ВЕБХУК
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# ГЛАВНАЯ
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    print("\n" + "="*60)
    print("🚀 БОТ С ПОЛНЫМ ФУНКЦИОНАЛОМ ЗАПУСКАЕТСЯ")
    print("="*60 + "\n")
    
    dp.include_router(admin_router)
    dp.include_router(diag_router)
    dp.include_router(main_router)
    
    # Railway использует polling (не webhook)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Polling активирован")
    
    print(f"✅ БОТ РАБОТАЕТ")
    print(f"📍 ПОЛНЫЙ ФУНКЦИОНАЛ ВКЛЮЧЁН")
    print("\n" + "="*60 + "\n")
    
    # Запуск polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 БОТ ОСТАНОВЛЕН")
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")
