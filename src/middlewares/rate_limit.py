"""
Middleware для ограничения частоты запросов.
"""
import time
from typing import Dict, Callable, Awaitable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

class RateLimitMiddleware(BaseMiddleware):
    """
    Ограничивает количество запросов от одного пользователя.
    """
    
    def __init__(self, rate_limit: float = 0.5, burst_limit: int = 5):
        self.rate_limit = rate_limit
        self.burst_limit = burst_limit
        self.user_requests: Dict[int, list] = {}
        
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id
        
        if not user_id:
            return await handler(event, data)
        
        now = time.time()
        
        if user_id in self.user_requests:
            self.user_requests[user_id] = [
                ts for ts in self.user_requests[user_id] 
                if now - ts < 60
            ]
        else:
            self.user_requests[user_id] = []
        
        if len(self.user_requests[user_id]) >= self.burst_limit:
            if isinstance(event, Message):
                await event.answer("⏳ Слишком много сообщений. Подождите минуту.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⏳ Слишком часто", show_alert=False)
            return
        
        if self.user_requests[user_id]:
            last_request = self.user_requests[user_id][-1]
            if now - last_request < self.rate_limit:
                if isinstance(event, CallbackQuery):
                    await event.answer("⏳", show_alert=False)
                return
        
        self.user_requests[user_id].append(now)
        
        return await handler(event, data)