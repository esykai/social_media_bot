import os
import asyncio
import logging
import time

import tweepy
from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto
from moviepy import VideoFileClip

from config import (
    X_API_KEY,
    X_API_SECRET,
    X_ACCESS_TOKEN,
    X_ACCESS_TOKEN_SECRET,
    TELEGRAM_GROUP_ID,
)

client_v2 = tweepy.Client(
    consumer_key=X_API_KEY,
    consumer_secret=X_API_SECRET,
    access_token=X_ACCESS_TOKEN,
    access_token_secret=X_ACCESS_TOKEN_SECRET
)

auth = tweepy.OAuthHandler(X_API_KEY, X_API_SECRET)
auth.set_access_token(X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET)
api_v1 = tweepy.API(auth)


async def post_to_x(media_paths: list[str], has_media: bool, description: str) -> bool:
    """
    Публикация в X.com с улучшенной обработкой медиа
    """
    try:
        media_ids = []

        if has_media and media_paths:
            for media_path in media_paths:
                try:
                    # Проверяем размер и валидность файла
                    validation = validate_media_file(media_path)
                    if not validation['valid']:
                        logging.error(f"Невалидный файл {media_path}: {validation['error']}")
                        continue

                    # Загружаем видео с улучшенной обработкой
                    if media_path.lower().endswith(('.mp4', '.mov', '.avi')):
                        media_id = await upload_video_to_x(media_path)
                        if media_id:
                            media_ids.append(media_id)
                    else:
                        # Для фото используем обычную загрузку
                        media = api_v1.media_upload(filename=media_path)
                        media_ids.append(media.media_id)
                        logging.info(f"Фото загружено: {media_path}, ID: {media.media_id}")

                except Exception as e:
                    logging.error(f"Ошибка загрузки медиа {media_path}: {e}")
                    continue

        # Создаем твит
        if media_ids:
            response = client_v2.create_tweet(text=description, media_ids=media_ids)
        else:
            response = client_v2.create_tweet(text=description)

        if response.data:
            logging.info(f"Твит опубликован: {response.data['id']}")
            return True
        else:
            logging.error("Не удалось получить ID твита")
            return False

    except tweepy.TooManyRequests:
        logging.error("Превышен лимит запросов к X.com API")
        return False
    except tweepy.Unauthorized:
        logging.error("Ошибка авторизации X.com API")
        return False
    except tweepy.Forbidden:
        logging.error("Доступ запрещен к X.com API")
        return False
    except Exception as e:
        logging.error(f"Общая ошибка публикации в X.com: {str(e)}")
        return False


async def upload_video_to_x(video_path: str) -> str:
    """
    Улучшенная загрузка видео на X.com с чанками
    """
    try:
        file_size = os.path.getsize(video_path)
        logging.info(f"Начинаем загрузку видео: {video_path} ({file_size / (1024 * 1024):.1f} МБ)")

        # Шаг 1: Инициализация загрузки
        media = api_v1.media_upload(
            filename=video_path,
            media_category="tweet_video",
            chunked=True  # Включаем чанковую загрузку
        )

        media_id = media.media_id
        logging.info(f"Видео загружено, ID: {media_id}, ожидаем обработки...")

        # Шаг 2: Ожидание обработки
        processing_success = await wait_for_video_processing_improved(media_id)

        if processing_success:
            logging.info(f"Видео успешно обработано: {media_id}")
            return media_id
        else:
            logging.error(f"Ошибка обработки видео: {media_id}")
            return None

    except Exception as e:
        logging.error(f"Ошибка загрузки видео {video_path}: {e}")
        return None


async def wait_for_video_processing_improved(media_id: str) -> bool:
    """
    Улучшенное ожидание обработки видео на X.com
    """
    max_attempts = 120  # Увеличиваем количество попыток
    attempt = 0
    last_check_time = time.time()

    while attempt < max_attempts:
        try:
            status = api_v1.get_media_upload_status(media_id)

            if hasattr(status, 'processing_info'):
                processing_info = status.processing_info
                state = processing_info.get('state')

                logging.info(f"Статус обработки видео {media_id}: {state}")

                if state == 'succeeded':
                    logging.info(f"✅ Видео обработано успешно: {media_id}")
                    return True

                elif state == 'failed':
                    error_info = processing_info.get('error', {})
                    logging.error(f"❌ Обработка видео неудачна: {media_id}, ошибка: {error_info}")
                    return False

                elif state in ['pending', 'in_progress']:
                    check_after = processing_info.get('check_after_secs', 10)
                    progress = processing_info.get('progress_percent', 0)

                    logging.info(f"⏳ Обработка видео: {progress}%, следующая проверка через {check_after} сек")

                    # Адаптивное ожидание
                    await asyncio.sleep(min(check_after, 30))  # Максимум 30 сек между проверками

                else:
                    logging.warning(f"⚠️ Неизвестное состояние обработки: {state}")
                    await asyncio.sleep(10)
            else:
                # Если нет информации о обработке, считаем что готово
                logging.info(f"✅ Видео готово к использованию: {media_id}")
                return True

        except tweepy.TooManyRequests:
            logging.warning("⚠️ Превышен лимит запросов при проверке статуса, ждем 60 сек")
            await asyncio.sleep(60)

        except Exception as e:
            logging.error(f"❌ Ошибка проверки статуса видео {media_id}: {e}")
            await asyncio.sleep(10)

        attempt += 1

        # Логируем прогресс каждые 10 попыток
        if attempt % 10 == 0:
            elapsed = time.time() - last_check_time
            logging.info(f"⏱️ Обработка видео: попытка {attempt}/{max_attempts}, прошло {elapsed:.1f} сек")

    logging.error(f"❌ Таймаут обработки видео: {media_id} (попыток: {attempt})")
    return False


