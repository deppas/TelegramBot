import os
import telebot
import logging
from telebot import types
from datetime import datetime
from peewee import *
import requests
import config

bot = telebot.TeleBot(config.TOKEN)

db = SqliteDatabase('finance_bot.db')

logging.basicConfig(filename='user_log.txt', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class Expense(Model):
    user_id = IntegerField()
    amount = FloatField()
    description = CharField()
    date = DateTimeField(default=datetime.now)

    class Meta:
        database = db


db.create_tables([Expense])


def get_currency_rate(base_currency, target_currency):
    """
    Получите курс обмена валюты из API.
    """
    response = requests.get(
        f'{config.CURRENCY_API_BASE_URL}?access_key={config.CURRENCY_API_KEY}&base={base_currency}'
    )
    data = response.json()
    rate = data['rates'][target_currency]
    return rate


def send_inline_keyboard(chat_id, text, options):
    """
    Отправьте пользователю сообщение со встроенной клавиатурой.
    """
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    for option in options:
        callback_button = types.InlineKeyboardButton(
            text=option['text'], callback_data=option['callback_data']
        )
        keyboard.add(callback_button)
    bot.send_message(chat_id, text, reply_markup=keyboard)


@bot.message_handler(commands=['start'])
def handle_start(message):
    """
    Обработка команды /start от пользователя.
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    logging.info(f"User ID: {user_id}, Chat ID: {chat_id}, Command: /start")
    bot.send_message(
        chat_id, 'Добро пожаловать в Личный финансовый бот! Чем бы Вы хотели заняться?'
    )
    send_inline_keyboard(
        chat_id,
        'Выберите опцию:',
        [
            {'text': 'Добавить расходы', 'callback_data': 'add_expense'},
            {'text': 'Просмотр расходов', 'callback_data': 'view_expenses'},
            {'text': 'Конвертировать валюту', 'callback_data': 'convert_currency'},
            {'text': 'Загрузить файл', 'callback_data': 'upload_file'},
        ],
    )


@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    """
    Обработка запросов обратного вызова с встроенной клавиатуры.
    """
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    logging.info(f"User ID: {user_id}, Chat ID: {chat_id}, Callback Query: {call.data}")

    if call.data == 'add_expense':
        bot.send_message(chat_id, 'Пожалуйста, введите сумму:')
        bot.register_next_step_handler(call.message, add_expense_amount)
    elif call.data == 'view_expenses':
        expenses = Expense.select().where(Expense.user_id == user_id)
        total_expenses = sum(expense.amount for expense in expenses)
        bot.send_message(
            chat_id, f'Ваши общие расходы: {total_expenses} USD'
        )
        bot.send_message(chat_id, 'Вот ваши расходы:')
        for expense in expenses:
            bot.send_message(
                chat_id,
                f'{expense.amount} USD - {expense.description} ({expense.date.strftime("%Y-%m-%d %H:%M:%S")})',
            )
    elif call.data == 'convert_currency':
        bot.send_message(chat_id, 'Пожалуйста, введите сумму:')
        bot.register_next_step_handler(call.message, convert_currency_amount)
    elif call.data == 'upload_file':
        bot.send_message(chat_id, 'Пожалуйста, загрузите файл:')
        bot.register_next_step_handler(call.message, upload_file)
    else:
        bot.send_message(chat_id, 'Неверный вариант. Пожалуйста, выберите еще раз.')


def add_expense_amount(message):
    """
    Обработка пользовательского ввода для добавления суммы расходов.
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        amount = float(message.text)
        bot.send_message(chat_id, 'Введите описание расхода:')
        bot.register_next_step_handler(message, add_expense_description, amount)
    except ValueError:
        bot.send_message(chat_id, 'Неверный Ввод. Пожалуйста, введите действительную сумму.')


def add_expense_description(message, amount):
    """
    Обработка пользовательского ввода для добавления описания расходов.
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    description = message.text
    expense = Expense(user_id=user_id, amount=amount, description=description)
    expense.save()
    logging.info(f"User ID: {user_id}, Chat ID: {chat_id}, Added Expense: {description}")
    bot.send_message(chat_id, 'Расход успешно добавлен!')


def convert_currency_amount(message):
    """
    Обработка пользовательского ввода для конвертации суммы в валюте.
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        amount = float(message.text)
        bot.send_message(chat_id, 'Пожалуйста, введите базовую валюту (например, USD):')
        bot.register_next_step_handler(message, convert_currency_base_currency, amount)
    except ValueError:
        bot.send_message(chat_id, 'Неверный Ввод. Пожалуйста, введите действительную сумму.')


def convert_currency_base_currency(message, amount):
    """
    Обработка пользовательского ввода для конвертации валюты в базовую валюту.
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    base_currency = message.text.upper()
    bot.send_message(chat_id, 'Пожалуйста, введите целевую валюту (например, EUR):')
    bot.register_next_step_handler(message, convert_currency_target_currency, amount, base_currency)


def convert_currency_target_currency(message, amount, base_currency):
    """
    Обработка пользовательского ввода для преобразования валюты в целевую валюту.
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    target_currency = message.text.upper()
    try:
        rate = get_currency_rate(base_currency, target_currency)
        converted_amount = amount * rate
        bot.send_message(
            chat_id,
            f'{amount} {base_currency} is equivalent to {converted_amount} {target_currency}',
        )
    except requests.exceptions.RequestException:
        bot.send_message(chat_id, 'Не удалось получить курс обмена валюты. Пожалуйста, повторите попытку позже.')


def upload_file(message):
    """
    Обработка загрузки файлов пользователя.
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    if message.document:
        file_info = bot.get_file(message.document.file_id)
        file_url = f'https://api.telegram.org/file/bot{config.TOKEN}/{file_info.file_path}'
        bot.send_message(chat_id, f'Спасибо за загрузку файла! URL: {file_url}')
    else:
        bot.send_message(chat_id, 'Файл не найден. Пожалуйста, загрузите файл.')


if __name__ == '__main__':
    bot.polling(none_stop=True)
