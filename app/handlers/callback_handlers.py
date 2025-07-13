import logging
import os

from aiogram import Router, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ALLOWED_USER_ID, MAX_TEXT_LENGTH, MAX_MEDIA_FILES
from utils.user_state import UserState, user_states
from utils.keyboards import get_main_menu_keyboard, get_content_info
from utils.social_poster import post_to_telegram, post_to_x
from states import PostStates

router = Router()


async def check_access(user_id: int) -> bool:
    """Проверка доступа пользователя"""
    return user_id == ALLOWED_USER_ID


async def get_user_state(user_id: int) -> UserState:
    """Получить состояние пользователя"""
    if user_id not in user_states:
        user_states[user_id] = UserState()
    return user_states[user_id]


@router.callback_query(lambda c: c.data == "add_text")
async def add_text_callback(callback: types.CallbackQuery, state):
    """Обработка добавления текста"""
    user_id = callback.from_user.id

    if not await check_access(user_id):
        await callback.answer("🚫 Доступ запрещён")
        return

    await state.set_state(PostStates.waiting_for_text)

    await callback.message.edit_text(
        f"📝 **Введите текст для публикации:**\n\n"
        f"⚠️ Максимум {MAX_TEXT_LENGTH} символов\n"
        f"💡 Можно использовать эмодзи и форматирование",
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "add_media")
async def add_media_callback(callback: types.CallbackQuery):
    """Обработка добавления медиа"""
    user_id = callback.from_user.id

    if not await check_access(user_id):
        await callback.answer("🚫 Доступ запрещён")
        return

    user_state = await get_user_state(user_id)

    if len(user_state.media_files) >= MAX_MEDIA_FILES:
        await callback.answer(f"⚠️ Максимум {MAX_MEDIA_FILES} файлов")
        return

    user_state.current_mode = "adding_media"

    from ..utils.keyboards import get_media_menu_keyboard
    await callback.message.edit_text(
        f"🖼️ **Отправьте фото или видео:**\n\n"
        f"📊 Добавлено файлов: {len(user_state.media_files)}/{MAX_MEDIA_FILES}\n"
        f"📷 Поддержка: JPG, PNG\n"
        f"🎥 Поддержка: MP4, MOV\n\n"
        f"💡 Используйте кнопки ниже после загрузки",
        reply_markup=get_media_menu_keyboard(user_state),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "preview")
async def preview_callback(callback: types.CallbackQuery):
    """Предпросмотр публикации"""
    user_id = callback.from_user.id

    if not await check_access(user_id):
        await callback.answer("🚫 Доступ запрещён")
        return

    state = await get_user_state(user_id)
    preview_text = get_content_info(state)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

    await callback.message.edit_text(preview_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(lambda c: c.data == "clear_all")
async def clear_all_callback(callback: types.CallbackQuery):
    """Очистка всего содержимого"""
    user_id = callback.from_user.id

    if not await check_access(user_id):
        await callback.answer("🚫 Доступ запрещён")
        return

    state = await get_user_state(user_id)

    for file in state.media_files:
        if os.path.exists(file):
            try:
                os.remove(file)
                logging.debug(f"Удалён файл: {file}")
            except Exception as e:
                logging.error(f"Ошибка удаления файла {file}: {e}")

    platforms_backup = state.selected_platforms.copy()
    state.media_files = []
    state.description = ""
    state.selected_platforms = platforms_backup
    state.current_mode = "idle"

    main_text = "🗑️ **Контент очищен!**\n\n" + get_content_info(state)
    keyboard = get_main_menu_keyboard(state)

    await callback.message.edit_text(main_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer("✅ Всё удалено")


@router.callback_query(lambda c: c.data in ["toggle_telegram", "toggle_x"])
async def toggle_platform(callback: types.CallbackQuery):
    """Переключение платформы"""
    user_id = callback.from_user.id

    if not await check_access(user_id):
        await callback.answer("🚫 Доступ запрещён")
        return

    state = await get_user_state(user_id)
    platform = callback.data.replace("toggle_", "")

    state.selected_platforms[platform] = not state.selected_platforms[platform]

    if not any(state.selected_platforms.values()):
        state.selected_platforms[platform] = True
        await callback.answer("⚠️ Должна быть выбрана хотя бы одна платформа")
        return

    platform_name = "📱 Telegram" if platform == "telegram" else "🐦 X.com"
    status = "✅ включена" if state.selected_platforms[platform] else "❌ отключена"

    main_text = "🚀 **Публикация в соцсети**\n\n" + get_content_info(state)
    keyboard = get_main_menu_keyboard(state)

    await callback.message.edit_text(main_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer(f"{platform_name} {status}")


@router.callback_query(lambda c: c.data == "confirm_post")
async def confirm_post(callback: types.CallbackQuery):
    """Подтверждение и публикация"""
    user_id = callback.from_user.id

    if not await check_access(user_id):
        await callback.answer("🚫 Доступ запрещён")
        return

    state = await get_user_state(user_id)

    if not state.description and not state.media_files:
        await callback.answer("⚠️ Нет контента для публикации")
        return

    if not any(state.selected_platforms.values()):
        await callback.answer("⚠️ Выберите хотя бы одну платформу")
        return

    await callback.message.edit_text("🚀 Публикация началась...\n\n⏳ Пожалуйста, подождите")

    results = []

    try:
        if state.selected_platforms["telegram"]:
            try:
                success = await post_to_telegram(
                    callback.message.bot,
                    state.media_files,
                    bool(state.media_files),
                    state.description
                )
                results.append("✅ Telegram — опубликовано" if success else "❌ Telegram — ошибка")
            except Exception as e:
                results.append(f"❌ Telegram — ошибка: {str(e)}")
                logging.error(f"Ошибка при публикации в Telegram: {e}")

        if state.selected_platforms["x"]:
            try:
                success = await post_to_x(
                    state.media_files,
                    bool(state.media_files),
                    state.description
                )
                results.append("✅ X.com — опубликовано" if success else "❌ X.com — ошибка")
            except Exception as e:
                results.append(f"❌ X.com — ошибка: {str(e)}")
                logging.error(f"Ошибка при публикации в X.com: {e}")

        result_text = "📊 **Результаты публикации:**\n\n" + "\n".join(results)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
        ])
        await callback.message.edit_text(result_text, reply_markup=keyboard, parse_mode="Markdown")

    except Exception as e:
        error_text = f"❌ **Критическая ошибка:**\n\n{str(e)}"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Повторить", callback_data="confirm_post")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
        ])
        await callback.message.edit_text(error_text, reply_markup=keyboard, parse_mode="Markdown")
        logging.error(f"Критическая ошибка при публикации: {e}")

    finally:
        for file in state.media_files:
            if os.path.exists(file):
                try:
                    os.remove(file)
                    logging.debug(f"Удалён файл: {file}")
                except Exception as e:
                    logging.error(f"Ошибка удаления файла {file}: {e}")

        platforms_backup = state.selected_platforms.copy()
        state.media_files = []
        state.description = ""
        state.selected_platforms = platforms_backup
        state.current_mode = "idle"

    try:
        await callback.answer()
    except:
        pass


@router.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    user_id = callback.from_user.id

    if not await check_access(user_id):
        await callback.answer("🚫 Доступ запрещён")
        return

    state = await get_user_state(user_id)
    state.current_mode = "idle"

    main_text = "🚀 **Публикация в соцсети**\n\n" + get_content_info(state)
    keyboard = get_main_menu_keyboard(state)

    await callback.message.edit_text(main_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()
