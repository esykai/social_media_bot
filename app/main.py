import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage

from config import TELEGRAM_BOT_TOKEN
from handlers import command_handlers, callback_handlers, message_handlers

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

session = AiohttpSession(
    api=TelegramAPIServer.from_base('http://telegram-bot-api:8081')
)
bot = Bot(
    token=TELEGRAM_BOT_TOKEN,
    session=session
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

dp.include_router(command_handlers.router)
dp.include_router(callback_handlers.router)
dp.include_router(message_handlers.router)


async def main():
    try:
        logging.info("Starting Social Media Publisher Bot...")
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logging.error(f"Critical error: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())