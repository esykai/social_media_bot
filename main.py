import os
import asyncio
import re

from aiogram import Bot, Dispatcher, types, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from ffmpeg import ffmpeg
import logging

from config import TELEGRAM_BOT_TOKEN, MAX_MEDIA_FILES, MAX_TEXT_LENGTH, ALLOWED_USER_ID
from social_poster import post_to_telegram, post_to_x

session = AiohttpSession(
    api=TelegramAPIServer.from_base('http://telegram-bot-api:8081')
)
bot = Bot(
    token=TELEGRAM_BOT_TOKEN,
    session=session
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class PostStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_media = State()
    editing_content = State()


class UserState:
    def __init__(self):
        self.media_files = []
        self.description = ""
        self.selected_platforms = {"telegram": True, "x": True}
        self.menu_message_id = None
        self.current_mode = "idle"  # idle, adding_media, adding_text


user_states = {}


async def check_access(user_id: int) -> bool:
    """Проверка доступа пользователя"""
    return user_id == ALLOWED_USER_ID


async def get_user_state(user_id: int) -> UserState:
    """Получение состояния пользователя"""
    if user_id not in user_states:
        user_states[user_id] = UserState()
    return user_states[user_id]


def get_platform_status(platforms: dict) -> str:
    """Получение статуса платформ с эмодзи"""
    telegram_status = "✅" if platforms["telegram"] else "❌"
    x_status = "✅" if platforms["x"] else "❌"
    return f"📱 Telegram {telegram_status} | 🐦 X.com {x_status}"


def get_main_menu_keyboard(state: UserState) -> InlineKeyboardMarkup:
    """Создание главного меню"""
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
    """Создание меню для работы с медиа"""
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
    """Получение информации о контенте"""
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


async def compress_video(
    input_path: str,
    output_path: str,
    message: types.Message,
    ffmpeg_path: str = "ffmpeg",
    crf: int = 23,
    preset: str = "medium",
    audio_bitrate: str = "128k"
) -> bool:
    """Сжимает видео с использованием FFmpeg и отображает прогресс в Telegram."""
    if not os.path.exists(input_path):
        logging.error(f"Файл {input_path} не найден")
        await message.reply(f"❌ Ошибка: Файл {input_path} не найден.")
        return False
    if not os.path.exists(ffmpeg_path):
        logging.error(f"FFmpeg не найден по пути {ffmpeg_path}")
        await message.reply(f"❌ Ошибка: FFmpeg не найден по пути {ffmpeg_path}.")
        return False

    progress_message = None
    try:
        ff = ffmpeg.FFmpeg(executable=ffmpeg_path)
        ff.input(input_path)

        progress_message = await message.reply("⏳ Сжатие видео началось... 0%")

        def handle_progress(line):
            match = re.search(r"time=(\d+:\d+:\d+\.\d+)", line)
            if match:
                time_str = match.group(1)
                asyncio.create_task(progress_message.edit_text(f"⏳ Сжатие видео: {time_str}"))

        ff.on("stderr", handle_progress)

        ff.output(
            output_path,
            vcodec="libx264",
            crf=crf,
            preset=preset,
            acodec="aac",
            **{"b:a": audio_bitrate},
            movflags="faststart"
        )

        ff.execute()
        await progress_message.edit_text("✅ Видео успешно сжато!")
        logging.info(f"Видео сжато: {output_path}")
        return True
    except ffmpeg.FFmpegError as e:
        await progress_message.edit_text(f"❌ Ошибка FFmpeg: {str(e)}")
        logging.error(f"Ошибка FFmpeg при сжатии {input_path}: {e}")
        return False
    except Exception as e:
        await progress_message.edit_text(f"❌ Ошибка при сжатии видео: {str(e)}")
        logging.error(f"Ошибка при сжатии {input_path}: {e}")
        return False


@dp.message(CommandStart())
async def start(message: types.Message):
    """Обработка команды /start"""
    user_id = message.from_user.id

    if not await check_access(user_id):
        await message.reply("🚫 Доступ только для авторизованного пользователя.")
        return

    state = await get_user_state(user_id)

    welcome_text = (
        "🚀 **Добро пожаловать в Social Media Publisher!**\n\n"
        "📱 Публикуйте контент в Telegram и X.com\n"
        "🖼️ Поддержка фото и видео\n"
        "📝 Добавление текстовых описаний\n"
        "⚙️ Гибкие настройки публикации\n\n"
        "👇 Выберите действие:"
    )

    keyboard = get_main_menu_keyboard(state)
    sent_message = await message.reply(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
    state.menu_message_id = sent_message.message_id


@dp.message(Command("help"))
async def help_command(message: types.Message):
    """Обработка команды /help"""
    user_id = message.from_user.id

    if not await check_access(user_id):
        await message.reply("🚫 Доступ только для авторизованного пользователя.")
        return

    help_text = (
        "❓ **Помощь по использованию бота:**\n\n"
        "🔧 **Команды:**\n"
        "• `/start` - Запуск бота\n"
        "• `/help` - Эта справка\n"
        "• `/clear` - Очистить всё\n"
        "• `/status` - Показать статус\n\n"
        "📱 **Возможности:**\n"
        "• Публикация в Telegram и X.com\n"
        "• Поддержка фото и видео\n"
        "• Добавление текстовых описаний\n"
        "• Предпросмотр контента\n"
        "• Выбор платформ для публикации\n\n"
        "⚠️ **Ограничения:**\n"
        f"• Максимум {MAX_MEDIA_FILES} медиа файлов\n"
        f"• Максимум {MAX_TEXT_LENGTH} символов в тексте\n"
        "• Поддерживаются только JPG и MP4 файлы"
    )

    await message.reply(help_text, parse_mode="Markdown")


@dp.message(Command("clear"))
async def clear_command(message: types.Message):
    """Обработка команды /clear"""
    user_id = message.from_user.id

    if not await check_access(user_id):
        await message.reply("🚫 Доступ только для авторизованного пользователя.")
        return

    state = await get_user_state(user_id)

    for file in state.media_files:
        if os.path.exists(file):
            try:
                os.remove(file)
                logging.debug(f"Удален файл: {file}")
            except Exception as e:
                logging.error(f"Ошибка удаления файла {file}: {e}")

    user_states[user_id] = UserState()
    await message.reply("🗑️ Сессия полностью очищена.")


@dp.message(Command("status"))
async def status_command(message: types.Message):
    """Обработка команды /status"""
    user_id = message.from_user.id

    if not await check_access(user_id):
        await message.reply("🚫 Доступ только для авторизованного пользователя.")
        return

    state = await get_user_state(user_id)
    status_text = get_content_info(state)

    await message.reply(status_text, parse_mode="Markdown")


@dp.callback_query(lambda c: c.data == "add_text")
async def add_text_callback(callback: types.CallbackQuery, state: FSMContext):
    """Добавление текста"""
    user_id = callback.from_user.id

    if not await check_access(user_id):
        await callback.answer("🚫 Доступ запрещен")
        return

    await state.set_state(PostStates.waiting_for_text)
    await callback.message.edit_text(
        f"📝 **Введите текст для публикации:**\n\n"
        f"⚠️ Максимум {MAX_TEXT_LENGTH} символов\n"
        f"💡 Можете использовать эмодзи и форматирование",
        parse_mode="Markdown"
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "add_media")
async def add_media_callback(callback: types.CallbackQuery):
    """Добавление медиа"""
    user_id = callback.from_user.id

    if not await check_access(user_id):
        await callback.answer("🚫 Доступ запрещен")
        return

    user_state = await get_user_state(user_id)

    if len(user_state.media_files) >= MAX_MEDIA_FILES:
        await callback.answer(f"⚠️ Максимум {MAX_MEDIA_FILES} файлов")
        return

    user_state.current_mode = "adding_media"

    await callback.message.edit_text(
        f"🖼️ **Отправьте фото или видео:**\n\n"
        f"📊 Файлов добавлено: {len(user_state.media_files)}/{MAX_MEDIA_FILES}\n"
        f"📷 Поддерживаются: JPG, PNG\n"
        f"🎥 Поддерживаются: MP4, MOV\n\n"
        f"💡 После добавления файлов используйте кнопки ниже",
        reply_markup=get_media_menu_keyboard(user_state),
        parse_mode="Markdown"
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "preview")
async def preview_callback(callback: types.CallbackQuery):
    """Предпросмотр контента"""
    user_id = callback.from_user.id

    if not await check_access(user_id):
        await callback.answer("🚫 Доступ запрещен")
        return

    state = await get_user_state(user_id)
    preview_text = get_content_info(state)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

    await callback.message.edit_text(preview_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "clear_all")
async def clear_all_callback(callback: types.CallbackQuery):
    """Очистка всего контента"""
    user_id = callback.from_user.id

    if not await check_access(user_id):
        await callback.answer("🚫 Доступ запрещен")
        return

    state = await get_user_state(user_id)

    for file in state.media_files:
        if os.path.exists(file):
            try:
                os.remove(file)
                logging.debug(f"Удален файл: {file}")
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
    await callback.answer("✅ Весь контент удален")


@dp.callback_query(lambda c: c.data in ["toggle_telegram", "toggle_x"])
async def toggle_platform(callback: types.CallbackQuery):
    """Переключение платформ"""
    user_id = callback.from_user.id

    if not await check_access(user_id):
        await callback.answer("🚫 Доступ запрещен")
        return

    state = await get_user_state(user_id)
    platform = callback.data.replace("toggle_", "")

    state.selected_platforms[platform] = not state.selected_platforms[platform]

    if not any(state.selected_platforms.values()):
        state.selected_platforms[platform] = True
        await callback.answer("⚠️ Должна быть выбрана хотя бы одна платформа")
        return

    platform_name = "📱 Telegram" if platform == "telegram" else "🐦 X.com"
    status = "✅ включен" if state.selected_platforms[platform] else "❌ выключен"

    main_text = "🚀 **Social Media Publisher**\n\n" + get_content_info(state)
    keyboard = get_main_menu_keyboard(state)

    await callback.message.edit_text(main_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer(f"{platform_name} {status}")


@dp.callback_query(lambda c: c.data == "confirm_post")
async def confirm_post(callback: types.CallbackQuery):
    """Подтверждение публикации"""
    user_id = callback.from_user.id

    if not await check_access(user_id):
        await callback.answer("🚫 Доступ запрещен")
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
                success = await post_to_telegram(bot, state.media_files, bool(state.media_files), state.description)
                if success:
                    results.append("✅ Telegram - опубликовано")
                else:
                    results.append("❌ Telegram - ошибка")
            except Exception as e:
                results.append(f"❌ Telegram - ошибка: {str(e)}")
                logging.error(f"Ошибка публикации в Telegram: {e}")

        if state.selected_platforms["x"]:
            try:
                success = await post_to_x(state.media_files, bool(state.media_files), state.description)
                if success:
                    results.append("✅ X.com - опубликовано")
                else:
                    results.append("❌ X.com - ошибка")
            except Exception as e:
                results.append(f"❌ X.com - ошибка: {str(e)}")
                logging.error(f"Ошибка публикации в X.com: {e}")

        result_text = "📊 **Результаты публикации:**\n\n" + "\n".join(results)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
        ])

        await callback.message.edit_text(result_text, reply_markup=keyboard, parse_mode="Markdown")

    except Exception as e:
        error_text = f"❌ **Критическая ошибка:**\n\n{str(e)}"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="confirm_post")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
        ])
        await callback.message.edit_text(error_text, reply_markup=keyboard, parse_mode="Markdown")
        logging.error(f"Критическая ошибка публикации: {e}")

    finally:
        for file in state.media_files:
            if os.path.exists(file):
                try:
                    os.remove(file)
                    logging.debug(f"Удален файл: {file}")
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


