import asyncio
import os
import json
import time
import logging
import aiohttp

from aiogram import types

from config import FREE_CONVERT_API


async def compress_video_with_auto_format(
        input_path: str,
        output_path: str,
        message: types.Message,
        api_key: str = FREE_CONVERT_API,
        crf: int = 23,
        preset: str = "medium",
        audio_bitrate: str = "128k"
) -> bool:
    """Версия с автоматическим определением расширения"""
    input_format = os.path.splitext(input_path)[1].lower().lstrip('.')
    if input_format == 'mov':
        input_format = 'mov'
    elif input_format in ['mp4', 'avi', 'mkv', 'wmv', 'flv']:
        input_format = input_format
    else:
        input_format = 'mp4'  # По умолчанию

    return await compress_video_with_format(
        input_path=input_path,
        output_path=output_path,
        message=message,
        api_key=api_key,
        input_format=input_format
    )

async def compress_video_with_format(
        input_path: str,
        output_path: str,
        message: types.Message,
        api_key: str = FREE_CONVERT_API,
        input_format: str = "mov"
) -> bool:
    """Версия с указанием кастомного расширения"""
    if not os.path.exists(input_path):
        logging.error(f"Файл {input_path} не найден")
        await message.reply(f"❌ Ошибка: Файл {input_path} не найден.")
        return False

    # Ограничение: не более 750 МБ
    file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
    if file_size_mb > 750:
        logging.error(f"Файл {input_path} превышает лимит 750 МБ")
        await message.reply(f"❌ Ошибка: Файл слишком большой ({file_size_mb:.2f} МБ). Лимит: 750 МБ.")
        return False

    progress_message = await message.reply("⏳ Сжатие видео началось...")

    BASE_URL = 'https://api.freeconvert.com/v1/process'
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    async with aiohttp.ClientSession() as session:
        try:
            input_body = {
                "tasks": {
                    "import-1": {
                        "operation": "import/upload"
                    },
                    "compress-1": {
                        "operation": "compress",
                        "input": "import-1",
                        "input_format": input_format,
                        "output_format": "mp4",
                        "options": {
                            "video_codec": "libx264",
                            "crf": 23,
                            "maxrate": "4.5M",
                            "preset": "faster",
                            "flags": "+global_header",
                            "pix_fmt": "yuv420p",
                            "profile": "baseline",
                            "movflags": "+faststart",
                            "audio_codec": "aac",
                            "audio_bitrate": "128k",
                            "audio_channels": 2
                        }
                    },
                    "export-1": {
                        "operation": "export/url",
                        "input": ["compress-1"]
                    }
                }
            }

            async with session.post(f'{BASE_URL}/jobs', headers=headers, data=json.dumps(input_body)) as response:
                if response.status not in [200, 201]:
                    error_text = await response.text()
                    logging.error(f"Ошибка при создании задачи: {response.status} - {error_text}")
                    return False

                job = await response.json()
                job_id = job['id']

                import_task = None
                for task in job['tasks']:
                    if task['name'] == 'import-1':
                        import_task = task
                        break

                if not import_task:
                    logging.error("Импорт-задача не найдена")
                    return False

                upload_url = import_task['result']['form']['url']
                upload_params = import_task['result']['form']['parameters']

            form_data = aiohttp.FormData()
            for key, value in upload_params.items():
                form_data.add_field(key, value)

            with open(input_path, 'rb') as video_file:
                form_data.add_field('file', video_file, filename=os.path.basename(input_path))

                async with session.post(upload_url, data=form_data) as response:
                    if response.status not in [200, 201, 204]:
                        error_text = await response.text()
                        logging.error(f"Ошибка при загрузке файла: {response.status} - {error_text}")
                        return False

            timeout = 600
            start_time = time.time()

            while time.time() - start_time < timeout:
                async with session.get(f'{BASE_URL}/jobs/{job_id}', headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logging.error(f"Ошибка при проверке статуса: {response.status} - {error_text}")
                        return False

                    job_status = await response.json()
                    status = job_status['status']
                    logging.info(f"Статус задачи: {status}")

                    if status == 'completed':
                        break
                    elif status == 'failed':
                        error_msg = job_status.get('message', 'Неизвестная ошибка')
                        logging.error(f"Ошибка при сжатии: {error_msg}")
                        return False

                await asyncio.sleep(3)

            if time.time() - start_time >= timeout:
                logging.error("Превышено время ожидания сжатия (10 минут)")
                return False

            export_task = None
            for task in job_status['tasks']:
                if task['name'] == 'export-1':
                    export_task = task
                    break

            if not export_task or 'result' not in export_task or 'url' not in export_task['result']:
                logging.error("Результат экспорта не найден")
                return False

            download_url = export_task['result']['url']

            async with session.get(download_url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logging.error(f"Ошибка при загрузке файла: {response.status} - {error_text}")
                    return False

                with open(output_path, 'wb') as f:
                    f.write(await response.read())

            original_size = os.path.getsize(input_path)
            compressed_size = os.path.getsize(output_path)

            if original_size > 0:
                compression_ratio = 100 - (compressed_size / original_size * 100)
                original_mb = original_size / (1024 * 1024)
                compressed_mb = compressed_size / (1024 * 1024)

                compression_info = (
                    f"📦 Размер до: {original_mb:.2f} МБ\n"
                    f"📦 Размер после: {compressed_mb:.2f} МБ\n"
                    f"📉 Сжато на {compression_ratio:.1f}%"
                )
            else:
                compression_info = "⚠️ Невозможно рассчитать степень сжатия (размер исходного файла — 0 байт)."

            await progress_message.edit_text(f"✅ Видео успешно сжато!\n\n{compression_info}")
            logging.info(f"Видео сжато: {output_path} ({compression_info})")
            return True

        except Exception as e:
            await progress_message.edit_text(f"❌ Ошибка во время сжатия: {str(e)}")
            logging.exception(f"Исключение во время сжатия: {e}")
            return False
