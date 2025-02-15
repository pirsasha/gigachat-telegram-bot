"""Main entry point for the GigaChat Bot application."""
import os
import yaml
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
import base64
import requests
import uuid
import warnings
import threading
import time
from urllib.parse import urlencode
from urllib3.exceptions import InsecureRequestWarning
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import io
import re
import asyncio
import signal
import sys

# Отключаем предупреждения о небезопасном SSL
warnings.filterwarnings('ignore', category=InsecureRequestWarning)

# Configure logging
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# File handler
try:
    file_handler = RotatingFileHandler("bot.log", maxBytes=1024*1024, backupCount=5)
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)
    logger.info("Логирование инициализировано успешно")
except Exception as e:
    logger.error(f"Ошибка инициализации файлового логирования: {str(e)}")

class GigaChatBot:
    def __init__(self, bot_token, allowed_chat_ids, client_id, client_secret):
        """Initialize the GigaChat bot with the given credentials."""
        self.bot_token = bot_token
        self.allowed_chat_ids = [int(chat_id) for chat_id in allowed_chat_ids]
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expiry = None
        self._stop_event = threading.Event()

        # Добавляем хранение истории чатов и контекстов
        self.chat_histories = {}
        self.chat_contexts = {}  # Хранение context_id для каждого чата
        # Максимальное количество сообщений в истории
        self.max_history_length = 10

        # Создаем сессию для работы с API
        self.session = requests.Session()
        self.session.verify = False
        logger.warning("SSL verification is disabled")

        # Initialize the application
        self.application = Application.builder().token(bot_token).build()

        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("image", self.generate_image))
        self.application.add_handler(CommandHandler("clear", self.clear_history))
        self.application.add_handler(MessageHandler(
            filters.PHOTO | filters.Document.ALL, 
            self.process_file
        ))
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_message
        ))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        chat_id = update.effective_chat.id
        logger.debug("Received /start command from chat_id: %s", chat_id)

        if chat_id not in self.allowed_chat_ids:
            logger.warning("Unauthorized /start command from chat_id: %s", chat_id)
            return

        await update.message.reply_text(
            "Привет! Я бот с интеграцией GigaChat. "
            "Отправьте мне текстовое сообщение, и я постараюсь помочь. "
            "\n\nТакже вы можете:\n"
            "• Использовать команду /image для генерации изображений\n"
            "• Отправлять изображения (JPG, PNG, TIFF, BMP до 15MB) для анализа\n"
            "• Отправлять текстовые файлы (TXT, CSV, MD, PDF, DOC, DOCX до 30MB) для анализа\n"
            "• Использовать команду /clear для очистки истории чата"
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages."""
        chat_id = update.effective_chat.id
        logger.debug("Received message from chat_id: %s", chat_id)

        if chat_id not in self.allowed_chat_ids:
            logger.warning("Unauthorized message from chat_id: %s", chat_id)
            return

        try:
            # Ensure we have a valid access token
            if not self.access_token and not self.get_access_token():
                logger.error("Failed to obtain access token")
                await update.message.reply_text(
                    "Ошибка авторизации в GigaChat API. Пожалуйста, попробуйте позже.",
                    reply_to_message_id=update.message.message_id
                )
                return

            # Отправляем сообщение о начале обработки
            processing_message = await update.message.reply_text(
                "💭 Обрабатываю ваше сообщение...",
                reply_to_message_id=update.message.message_id
            )

            # Получаем или инициализируем историю чата
            if chat_id not in self.chat_histories:
                self.chat_histories[chat_id] = [{
                    "role": "system",
                    "content": "Ты — умный и дружелюбный ассистент. Отвечай подробно, но по существу. "
                    "Поддерживай контекст диалога и учитывай предыдущие сообщения при ответе. "
                    "Если не уверен в ответе, так и скажи."
                }]
                logger.debug(f"Инициализирована новая история для chat_id: {chat_id}")

            # Добавляем сообщение пользователя в историю
            self.chat_histories[chat_id].append({
                "role": "user",
                "content": update.message.text
            })

            logger.debug(f"История чата для {chat_id} после добавления сообщения пользователя: {len(self.chat_histories[chat_id])} сообщений")

            # Ограничиваем длину истории, сохраняя системное сообщение
            if len(self.chat_histories[chat_id]) > self.max_history_length + 1:  # +1 для системного сообщения
                system_message = self.chat_histories[chat_id][0]
                self.chat_histories[chat_id] = [system_message] + self.chat_histories[chat_id][-(self.max_history_length):]
                logger.debug(f"История чата для {chat_id} обрезана до {self.max_history_length} сообщений + системное")

            # Подготавливаем запрос с учетом контекста
            request_data = {
                "model": "GigaChat",
                "messages": self.chat_histories[chat_id],
                "temperature": 0.7,
                "max_tokens": 1500,
                "update_interval": 0
            }

            # Добавляем context_id если он есть
            if chat_id in self.chat_contexts:
                request_data["context_id"] = self.chat_contexts[chat_id]

            logger.debug(f"Отправка запроса к API с {len(self.chat_histories[chat_id])} сообщениями")

            response = self.session.post(
                "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                json=request_data,
                verify=False
            )

            if response.status_code == 200:
                data = response.json()
                bot_response = data["choices"][0]["message"]["content"]

                # Сохраняем context_id для следующих сообщений
                if "context_id" in data:
                    self.chat_contexts[chat_id] = data["context_id"]
                    logger.debug(f"Сохранен context_id для chat_id {chat_id}: {data['context_id']}")

                # Добавляем ответ бота в историю
                self.chat_histories[chat_id].append({
                    "role": "assistant",
                    "content": bot_response
                })

                logger.debug(f"История чата для {chat_id} после добавления ответа бота: {len(self.chat_histories[chat_id])} сообщений")

                await processing_message.delete()
                await update.message.reply_text(
                    bot_response,
                    reply_to_message_id=update.message.message_id
                )
                logger.info("Successfully sent response to user")

            elif response.status_code == 401:
                logger.warning("Token expired, attempting to refresh...")
                if self.get_access_token():
                    await processing_message.delete()
                    return await self.handle_message(update, context)
                else:
                    await processing_message.edit_text(
                        "❌ Ошибка авторизации в GigaChat API. Повторите попытку позже."
                    )
            else:
                logger.error("API error response: %s", response.text)
                await processing_message.edit_text(
                    "❌ Произошла ошибка при обработке запроса. Попробуйте позже."
                )

        except Exception as e:
            logger.error("Error processing message: %s", str(e))
            await update.message.reply_text(
                "❌ Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."
            )

    async def generate_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle image generation command."""
        chat_id = update.effective_chat.id
        logger.debug("Received image generation request from chat_id: %s", chat_id)

        if chat_id not in self.allowed_chat_ids:
            logger.warning("Unauthorized image request from chat_id: %s", chat_id)
            return

        message_parts = update.message.text.split(' ', 1)
        if len(message_parts) < 2:
            await update.message.reply_text(
                "Пожалуйста, добавьте описание изображения после команды /image\n"
                "Например: /image красивый закат на море"
            )
            return

        prompt = message_parts[1]
        logger.debug("Processing image generation: %s", prompt)

        try:
            if not self.access_token and not self.get_access_token():
                logger.error("Failed to obtain access token")
                await update.message.reply_text(
                    "🚫 Ошибка авторизации в GigaChat API. Пожалуйста, попробуйте позже."
                )
                return

            status_message = await update.message.reply_text(
                "🎨 Генерирую изображение, пожалуйста, подождите..."
            )

            response = self.session.post(
                "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "GigaChat",
                    "messages": [{"role": "user", "content": f"Нарисуй {prompt}"}],
                    "temperature": 0.7,
                    "max_tokens": 1500,
                    "function_call": "auto"
                },
                verify=False
            )

            if response.status_code == 200:
                data = response.json()
                message = data["choices"][0]["message"]
                content = message.get("content", "")
                import re
                img_match = re.search(r'<img src="([^"]+)"', content)

                if img_match:
                    file_id = img_match.group(1)
                    image_url = f"https://gigachat.devices.sberbank.ru/api/v1/files/{file_id}/content"

                    image_response = self.session.get(
                        image_url,
                        headers={"Authorization": f"Bearer {self.access_token}"},
                        verify=False
                    )

                    if image_response.status_code == 200:
                        caption = f"🎨 Сгенерированное изображение по запросу: {prompt}"
                        await update.message.reply_photo(
                            photo=image_response.content,
                            caption=caption
                        )
                        await status_message.delete()
                    else:
                        logger.error("Error downloading image: %s - %s", 
                                   image_response.status_code, 
                                   image_response.text[:200])
                        await status_message.edit_text("❌ Не удалось загрузить сгенерированное изображение.")
                else:
                    logger.error("Image ID not found in response")
                    await status_message.edit_text("❌ Не удалось сгенерировать изображение.")

            elif response.status_code == 401:
                logger.warning("Token expired, attempting to refresh...")
                if self.get_access_token():
                    await status_message.delete()
                    return await self.generate_image(update, context)
                else:
                    await status_message.edit_text(
                        "❌ Ошибка авторизации в GigaChat API. Повторите попытку позже."
                    )
            else:
                logger.error("API error response: %s", response.text)
                await status_message.edit_text(
                    "❌ Произошла ошибка при генерации изображения. Попробуйте позже."
                )

        except Exception as e:
            logger.error("Error generating image: %s", str(e))
            await update.message.reply_text(
                "❌ Произошла непредвиденная ошибка при генерации изображения. Пожалуйста, попробуйте позже."
            )

    async def process_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle file uploads."""
        chat_id = update.effective_chat.id
        logger.debug("Received file from chat_id: %s", chat_id)

        if chat_id not in self.allowed_chat_ids:
            logger.warning("Unauthorized file upload from chat_id: %s", chat_id)
            return

        try:
            # Get file from message
            if update.message.document:
                file = update.message.document
                mime_type = file.mime_type
                logger.debug(f"Processing document with MIME type: {mime_type}")
            elif update.message.photo:
                file = update.message.photo[-1]
                mime_type = 'image/jpeg'
                logger.debug("Processing photo")
            else:
                await update.message.reply_text(
                    "Пожалуйста, отправьте файл или изображение."
                )
                return

            # Define supported MIME types and size limits
            supported_image_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/tiff', 'image/bmp']
            supported_text_types = [
                'text/plain', 'text/csv', 'text/markdown', 
                'application/pdf', 'application/msword',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            ]

            # Set size limits based on file type
            max_image_size = 15 * 1024 * 1024  # 15MB for images
            max_text_size = 30 * 1024 * 1024   # 30MB for text files

            is_image = mime_type in supported_image_types
            is_text = mime_type in supported_text_types

            if not (is_image or is_text):
                await update.message.reply_text(
                    "❌ Неподдерживаемый формат файла. Поддерживаются:\n"
                    "• Изображения: JPG, PNG, TIFF, BMP\n"
                    "• Текстовые файлы: TXT, CSV, MD, PDF, DOC, DOCX"
                )
                return

            # Send initial processing status
            status_message = await update.message.reply_text(
                "🔄 Начинаю обработку файла..."
            )

            try:
                # Download and validate file
                file_obj = await context.bot.get_file(file.file_id)
                file_content = await file_obj.download_as_bytearray()
                file_size = len(file_content)
                max_size = max_image_size if is_image else max_text_size
                size_limit_mb = "15MB" if is_image else "30MB"

                if file_size > max_size:
                    await status_message.edit_text(
                        f"❌ Файл слишком большой. Максимальный размер - {size_limit_mb}."
                    )
                    return

                # Ensure we have a valid access token
                if not self.access_token and not self.get_access_token():
                    logger.error("Failed to obtain access token")
                    await status_message.edit_text(
                        "Ошибка авторизации в GigaChat API. Пожалуйста, попробуйте позже."
                    )
                    return

                # Upload file to GigaChat API
                logger.info("Uploading file to GigaChat API...")
                await status_message.edit_text("🔄 Загружаю файл в систему анализа...")

                # Prepare file upload
                file_name = file.file_name if hasattr(file, 'file_name') else f"file.{mime_type.split('/')[-1]}"
                files = {
                    'file': (file_name, io.BytesIO(file_content), mime_type)
                }

                logger.debug(f"Uploading file with name: {file_name}, mime_type: {mime_type}")

                # Upload file
                upload_response = self.session.post(
                    "https://gigachat.devices.sberbank.ru/api/v1/files",
                    headers={
                        "Authorization": f"Bearer {self.access_token}",
                        "Accept": "application/json"
                    },
                    data={'purpose': 'general'},
                    files=files,
                    verify=False
                )

                logger.debug(f"Upload response status: {upload_response.status_code}")
                logger.debug(f"Upload response: {upload_response.text[:200]}")

                if upload_response.status_code == 200:
                    upload_data = upload_response.json()
                    file_id = upload_data.get('id')

                    if not file_id:
                        raise ValueError("File ID not found in response")

                    # Update status
                    await status_message.edit_text("🔄 Анализирую содержимое...")

                    # Prepare analysis prompt based on file type
                    if is_image:
                        prompt = "Опиши подробно, что изображено на этой фотографии?"
                    else:
                        prompt = "Проанализируй содержимое документа и предоставь краткую сводку основных моментов."

                    # Send the analysis request
                    completion_response = self.session.post(
                        "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.access_token}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "GigaChat-Pro",
                            "messages": [
                                {
                                    "role": "user",
                                    "content": prompt,
                                    "attachments": [file_id]
                                }
                            ],
                            "temperature": 0.7,
                        },
                        verify=False
                    )

                    if completion_response.status_code == 200:
                        try:
                            response_data = completion_response.json()
                            analysis = response_data["choices"][0]["message"]["content"]
                            logger.info("Successfully received content analysis")
                            file_type = "изображения" if is_image else "документа"
                            await status_message.edit_text(f"📝 Результат анализа {file_type}:\n\n{analysis}")
                        except (KeyError, IndexError, ValueError) as e:
                            logger.error(f"Error parsing analysis response: {str(e)}")
                            await status_message.edit_text(
                                "❌ Ошибка при обработке ответа от API. Пожалуйста, попробуйте позже."
                            )
                    elif completion_response.status_code == 401:
                        logger.warning("Token expired during file analysis, attempting to refresh...")
                        if self.get_access_token():
                            logger.info("Token refreshed successfully, retrying file analysis")
                            return await self.process_file(update, context)
                        else:
                            await status_message.edit_text(
                                "❌ Ошибка авторизации. Пожалуйста, попробуйте позже."
                            )
                    else:
                        error_message = "Неизвестная ошибка"
                        try:
                            error_data = completion_response.json()
                            error_message = error_data.get("error", {}).get("message", error_message)
                        except:
                            pass

                        logger.error(f"Analysis failed: {completion_response.status_code} - {error_message}")
                        await status_message.edit_text(
                            f"❌ Ошибка при анализе файла: {error_message}"
                        )

                else:
                    logger.error(f"File upload failed: {upload_response.text}")
                    await status_message.edit_text(
                        "❌ Ошибка при загрузке файла. Пожалуйста, попробуйте позже."
                    )

            except Exception as e:
                logger.error(f"Error in file processing: {str(e)}", exc_info=True)
                await status_message.edit_text(
                    "❌ Произошла ошибка при обработке файла. Пожалуйста, попробуйте позже."
                )

        except Exception as e:
            logger.error(f"Error processing file: {str(e)}", exc_info=True)
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке файла. Пожалуйста, попробуйте позже."
            )

    def get_access_token(self):
        """Get access token from GigaChat API."""
        try:
            auth_string = f"{self.client_id}:{self.client_secret}"
            auth_key = base64.b64encode(auth_string.encode()).decode()
            request_id = str(uuid.uuid4())
            logger.debug("Making token request with request ID: %s", request_id)

            data = urlencode({
                "scope": "GIGACHAT_API_PERS",
            })

            logger.debug("Encoded form data: %s", data)

            response = self.session.post(
                "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                headers={
                    "Authorization": f"Basic {auth_key}",
                    "RqUID": request_id,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json"
                },
                data=data,
                verify=False
            )

            logger.debug("Token request response status: %s", response.status_code)
            logger.debug("Token request response: %s", response.text[:200])

            if response.status_code == 200:
                try:
                    data = response.json()
                    if "access_token" in data:
                        self.access_token = data["access_token"]
                        self.token_expiry = datetime.now() + timedelta(minutes=30)
                        logger.info("Successfully obtained new access token, expires at %s", self.token_expiry)
                        return True
                    else:
                        logger.error("Access token not found in response data: %s", data)
                        return False
                except ValueError as e:
                    logger.error("Failed to parse token response JSON: %s", str(e))
                    return False
            else:
                logger.error("Token request failed. Status: %s, Response: %s",
                          response.status_code, response.text[:200])
                return False

        except Exception as e:
            logger.error("Error getting access token: %s", str(e))
            return False

    def _token_update_loop(self):
        """Background thread to update the access token."""
        while not self._stop_event.is_set():
            try:
                current_time = datetime.now()
                if (not self.access_token or 
                    self.token_expiry is None or 
                    current_time + timedelta(minutes=5) >= self.token_expiry):
                    logger.info("Updating access token...")
                    self.get_access_token()
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error("Error in token update loop: %s", str(e))
                time.sleep(60)

    async def clear_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Очистить историю чата для пользователя."""
        chat_id = update.effective_chat.id
        if chat_id not in self.allowed_chat_ids:
            return

        # Сохраняем только системное сообщение при очистке
        if chat_id in self.chat_histories:
            system_message = {
                "role": "system",
                "content": "Ты — умный и дружелюбный ассистент. Отвечай подробно, но по существу. "
                "Поддерживай контекст диалога и учитывай предыдущие сообщения при ответе. "
                "Если не уверен в ответе, так и скажи."
            }
            self.chat_histories[chat_id] = [system_message]
            # Очищаем context_id
            if chat_id in self.chat_contexts:
                del self.chat_contexts[chat_id]
            await update.message.reply_text("✨ История чата очищена!")
        else:
            await update.message.reply_text("История чата уже пуста.")


