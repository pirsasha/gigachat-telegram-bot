# GigaChat Telegram Bot

Telegram бот с интеграцией GigaChat API для генерации и анализа изображений.

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/yourusername/gigachat-telegram-bot.git
cd gigachat-telegram-bot
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл `secrets.yaml` на основе `example.secrets.yaml`:
```yaml
telegram_bot_api_key: "YOUR_BOT_TOKEN"
telegram_allowed_chat_ids:
  - YOUR_CHAT_ID
gigachat_authorization_key: "YOUR_BASE64_ENCODED_KEY"
```

## Настройка

### Получение Telegram Bot Token
1. Обратитесь к [@BotFather](https://t.me/BotFather) в Telegram
2. Создайте нового бота командой `/newbot`
3. Следуйте инструкциям и получите токен бота

### Получение Chat ID
1. Добавьте [@userinfobot](https://t.me/userinfobot) в Telegram
2. Отправьте любое сообщение боту
3. Бот вернёт ваш Chat ID

### Настройка GigaChat API
1. Получите доступ к [GigaChat API](https://developers.sber.ru/portal/products/gigachat-api)
2. Создайте авторизационный ключ
3. Закодируйте ключ в формате Base64 (client_id:client_secret)

## Запуск

```bash
python main.py
```

## Функциональность

Бот поддерживает следующие команды и возможности:

1. `/start` - Начало работы с ботом
2. `/image [описание]` - Генерация изображения по текстовому описанию
3. Анализ отправленных изображений (JPG, PNG, TIFF, BMP до 15MB)
4. Анализ документов (TXT, CSV, MD, PDF, DOC, DOCX до 30MB)
5. Диалог с использованием GigaChat API

## Требования

- Python 3.11+
- Токен Telegram бота
- Ключ авторизации GigaChat API
