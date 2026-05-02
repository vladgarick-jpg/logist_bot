import logging
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardRemove, Update
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

import config
import database

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=config.TOKEN)
dp = Dispatcher()

# Инициализация БД
database.init_db()

# -------------------- ОБРАБОТКА КОМАНД --------------------

@dp.message(CommandStart())
async def start_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Отправь мне свой вопрос (текст или фото с описанием), и я передам его специалистам.",
        reply_markup=ReplyKeyboardRemove()
    )

# -------------------- ЛОГИКА ВОПРОСОВ (User -> Group) --------------------

@dp.message(F.chat.type == "private")
async def handle_logist_question(message: Message, state: FSMContext):
    await state.clear()
    
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.full_name
    
    # Собираем текст: либо само сообщение, либо описание к фото
    question_text = message.text or message.caption or "🖼 Фото без описания"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🛠 Я беру этот вопрос", callback_data="assign")]]
    )

    try:
        if message.photo:
            sent_message = await bot.send_photo(
                config.GROUP_CHAT_ID,
                message.photo[-1].file_id,
                caption=f"❓ <b>Новый вопрос от @{username}</b>\n\n{question_text}",
                parse_mode="HTML",
                reply_markup=keyboard
            )
        else:
            sent_message = await bot.send_message(
                config.GROUP_CHAT_ID,
                f"❓ <b>Новый вопрос от @{username}</b>\n\n{question_text}",
                parse_mode="HTML",
                reply_markup=keyboard
            )

        # Сохраняем в БД
        database.save_question(user_id, username, question_text, sent_message.message_id)
        await message.reply("✅ Ваш вопрос отправлен специалистам. Ожидайте ответ!")
        
    except Exception as e:
        logger.error(f"Ошибка при пересылке вопроса: {e}")
        await message.reply("❌ Произошла ошибка. Попробуйте позже.")

# -------------------- ПРИНЯТИЕ ВОПРОСА (Callback) --------------------

@dp.callback_query(F.data == "assign")
async def assign_specialist(callback: CallbackQuery):
    message_id = callback.message.message_id
    specialist_id = callback.from_user.id
    specialist_name = callback.from_user.full_name

    question_data = database.get_question_by_message_id(message_id)
    if not question_data:
        await callback.answer("⚠ Ошибка: вопрос не найден в базе.", show_alert=True)
        return

    database.assign_specialist_to_question(message_id, specialist_id, specialist_name)

    # Обновляем текст сообщения в группе
    new_caption = f"❓ <b>Новый вопрос от @{question_data[1]}</b>\n\n{question_data[2]}\n\n👷‍♂️ <b>Взял в работу: {specialist_name}</b>"
    
    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=new_caption, parse_mode="HTML", reply_markup=None)
        else:
            await callback.message.edit_text(text=new_caption, parse_mode="HTML", reply_markup=None)
    except Exception as e:
        logger.error(f"Ошибка при обновлении сообщения: {e}")

    await callback.answer("✅ Вы взяли вопрос!")

# -------------------- ОТВЕТ СПЕЦИАЛИСТА (Group -> User) --------------------

@dp.message(F.chat.id == config.GROUP_CHAT_ID, F.reply_to_message)
async def handle_specialist_answer(message: Message):
    original_msg_id = message.reply_to_message.message_id
    question_data = database.get_question_by_message_id(original_msg_id)

    if not question_data:
        return  # Это не ответ на вопрос из базы

    user_id, username, question_text, spec_id, spec_name = question_data
    
    final_spec_name = spec_name or message.from_user.full_name
    answer_header = f"🔹 <b>Ответ на ваш вопрос:</b>\n\n❓ {question_text}\n📌 Ответил: {final_spec_name}\n\n"

    try:
        if message.photo:
            await bot.send_photo(user_id, message.photo[-1].file_id, caption=f"{answer_header}{message.caption or ''}", parse_mode="HTML")
        elif message.document:
            await bot.send_document(user_id, message.document.file_id, caption=answer_header, parse_mode="HTML")
        elif message.video:
            await bot.send_video(user_id, message.video.file_id, caption=answer_header, parse_mode="HTML")
        else:
            await bot.send_message(user_id, f"{answer_header}{message.text}", parse_mode="HTML")
        
        await message.reply("✅ Ответ отправлен пользователю.")
    except Exception as e:
        logger.error(f"Не удалось отправить ответ пользователю: {e}")
        await message.reply("❌ Не удалось доставить ответ (возможно, бот заблокирован).")

# -------------------- WEBHOOK НАСТРОЙКИ --------------------

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = "https://logist-bot-7cw6.onrender.com" + WEBHOOK_PATH

async def handle_webhook(request):
    try:
        data = await request.json()
        update = Update(**data)
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error(f"Ошибка при обработке вебхука: {e}")
    return web.Response(text="OK")

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
    logger.info(f"Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close() # Важно для Render!
    logger.info("Сессия закрыта.")

def main():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", lambda r: web.Response(text="Bot is running!")) # Хелсчек для Render

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    web.run_app(app, host="0.0.0.0", port=10000)

if __name__ == "__main__":
    main()