"""
Планировщик автоматической публикации постов.
"""
import asyncio
import logging
from datetime import datetime
from aiogram import Bot

from src.database.db import db
from src.database.models import ScheduledPostModel
from src.utils.text_loader import ContentLoader
from src.config import Config

logger = logging.getLogger(__name__)

class PostScheduler:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.running = False
        self.task = None
        self.channel_id = Config.CHANNEL_ID
    
    async def start(self):
        self.running = True
        self.task = asyncio.create_task(self._run())
        logger.info("Планировщик постов запущен")
    
    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
        logger.info("Планировщик постов остановлен")
    
    async def _run(self):
        while self.running:
            try:
                await self._check_schedule()
            except Exception as e:
                logger.error(f"Ошибка в планировщике: {e}")
            await asyncio.sleep(60)
    
    async def _check_schedule(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:00')
        with db.cursor() as c:
            c.execute("""
                SELECT id, post_id, channel_id
                FROM scheduled_posts
                WHERE status = 'pending' AND scheduled_time <= ?
                LIMIT 5
            """, (now,))
            pending = c.fetchall()
        
        for post in pending:
            await self._publish_post(post['id'], post['post_id'], post['channel_id'])
    
    async def _publish_post(self, schedule_id: int, post_id: str, channel_id: str):
        content = ContentLoader.load_post(post_id)
        if not content:
            logger.error(f"Пост {post_id} не найден")
            with db.cursor() as c:
                c.execute("UPDATE scheduled_posts SET status='failed', error='Файл не найден' WHERE id=?", (schedule_id,))
            return
        
        target = channel_id if channel_id else self.channel_id
        if not target:
            logger.warning("Не указан channel_id для публикации")
            return
        
        try:
            await self.bot.send_message(target, content, parse_mode='HTML')
            with db.cursor() as c:
                c.execute("""
                    UPDATE scheduled_posts 
                    SET status='published', published_at=? 
                    WHERE id=?
                """, (datetime.now(), schedule_id))
            logger.info(f"Пост {post_id} опубликован в {target}")
        except Exception as e:
            logger.error(f"Ошибка публикации {post_id}: {e}")
            with db.cursor() as c:
                c.execute("UPDATE scheduled_posts SET status='failed', error=? WHERE id=?", (str(e), schedule_id))