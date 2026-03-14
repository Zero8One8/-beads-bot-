"""
Главный файл запуска бота.
Объединяет все роутеры и запускает polling.
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import Config
from src.database.db import db
from src.database.init import init_db
from src.utils.text_loader import ContentLoader
from src.middlewares.rate_limit import RateLimitMiddleware

# Импортируем все роутеры
from src.handlers import user
from src.handlers import shop
from src.handlers import diagnostic
from src.handlers import custom_order
from src.handlers import music
from src.handlers import workouts
from src.handlers import services
from src.handlers import gifts
from src.handlers import wishlist
from src.handlers import faq
from src.handlers import quiz
from src.handlers import stories
from src.handlers import club
from src.handlers import payment
from src.handlers import admin
from src.handlers import admin_diagnostic
from src.handlers import admin_products
from src.handlers import admin_promos
from src.handlers import admin_services
from src.handlers import admin_club
from src.handlers import admin_broadcast
from src.handlers import admin_stats
from src.handlers import admin_orders
from src.handlers import admin_export
from src.handlers import admin_scheduler
from src.handlers import admin_site
from src.handlers import admin_settings

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Config.STORAGE_PATH / 'bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

bot = Bot(
    token=Config.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher(storage=MemoryStorage())

# Регистрируем middleware
dp.message.middleware(RateLimitMiddleware())
dp.callback_query.middleware(RateLimitMiddleware())

# Регистрируем все роутеры
dp.include_router(user.router)
dp.include_router(shop.router)
dp.include_router(diagnostic.router)
dp.include_router(custom_order.router)
dp.include_router(music.router)
dp.include_router(workouts.router)
dp.include_router(services.router)
dp.include_router(gifts.router)
dp.include_router(wishlist.router)
dp.include_router(faq.router)
dp.include_router(quiz.router)
dp.include_router(stories.router)
dp.include_router(club.router)
dp.include_router(payment.router)
dp.include_router(admin.router)
dp.include_router(admin_diagnostic.router)
dp.include_router(admin_products.router)
dp.include_router(admin_promos.router)
dp.include_router(admin_services.router)
dp.include_router(admin_club.router)
dp.include_router(admin_broadcast.router)
dp.include_router(admin_stats.router)
dp.include_router(admin_orders.router)
dp.include_router(admin_export.router)
dp.include_router(admin_scheduler.router)
dp.include_router(admin_site.router)
dp.include_router(admin_settings.router)

# Фоновые задачи
async def background_tasks():
    from src.services.background import (
        check_pending_orders,
        check_birthdays,
        check_expired_subscriptions,
        check_cart_reminders
    )
    await asyncio.gather(
        check_pending_orders(),
        check_birthdays(),
        check_expired_subscriptions(),
        check_cart_reminders(),
        return_exceptions=True
    )

async def on_startup():
    logger.info("="*50)
    logger.info("🚀 ЗАПУСК БОТА MAGIC STONES V6.0")
    logger.info("="*50)
    
    # Инициализация БД
    init_db()
    logger.info("✅ База данных инициализирована")
    
    # Предзагрузка контента
    stones = ContentLoader.load_all_stones()
    logger.info(f"📚 Загружено камней: {len(stones)}")
    
    # Запуск фоновых задач
    asyncio.create_task(background_tasks())
    
    logger.info("✅ Бот готов к работе")

async def on_shutdown():
    logger.info("🛑 Остановка бота...")
    db.close_all()
    logger.info("👋 Все соединения закрыты")

async def main():
    await on_startup()
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await on_shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.exception(f"💥 Критическая ошибка: {e}")