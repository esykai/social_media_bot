import os
import logging

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from utils.user_state import UserState, user_states
from utils.keyboards import get_main_menu_keyboard, get_content_info
from utils.video_compressor import compress_video_with_format
from states import PostStates
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


@router.message(Command("status"))
async def status_command(message: types.Message):
    """Обработка команды /status"""
    user_id = message.from_user.id

    if not await check_access(user_id):
        await message.reply("🚫 Доступ ограничен для авторизованных пользователей.")
        return

    state = await get_user_state(user_id)
    status_text = get_content_info(state)

    await message.reply(status_text, parse_mode="Markdown")


@router.message(F.text, PostStates.waiting_for_text)
async def handle_text_input(message: types.Message, state: FSMContext):
    """Обработка текстового ввода"""
    user_id = message.from_user.id

    if not await check_access(user_id):
        await message.reply("🚫 Доступ ограничен для авторизованных пользователей.")
        return

    text = message.text

    if len(text) > MAX_TEXT_LENGTH:
        await message.reply(f"⚠️ Текст слишком длинный! Максимум {MAX_TEXT_LENGTH} символов.")
        return

    user_state = await get_user_state(user_id)
    user_state.description = text

    await state.clear()

    main_text = "✅ **Текст добавлен!**\n\n" + get_content_info(user_state)
    keyboard = get_main_menu_keyboard(user_state)

    await message.reply(main_text, reply_markup=keyboard, parse_mode="Markdown")


@router.message(F.photo)
async def handle_photo(message: types.Message):
    """Обработка фото-сообщений"""
    user_id = message.from_user.id

    if not await check_access(user_id):
        await message.reply("🚫 Доступ ограничен для авторизованных пользователей.")
        return

    user_state = await get_user_state(user_id)

    if len(user_state.media_files) >= MAX_MEDIA_FILES:
        await message.reply(f"⚠️ Максимум {MAX_MEDIA_FILES} медиафайлов!")
        return

    try:
        photo = message.photo[-1]
        file_info = await message.bot.get_file(photo.file_id)
        user_state.media_files.append(file_info.file_path)

        if message.caption:
            if len(message.caption) <= MAX_TEXT_LENGTH:
                user_state.description = message.caption
            else:
                await message.reply(f"⚠️ Подпись слишком длинная! Максимум {MAX_TEXT_LENGTH} символов.")

        response_text = f"📷 **Фото добавлено!**\n\n" + get_content_info(user_state)
        keyboard = get_main_menu_keyboard(user_state)

        await message.reply(response_text, reply_markup=keyboard, parse_mode="Markdown")

    except Exception as e:
        await message.reply(f"❌ Ошибка при обработке фото: {str(e)}")
        logging.error(f"Ошибка при обработке фото: {e}")


@router.message(F.video)
async def handle_video(message: types.Message):
    """Обработка видео-сообщений"""
    user_id = message.from_user.id

    if not await check_access(user_id):
        await message.reply("🚫 Доступ ограничен для авторизованных пользователей.")
        return

    user_state = await get_user_state(user_id)

    if len(user_state.media_files) >= MAX_MEDIA_FILES:
        await message.reply(f"⚠️ Максимум {MAX_MEDIA_FILES} медиафайлов!")
        return

    try:
        video = message.video
        file_info = await message.bot.get_file(video.file_id)
        file_path = file_info.file_path
        compressed_path = f"media/video_{user_id}_{video.file_id}_compressed.mp4"

        os.makedirs("media", exist_ok=True)

        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        final_path = file_path

        if file_size_mb > 30:
            await message.reply(f"🎥 Видео ({file_size_mb:.2f} МБ) превышает 30 МБ, начинается сжатие...")
            success = await compress_video_with_format(
                file_path, compressed_path, message, crf=23, preset="medium"
            )
            if success:
                final_path = compressed_path
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logging.debug(f"Удалён оригинальный файл: {file_path}")
            else:
                await message.reply("❌ Ошибка сжатия видео, используется оригинал")
                final_path = file_path
        else:
            await message.reply(f"🎥 Видео ({file_size_mb:.2f} МБ) не требует сжатия")
            final_path = file_path

        user_state.media_files.append(final_path)

        if message.caption:
            if len(message.caption) <= MAX_TEXT_LENGTH:
                user_state.description = message.caption
            else:
                await message.reply(f"⚠️ Подпись слишком длинная! Максимум {MAX_TEXT_LENGTH} символов.")

        response_text = f"🎥 **Видео добавлено!**\n\n" + get_content_info(user_state)
        keyboard = get_main_menu_keyboard(user_state)

        await message.reply(response_text, reply_markup=keyboard, parse_mode="Markdown")

    except Exception as e:
        await message.reply(f"❌ Ошибка при обработке видео: {str(e)}")
        logging.error(f"Ошибка при обработке видео: {e}")


@router.message()
async def handle_other_messages(message: types.Message):
    """Обработка неподдерживаемых сообщений"""
    user_id = message.from_user.id

    if not await check_access(user_id):
        await message.reply("🚫 Доступ ограничен для авторизованных пользователей.")
        return

    await message.reply(
        "🤔 **Неподдерживаемый тип контента**\n\n"
        "📱 Поддерживаются:\n"
        "• 📝 Текстовые сообщения\n"
        "• 📷 Фото (JPG, PNG)\n"
        "• 🎥 Видео (MP4, MOV)\n\n"
        "💡 Используйте /start для возврата в меню",
        parse_mode="Markdown",
    )