def load_secrets():
    """Load secrets from secrets.yaml."""
    try:
        with open("secrets.yaml", "r", encoding="utf-8") as f:
            secrets = yaml.safe_load(f)
            logger.info("Secrets loaded successfully")
            logger.debug(f"Allowed chat IDs: {secrets.get('telegram_allowed_chat_ids')}")

            # Validate the authorization key
            auth_key = secrets.get("gigachat_authorization_key")
            if not auth_key:
                raise ValueError("GigaChat authorization key not found in secrets")

            try:
                # Try to decode the key to validate it
                decoded_auth = base64.b64decode(auth_key).decode()
                if ':' not in decoded_auth:
                    raise ValueError("Invalid authorization key format: missing client_id:client_secret separator")
                client_id, client_secret = decoded_auth.split(':', 1)
                if not client_id or not client_secret:
                    raise ValueError("Invalid client credentials in authorization key")
                logger.info("Successfully validated authorization key format")
                secrets["client_id"] = client_id
                secrets["client_secret"] = client_secret
            except Exception as e:
                raise ValueError(f"Invalid authorization key: {str(e)}")

            return secrets
    except Exception as e:
        logger.error(f"Error loading secrets: {str(e)}")
        raise

# Add lock file check
def is_bot_running():
    """Check if another instance of the bot is already running."""
    lock_file = "bot.lock"
    try:
        if os.path.exists(lock_file):
            # Проверяем, работает ли процесс
            with open(lock_file, 'r') as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 0)  # Проверка существования процесса
                logger.warning(f"Обнаружен работающий экземпляр бота (PID: {pid})")
                return True
            except OSError:
                # Процесс не существует, удаляем устаревший файл блокировки
                logger.info("Найден устаревший файл блокировки, удаляем")
                os.remove(lock_file)
                return False
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке файла блокировки: {e}")
        return False

