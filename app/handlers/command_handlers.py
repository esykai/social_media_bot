import os
import logging

from aiogram import Router, types
from aiogram.filters import CommandStart, Command

from utils.user_state import UserState, user_states
from utils.keyboards import get_main_menu_keyboard
from config import ALLOWED_USER_ID, MAX_MEDIA_FILES, MAX_TEXT_LENGTH

router = Router()


async def check_access(user_id: int) -> bool:
    """Проверка доступа пользователя"""
    return user_id == ALLOWED_USER_ID


async def get_user_state(user_id: int) -> UserState:
    """Получить состояние пользователя"""
    if user_id not in user_states:
        user_states[user_id] = UserState()
    return user_states[user_id]


@router.message(CommandStart())
async def start(message: types.Message):
    """Обработка команды /start"""
    user_id = message.from_user.id

    if not await check_access(user_id):
        await message.reply("🚫 Доступ ограничен для авторизованных пользователей.")
        return

    state = await get_user_state(user_id)

    welcome_text = (
        "🚀 **Добро пожаловать в Social Media Publisher!**\n\n"
        "📱 Публикация контента в Telegram и X.com\n"
        "🖼️ Поддержка фото и видео\n"
        "📝 Добавление текстовых описаний\n"
        "⚙️ Гибкие настройки публикации\n\n"
        "👇 Выберите действие:"
    )

    keyboard = get_main_menu_keyboard(state)
    sent_message = await message.reply(
        welcome_text, reply_markup=keyboard, parse_mode="Markdown"
    )
    state.menu_message_id = sent_message.message_id


@router.message(Command("help"))
async def help_command(message: types.Message):
    """Обработка команды /help"""
    user_id = message.from_user.id

    if not await check_access(user_id):
        await message.reply("🚫 Доступ ограничен для авторизованных пользователей.")
        return

    help_text = (
        "❓ **Помощь по использованию бота:**\n\n"
        "🔧 **Команды:**\n"
        "• `/start` - Запустить бота\n"
        "• `/help` - Это сообщение помощи\n"
        "• `/clear` - Очистить всё\n"
        "• `/status` - Показать статус\n\n"
        "📱 **Возможности:**\n"
        "• Публикация в Telegram и X.com\n"
        "• Поддержка фото и видео\n"
        "• Добавление текстовых описаний\n"
        "• Предпросмотр контента\n"
        "• Выбор платформ для публикации\n\n"
        "⚠️ **Ограничения:**\n"
        f"• Максимум {MAX_MEDIA_FILES} медиафайлов\n"
        f"• Максимум {MAX_TEXT_LENGTH} символов в тексте\n"
        "• Поддерживаются только JPG и MP4 файлы"
    )

    await message.reply(help_text, parse_mode="Markdown")


@router.message(Command("clear"))
async def clear_command(message: types.Message):
    """Обработка команды /clear"""
    user_id = message.from_user.id

    if not await check_access(user_id):
        await message.reply("🚫 Доступ ограничен для авторизованных пользователей.")
        return

    state = await get_user_state(user_id)

    for file in state.media_files:
        if os.path.exists(file):
            try:
                os.remove(file)
                logging.debug(f"Удалён файл: {file}")
            except Exception as e:
                logging.error(f"Ошибка удаления файла {file}: {e}")

    user_states[user_id] = UserState()
    await message.reply("🗑️ Сессия полностью очищена.")