@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    user_id = callback.from_user.id

    if not await check_access(user_id):
        await callback.answer("🚫 Доступ запрещен")
        return

    state = await get_user_state(user_id)
    state.current_mode = "idle"

    main_text = "🚀 **Social Media Publisher**\n\n" + get_content_info(state)
    keyboard = get_main_menu_keyboard(state)

    await callback.message.edit_text(main_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

# Обработка текстовых сообщений
@dp.message(F.text, PostStates.waiting_for_text)
async def handle_text_input(message: types.Message, state: FSMContext):
    """Обработка ввода текста"""
    user_id = message.from_user.id

    if not await check_access(user_id):
        await message.reply("🚫 Доступ только для авторизованного пользователя.")
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


# Обработка фото
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    """Обработка фото"""
    user_id = message.from_user.id

    if not await check_access(user_id):
        await message.reply("🚫 Доступ только для авторизованного пользователя.")
        return

    user_state = await get_user_state(user_id)

    if len(user_state.media_files) >= MAX_MEDIA_FILES:
        await message.reply(f"⚠️ Максимум {MAX_MEDIA_FILES} медиа файлов!")
        return

    try:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        user_state.media_files.append(file_info.file_path)

        if message.caption:
            if len(message.caption) <= MAX_TEXT_LENGTH:
                user_state.description = message.caption
            else:
                await message.reply(f"⚠️ Описание слишком длинное! Максимум {MAX_TEXT_LENGTH} символов.")

        response_text = f"📷 **Фото добавлено!**\n\n" + get_content_info(user_state)
        keyboard = get_main_menu_keyboard(user_state)

        await message.reply(response_text, reply_markup=keyboard, parse_mode="Markdown")

    except Exception as e:
        await message.reply(f"❌ Ошибка при обработке фото: {str(e)}")
        logging.error(f"Ошибка обработки фото: {e}")


# Обработка видео
@dp.message(F.video)
async def handle_video(message: types.Message):
    """Обработка видео"""
    user_id = message.from_user.id

    if not await check_access(user_id):
        await message.reply("🚫 Доступ только для авторизованного пользователя.")
        return

    user_state = await get_user_state(user_id)

    if len(user_state.media_files) >= MAX_MEDIA_FILES:
        await message.reply(f"⚠️ Максимум {MAX_MEDIA_FILES} медиа файлов!")
        return

    try:
        video = message.video
        file_info = await bot.get_file(video.file_id)
        compressed_path = f"media/video_{user_id}_{video.file_id}_compressed.mp4"

        os.makedirs("media", exist_ok=True)

        file_size_mb = os.path.getsize(file_info.file_path) / (1024 * 1024)
        final_path = file_info.file_path

        if file_size_mb > 30:
            await message.reply(f"🎥 Видео ({file_size_mb:.2f} МБ) превышает 30 МБ, сжатие началось...")
            ffmpeg_path = "C:/ffmpeg-7.1.1-essentials_build/bin/ffmpeg.exe"  # Укажите ваш путь
            success = await compress_video(file_info.file_path, compressed_path, message, ffmpeg_path=ffmpeg_path, crf=23,
                                           preset="medium")
            if success:
                final_path = compressed_path
                if os.path.exists(file_info.file_path):
                    os.remove(file_info.file_path)
                    logging.debug(f"Удалён оригинальный файл: {file_info.file_path}")
            else:
                await message.reply("❌ Не удалось сжать видео, используется оригинал")
                final_path = file_info.file_path
        else:
            await message.reply(f"🎥 Видео ({file_size_mb:.2f} МБ) не требует сжатия")

        user_state.media_files.append(final_path)

        if message.caption:
            if len(message.caption) <= MAX_TEXT_LENGTH:
                user_state.description = message.caption
            else:
                await message.reply(f"⚠️ Описание слишком длинное! Максимум {MAX_TEXT_LENGTH} символов.")

        response_text = f"🎥 **Видео добавлено!**\n\n" + get_content_info(user_state)
        keyboard = get_main_menu_keyboard(user_state)

        await message.reply(response_text, reply_markup=keyboard, parse_mode="Markdown")

    except Exception as e:
        await message.reply(f"❌ Ошибка при обработке видео: {str(e)}")
        logging.error(f"Ошибка обработки видео: {e}")


# Обработка остальных сообщений
@dp.message()
async def handle_other_messages(message: types.Message):
    """Обработка других типов сообщений"""
    user_id = message.from_user.id

    if not await check_access(user_id):
        await message.reply("🚫 Доступ только для авторизованного пользователя.")
        return

    await message.reply(
        "🤔 **Неподдерживаемый тип контента**\n\n"
        "📱 Поддерживаются:\n"
        "• 📝 Текстовые сообщения\n"
        "• 📷 Фотографии (JPG, PNG)\n"
        "• 🎥 Видео (MP4, MOV)\n\n"
        "💡 Используйте /start для возврата в меню",
        parse_mode="Markdown"
    )


async def main():
    """Главная функция запуска бота"""
    try:
        logging.info("Запуск Social Media Publisher Bot...")
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