def create_lock_file():
    """Create a lock file with current process ID."""
    lock_file = "bot.lock"
    try:
        with open(lock_file, 'w') as f:
            current_pid = os.getpid()
            f.write(str(current_pid))
            logger.info(f"Создан файл блокировки для PID: {current_pid}")
        return True
    except Exception as e:
        logger.error(f"Ошибка создания файла блокировки: {e}")
        return False

def remove_lock_file():
    """Remove the lock file."""
    lock_file = "bot.lock"
    try:
        if os.path.exists(lock_file):
            os.remove(lock_file)
            logger.info("Файл блокировки успешно удален")
    except Exception as e:
        logger.error(f"Ошибка удаления файла блокировки: {e}")

if __name__ == "__main__":
    try:
        if is_bot_running():
            logger.error("Другой экземпляр бота уже запущен.")
            sys.exit(1)

        if not create_lock_file():
            logger.error("Не удалось создать файл блокировки.")
            sys.exit(1)

        # Load configuration
        secrets = load_secrets()
        logger.info("Starting GigaChat Bot")

        # Initialize bot
        bot = GigaChatBot(
            bot_token=secrets["telegram_bot_api_key"],
            allowed_chat_ids=secrets["telegram_allowed_chat_ids"],
            client_id=secrets["client_id"],
            client_secret=secrets["client_secret"]
        )

        # Set up signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info("Получен сигнал завершения")
            remove_lock_file()
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        logger.info("Starting token update thread")
        bot.token_update_thread = threading.Thread(target=bot._token_update_loop, daemon=True)
        bot.token_update_thread.start()

        logger.info("Starting bot polling")
        Application.run_polling(bot.application, allowed_updates=Update.ALL_TYPES)

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error("Fatal error: %s", str(e))
    finally:
        remove_lock_file()
        sys.exit(0)