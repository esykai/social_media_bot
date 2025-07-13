from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.user_state import UserState


def get_platform_status(platforms: dict) -> str:
    """Получить эмодзи в зависимости активна платформа или нет"""
    telegram_status = "✅" if platforms["telegram"] else "❌"
    x_status = "✅" if platforms["x"] else "❌"
    return f"📱 Telegram {telegram_status} | 🐦 X.com {x_status}"

def get_main_menu_keyboard(state: UserState) -> InlineKeyboardMarkup:
    """Создание мега крутой клавы"""
    keyboard = []

    keyboard.append([
        InlineKeyboardButton(text="📝 Добавить текст", callback_data="add_text"),
        InlineKeyboardButton(text="🖼️ Добавить медиа", callback_data="add_media")
    ])

    if state.description or state.media_files:
        keyboard.append([
            InlineKeyboardButton(text="📋 Предпросмотр", callback_data="preview"),
            InlineKeyboardButton(text="🗑️ Очистить все", callback_data="clear_all")
        ])

    keyboard.append([
        InlineKeyboardButton(
            text=f"📱 Telegram {'✅' if state.selected_platforms['telegram'] else '❌'}",
            callback_data="toggle_telegram"
        ),
        InlineKeyboardButton(
            text=f"🐦 X.com {'✅' if state.selected_platforms['x'] else '❌'}",
            callback_data="toggle_x"
        )
    ])

    if (state.description or state.media_files) and any(state.selected_platforms.values()):
        keyboard.append([
            InlineKeyboardButton(text="🚀 Опубликовать", callback_data="confirm_post")
        ])

    keyboard.append([
        InlineKeyboardButton(text="❓ Помощь", callback_data="help")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_media_menu_keyboard(state: UserState) -> InlineKeyboardMarkup:
    """Создания медиа крутого меню"""
    keyboard = []

    if state.media_files:
        keyboard.append([
            InlineKeyboardButton(text="📝 Добавить описание", callback_data="add_description"),
            InlineKeyboardButton(text="✏️ Изменить описание", callback_data="edit_description")
        ])

        keyboard.append([
            InlineKeyboardButton(text="🗑️ Удалить последнее", callback_data="remove_last_media"),
            InlineKeyboardButton(text="🗑️ Очистить все медиа", callback_data="clear_media")
        ])

    keyboard.append([
        InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_content_info(state: UserState) -> str:
    """Получить информацию об контенте"""
    info = "📊 **Текущий контент:**\n\n"

    if state.description:
        preview = state.description[:100] + "..." if len(state.description) > 100 else state.description
        info += f"📝 **Текст:** {preview}\n"
        info += f"📏 **Длина:** {len(state.description)} символов\n\n"

    if state.media_files:
        info += f"🖼️ **Медиа файлов:** {len(state.media_files)}\n"
        for i, file in enumerate(state.media_files, 1):
            file_type = "📷 Фото" if file.endswith('.jpg') else "🎥 Видео"
            info += f"  {i}. {file_type}\n"
        info += "\n"

    info += f"🎯 **Платформы:** {get_platform_status(state.selected_platforms)}"

    return info
