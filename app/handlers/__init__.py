from aiogram import Router

from command_handlers import router as command_router
from callback_handlers import router as callback_router
from message_handlers import router as message_router

router = Router()
router.include_router(command_router)
router.include_router(callback_router)
router.include_router(message_router)
