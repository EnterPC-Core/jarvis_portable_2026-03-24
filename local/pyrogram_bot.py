import os

try:
    from pyrogram import Client, filters
except ImportError as error:
    raise RuntimeError(
        "Pyrogram runtime не готов: установи зависимости из local/requirements-pyrogram.txt "
        "(минимум `pyrogram` и `TgCrypto`)."
    ) from error

try:
    from openai import OpenAI
except ImportError as error:
    raise RuntimeError(
        "Pyrogram runtime не готов: отсутствует пакет `openai`. "
        "Установи зависимости из local/requirements-pyrogram.txt."
    ) from error

API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH', '')
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
SYSTEM_PROMPT = os.getenv('SYSTEM_PROMPT', 'Ты — Кодекс. Отвечай кратко и по делу.')
SESSION_NAME = os.getenv('PYROGRAM_SESSION', 'bot')

missing = [
    name for name, value in {
        'API_ID': API_ID,
        'API_HASH': API_HASH,
        'BOT_TOKEN': BOT_TOKEN,
        'OPENAI_API_KEY': OPENAI_API_KEY,
    }.items() if not value
]

if missing:
    raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

client_ai = OpenAI(api_key=OPENAI_API_KEY)
app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


@app.on_message(filters.command('start'))
def start(client, message):
    message.reply('Я Кодекс. Задай вопрос.')


@app.on_message(filters.text & ~filters.command)
def codex_reply(client, message):
    try:
        response = client_ai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': message.text},
            ],
        )
        answer = response.choices[0].message.content or 'Пустой ответ от модели.'
        message.reply(answer)
    except Exception as error:
        message.reply(f'Ошибка: {error}')


if __name__ == '__main__':
    app.run()