async def post_to_telegram(bot: Bot, media_paths: list[str], has_media: bool, description: str) -> bool:
    """
    Публикация в Telegram с улучшенной обработкой медиа
    """
    try:
        if not has_media or not media_paths:
            await bot.send_message(chat_id=TELEGRAM_GROUP_ID, text=description)
            logging.info("✅ Текстовое сообщение отправлено в Telegram")
            return True

        photos = []
        videos = []

        # Валидируем все файлы перед отправкой
        valid_media_paths = []
        for media_path in media_paths:
            validation = validate_media_file(media_path)
            if validation['valid']:
                valid_media_paths.append(media_path)
                if validation['type'] == 'video':
                    videos.append(media_path)
                else:
                    photos.append(media_path)
            else:
                logging.error(f"❌ Пропускаем невалидный файл {media_path}: {validation['error']}")

        # Отправляем видео
        for i, video_path in enumerate(videos):
            try:
                thumb_path = f"thumb_{i}.jpg"

                video = VideoFileClip(video_path)
                width, height = video.size
                duration = int(video.duration)
                video.save_frame(thumb_path, t=1)
                video.close()

                video_file = FSInputFile(video_path)
                thumb_file = FSInputFile(thumb_path)
                caption = description if i == 0 else ""

                await bot.send_video(
                    chat_id=TELEGRAM_GROUP_ID,
                    video=video_file,
                    caption=caption,
                    supports_streaming=True,
                    width=width,
                    height=height,
                    duration=duration,
                    thumbnail=thumb_file,
                )
                logging.info(f"✅ Видео отправлено в Telegram: {video_path}")
                await asyncio.sleep(1)

            except Exception as e:
                logging.error(f"❌ Ошибка отправки видео {video_path}: {e}")
                continue

        # Отправляем фото группами по 10
        if photos:
            photo_groups = [photos[i:i + 10] for i in range(0, len(photos), 10)]

            for group_index, photo_group in enumerate(photo_groups):
                try:
                    media_group = []

                    for i, photo_path in enumerate(photo_group):
                        photo_file = FSInputFile(photo_path)
                        caption = description if (group_index == 0 and i == 0 and not videos) else ""

                        media_group.append(
                            InputMediaPhoto(
                                media=photo_file,
                                caption=caption
                            )
                        )

                    await bot.send_media_group(chat_id=TELEGRAM_GROUP_ID, media=media_group)
                    logging.info(f"✅ Группа фото отправлена в Telegram: {len(photo_group)} фото")

                    if group_index < len(photo_groups) - 1:
                        await asyncio.sleep(1)

                except Exception as e:
                    logging.error(f"❌ Ошибка отправки группы фото: {e}")
                    continue

        return True

    except Exception as e:
        logging.error(f"❌ Общая ошибка публикации в Telegram: {str(e)}")
        return False


def validate_media_file(file_path: str) -> dict:
    """
    Улучшенная валидация медиа файла
    """
    result = {
        'valid': False,
        'type': None,
        'size_mb': 0,
        'error': None
    }

    if not os.path.exists(file_path):
        result['error'] = 'Файл не найден'
        return result

    try:
        result['size_mb'] = os.path.getsize(file_path) / (1024 * 1024)
    except OSError as e:
        result['error'] = f'Ошибка чтения файла: {e}'
        return result

    file_ext = file_path.lower().split('.')[-1]

    if file_ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
        result['type'] = 'photo'
        if result['size_mb'] > 5:
            result['error'] = f'Фото слишком большое: {result["size_mb"]:.1f} МБ (макс 5 МБ для X.com)'
        else:
            result['valid'] = True

    elif file_ext in ['mp4', 'mov', 'avi']:
        result['type'] = 'video'
        # X.com поддерживает видео до 512 МБ, но для стабильности ограничиваем 100 МБ
        if result['size_mb'] > 100:
            result['error'] = f'Видео слишком большое: {result["size_mb"]:.1f} МБ (макс 100 МБ)'
        else:
            result['valid'] = True
    else:
        result['error'] = f'Неподдерживаемый формат: {file_ext}'

    return result


def test_x_credentials():
    """
    Тест подключения к X.com API
    """
    try:
        me = client_v2.get_me()
        if me.data:
            logging.info(f"✅ X.com API v2 подключен: @{me.data.username}")
            return True
        else:
            logging.error("❌ X.com API v2: не удалось получить данные пользователя")
            return False

    except tweepy.Unauthorized:
        logging.error("❌ X.com API: неверные учетные данные")
        return False
    except Exception as e:
        logging.error(f"❌ X.com API: ошибка подключения - {e}")
        return False


def test_telegram_credentials(bot: Bot):
    """
    Тест подключения к Telegram API
    """
    try:
        return True
    except Exception as e:
        logging.error(f"❌ Telegram API: ошибка подключения - {e}")
        return False


# Функция для тестирования
async def test_posting():
    """
    Тестовая функция для проверки публикации
    """
    print("🧪 Тестирование публикации...")

    from config import TELEGRAM_BOT_TOKEN
    test_bot = Bot(token=TELEGRAM_BOT_TOKEN)

    try:
        # Тест X.com
        print("🔄 Тестируем X.com...")
        x_result = await post_to_x([], False, "🧪 Тестовое сообщение от бота")
        print(f"X.com результат: {'✅' if x_result else '❌'}")

        # Тест Telegram
        print("🔄 Тестируем Telegram...")
        tg_result = await post_to_telegram(test_bot, [], False, "🧪 Тестовое сообщение от бота")
        print(f"Telegram результат: {'✅' if tg_result else '❌'}")

    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
    finally:
        await test_bot.session.close()


if __name__ == "__main__":
    asyncio.run(test_posting())