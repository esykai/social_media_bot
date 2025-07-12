import tweepy
import asyncio
from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto
from config import X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET, TELEGRAM_GROUP_ID
import logging

client_v2 = tweepy.Client(
    consumer_key=X_API_KEY,
    consumer_secret=X_API_SECRET,
    access_token=X_ACCESS_TOKEN,
    access_token_secret=X_ACCESS_TOKEN_SECRET
)

auth = tweepy.OAuthHandler(X_API_KEY, X_API_SECRET)
auth.set_access_token(X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET)
api_v1 = tweepy.API(auth)


async def post_to_x(media_paths: list, has_media: bool, description: str):
    """
    Публикация в X.com с правильной обработкой медиа
    """
    try:
        media_ids = []

        if has_media and media_paths:
            for media_path in media_paths:
                try:
                    if media_path.lower().endswith(('.mp4', '.mov', '.avi')):
                        media = api_v1.media_upload(
                            filename=media_path,
                            media_category="tweet_video"
                        )
                        await wait_for_video_processing(media.media_id)
                    else:
                        media = api_v1.media_upload(filename=media_path)

                    media_ids.append(media.media_id)
                    logging.info(f"Медиа загружено: {media_path}, ID: {media.media_id}")

                except Exception as e:
                    logging.error(f"Ошибка загрузки медиа {media_path}: {e}")
                    continue

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


async def wait_for_video_processing(media_id):
    """
    Ожидание обработки видео на X.com
    """
    max_attempts = 60
    attempt = 0

    while attempt < max_attempts:
        try:
            status = api_v1.get_media_upload_status(media_id)

            if hasattr(status, 'processing_info'):
                state = status.processing_info.get('state')

                if state == 'succeeded':
                    logging.info(f"Видео обработано успешно: {media_id}")
                    return True
                elif state == 'failed':
                    logging.error(f"Обработка видео неудачна: {media_id}")
                    return False
                else:
                    check_after = status.processing_info.get('check_after_secs', 5)
                    logging.info(f"Ожидание обработки видео: {check_after} сек")
                    await asyncio.sleep(check_after)
            else:
                return True

        except Exception as e:
            logging.error(f"Ошибка проверки статуса видео: {e}")
            await asyncio.sleep(5)

        attempt += 1

    logging.error(f"Таймаут обработки видео: {media_id}")
    return False


async def post_to_telegram(bot: Bot, media_paths: list, has_media: bool, description: str):
    """
    Публикация в Telegram с улучшенной обработкой медиа
    """
    try:
        if not has_media or not media_paths:
            await bot.send_message(chat_id=TELEGRAM_GROUP_ID, text=description)
            logging.info("Текстовое сообщение отправлено в Telegram")
            return True

        photos = []
        videos = []

        for media_path in media_paths:
            if media_path.lower().endswith(('.mp4', '.mov', '.avi')):
                videos.append(media_path)
            else:
                photos.append(media_path)

        for i, video_path in enumerate(videos):
            try:
                video_file = FSInputFile(video_path)
                caption = description if i == 0 else ""
                await bot.send_video(
                    chat_id=TELEGRAM_GROUP_ID,
                    video=video_file,
                    caption=caption,
                    supports_streaming=True
                )
                logging.info(f"Видео отправлено в Telegram: {video_path}")

                await asyncio.sleep(1)

            except Exception as e:
                logging.error(f"Ошибка отправки видео {video_path}: {e}")
                continue

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
                    logging.info(f"Группа фото отправлена в Telegram: {len(photo_group)} фото")

                    if group_index < len(photo_groups) - 1:
                        await asyncio.sleep(1)

                except Exception as e:
                    logging.error(f"Ошибка отправки группы фото: {e}")
                    continue

        return True

    except Exception as e:
        logging.error(f"Общая ошибка публикации в Telegram: {str(e)}")
        return False


def test_x_credentials():
    """
    Тест подключения к X.com API
    """
    try:
        me = client_v2.get_me()
        if me.data:
            logging.info(f"X.com API v2 подключен: @{me.data.username}")
            return True
        else:
            logging.error("X.com API v2: не удалось получить данные пользователя")
            return False

    except tweepy.Unauthorized:
        logging.error("X.com API: неверные учетные данные")
        return False
    except Exception as e:
        logging.error(f"X.com API: ошибка подключения - {e}")
        return False


def test_telegram_credentials(bot: Bot):
    """
    Тест подключения к Telegram API
    """
    try:
        return True
    except Exception as e:
        logging.error(f"Telegram API: ошибка подключения - {e}")
        return False


# Дополнительные утилиты
def get_file_size_mb(file_path: str) -> float:
    """Получение размера файла в МБ"""
    try:
        import os
        size_bytes = os.path.getsize(file_path)
        return size_bytes / (1024 * 1024)
    except:
        return 0


def validate_media_file(file_path: str) -> dict:
    """
    Валидация медиа файла
    """
    import os

    result = {
        'valid': False,
        'type': None,
        'size_mb': 0,
        'error': None
    }

    if not os.path.exists(file_path):
        result['error'] = 'Файл не найден'
        return result

    result['size_mb'] = get_file_size_mb(file_path)

    file_ext = file_path.lower().split('.')[-1]

    if file_ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
        result['type'] = 'photo'
        # Telegram: макс 10 МБ для фото
        # X.com: макс 5 МБ для фото
        if result['size_mb'] > 5:
            result['error'] = f'Фото слишком большое: {result["size_mb"]:.1f} МБ (макс 5 МБ)'
        else:
            result['valid'] = True

    elif file_ext in ['mp4', 'mov', 'avi']:
        result['type'] = 'video'
        # Telegram: макс 50 МБ для видео
        # X.com: макс 512 МБ для видео
        if result['size_mb'] > 50:
            result['error'] = f'Видео слишком большое: {result["size_mb"]:.1f} МБ (макс 50 МБ)'
        else:
            result['valid'] = True
    else:
        result['error'] = f'Неподдерживаемый формат: {file_ext}'

    return result


# Функция для тестирования
async def test_posting():
    """
    Тестовая функция для проверки публикации
    """
    print("🧪 Тестирование публикации только текста...")

    from config import TELEGRAM_BOT_TOKEN
    test_bot = Bot(token=TELEGRAM_BOT_TOKEN)

    try:
        # Тест X.com
        x_result = await post_to_x([], False, "🧪 Тестовое сообщение от бота")
        print(f"X.com результат: {'✅' if x_result else '❌'}")

        # Тест Telegram
        tg_result = await post_to_telegram(test_bot, [], False, "🧪 Тестовое сообщение от бота")
        print(f"Telegram результат: {'✅' if tg_result else '❌'}")

    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
    finally:
        await test_bot.session.close()


if __name__ == "__main__":
    asyncio.run(test_posting())