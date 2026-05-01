import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
import config
import database

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.TOKEN)
dp = Dispatcher()

database.init_db()

# Обработчик команды /start
@dp.message(CommandStart())
async def start_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Отправь мне свой вопрос, и я передам его специалистам.",
        reply_markup=ReplyKeyboardRemove()
    )

# Обработчик вопросов от логистов (ЛС)
@dp.message(F.chat.type == "private")
async def handle_logist_question(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    question = message.text if message.text else "🖼 Фото без подписи"

    # Кнопка "Я беру этот вопрос"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🛠 Я беру этот вопрос", callback_data="assign")]]
    )

    # Отправляем вопрос в группу
    if message.photo:
        sent_message = await bot.send_photo(
            config.GROUP_CHAT_ID,
            message.photo[-1].file_id,
            caption=f"❓ <b>Новый вопрос от @{username}</b>\n\n{question}",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        sent_message = await bot.send_message(
            config.GROUP_CHAT_ID,
            f"❓ <b>Новый вопрос от @{username}</b>\n\n{question}",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    # ✅ Записываем в БД `message_id` из ГРУППЫ (не из ЛС!)
    database.save_question(user_id, username, question, sent_message.message_id)
    await message.reply("✅ Ваш вопрос отправлен специалистам. Ожидайте ответ!")

# Обработчик кнопки "Я беру этот вопрос"
@dp.callback_query(F.data == "assign")
async def assign_specialist(callback: CallbackQuery):
    message_id = callback.message.message_id  # Берём `message_id` из сообщения в группе
    specialist_id = callback.from_user.id
    specialist_name = callback.from_user.full_name

    question_data = database.get_question_by_message_id(message_id)
    if not question_data:
        await callback.answer("⚠ Ошибка: вопрос не найден.")
        return

    # ✅ Назначаем специалиста
    database.assign_specialist_to_question(message_id, specialist_id, specialist_name)

    # Обновляем сообщение в группе (убираем кнопку)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.edit_caption(
        caption=f"❓ <b>Новый вопрос от @{question_data[1]}</b>\n\n{question_data[2]}\n\n👷‍♂️ <b>Вопрос взял: {specialist_name}</b>",
        parse_mode="HTML"
    )

    await callback.answer("✅ Вопрос закреплён за вами!")

# Обработчик ответов от специалистов
@dp.message(F.chat.id == config.GROUP_CHAT_ID, F.reply_to_message)
async def handle_specialist_answer(message: Message):
    original_message_id = message.reply_to_message.message_id
    question_data = database.get_question_by_message_id(original_message_id)

    if question_data is None:
        return  

    user_id, username, question, specialist_id, specialist_name = question_data

    if not specialist_name:
        specialist_name = message.from_user.full_name

    text_answer = f"🔹 <b>Ответ на ваш вопрос:</b>\n\n❓ {question}\n📌 Ответил: {specialist_name}"

    if message.text:
        text_answer += f"\n\n{message.text}"

    if message.photo:
        await bot.send_photo(user_id, message.photo[-1].file_id, caption=text_answer, parse_mode="HTML")
        await message.reply("✅ Ответ с фото отправлен логисту.")
        return

    if message.document:
        await bot.send_document(user_id, message.document.file_id, caption=text_answer, parse_mode="HTML")
        await message.reply("✅ Ответ с файлом отправлен логисту.")
        return

    if message.video:
        await bot.send_video(user_id, message.video.file_id, caption=text_answer, parse_mode="HTML")
        await message.reply("✅ Ответ с видео отправлен логисту.")
        return

    await bot.send_message(user_id, text_answer, parse_mode="HTML")
    await message.reply("✅ Ответ отправлен логисту.")

async def main():
    database.init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
