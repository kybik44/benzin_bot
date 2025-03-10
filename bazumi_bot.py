import asyncio
import sqlite3
import logging
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InputMediaPhoto,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    CallbackContext,
    ConversationHandler,
)
from telegram.error import NetworkError, Forbidden

# Глобальные переменные
application = None
participate_handler = None

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect("bazumi_bot.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)""")
    c.execute(
        """CREATE TABLE IF NOT EXISTS contests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        photo_id TEXT,
        title TEXT,
        end_date TEXT,
        status TEXT DEFAULT 'active',
        message_id INTEGER
    )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS participants (
        contest_id INTEGER,
        user_id INTEGER,
        username TEXT,
        phone_number TEXT,
        PRIMARY KEY (contest_id, user_id)
    )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        photo_id TEXT,
        title TEXT,
        text TEXT,
        message_id INTEGER
    )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS verified_users (
        user_id INTEGER PRIMARY KEY,
        phone_number TEXT,
        verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )"""
    )
    c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (6357518457,))
    conn.commit()
    conn.close()


# Проверка администратора
def is_admin(user_id):
    conn = sqlite3.connect("bazumi_bot.db")
    c = conn.cursor()
    c.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
    result = c.fetchone() is not None
    conn.close()
    return result


def is_user_verified(user_id):
    conn = sqlite3.connect("bazumi_bot.db")
    c = conn.cursor()
    c.execute("SELECT 1 FROM verified_users WHERE user_id = ?", (user_id,))
    result = c.fetchone() is not None
    conn.close()
    return result


def mark_user_verified(user_id, phone_number):
    conn = sqlite3.connect("bazumi_bot.db")
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO verified_users (user_id, phone_number) VALUES (?, ?)",
        (user_id, phone_number),
    )
    conn.commit()
    conn.close()


def verify_specific_user(user_id, phone_number):
    """Добавляет конкретного пользователя в базу данных верифицированных пользователей"""
    conn = sqlite3.connect("bazumi_bot.db")
    c = conn.cursor()

    # Проверяем, существует ли пользователь в базе
    c.execute("SELECT 1 FROM verified_users WHERE user_id = ?", (user_id,))
    exists = c.fetchone() is not None

    if not exists:
        # Добавляем пользователя в базу верифицированных
        c.execute(
            "INSERT INTO verified_users (user_id, phone_number) VALUES (?, ?)",
            (user_id, phone_number),
        )
        conn.commit()
        result = True
    else:
        result = False

    conn.close()
    return result


# Вспомогательные функции
def validate_date(date_str):
    try:
        datetime.strptime(date_str, "%d.%m.%Y")
        return True
    except ValueError:
        return False


def format_contest_preview(title, date):
    return f"""На этой неделе мы разыгрываем <b>{title}</b>
Условия очень простые:
• нажать "<u>принять участие</u>"
• быть подписанным на канал <b>@BAZUMI_discountt</b>
• дождаться результатов, они будут <b>{date}</b> в нашем канале"""


def format_contest_notification(title, date):
    return f"""На этой неделе мы разыгрываем <b>{title}</b>
Условия очень простые:
• нажать "<u>принять участие</u>"
• быть подписанным на канал <b>@BAZUMI_discountt</b>
• дождаться результатов, они будут <b>{date}</b> в нашем канале
<i>Присоединяйся!</i>"""


def format_post_preview(title, text):
    return f"<b>{title}</b>\n\n{text}"


# Работа с базой данных
def add_admin(user_id):
    conn = sqlite3.connect("bazumi_bot.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()


def remove_admin(user_id):
    conn = sqlite3.connect("bazumi_bot.db")
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def create_contest(photo_id, title, end_date):
    conn = sqlite3.connect("bazumi_bot.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO contests (photo_id, title, end_date) VALUES (?, ?, ?)",
        (photo_id, title, end_date),
    )
    contest_id = c.lastrowid
    conn.commit()
    conn.close()
    return contest_id


def get_active_contest():
    conn = sqlite3.connect("bazumi_bot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM contests WHERE status = 'active' LIMIT 1")
    contest = c.fetchone()
    conn.close()
    return contest


def update_contest(contest_id, photo_id, title, end_date):
    conn = sqlite3.connect("bazumi_bot.db")
    c = conn.cursor()
    c.execute(
        "UPDATE contests SET photo_id = ?, title = ?, end_date = ? WHERE id = ?",
        (photo_id, title, end_date, contest_id),
    )
    conn.commit()
    conn.close()


def delete_contest_db(contest_id):
    """Удаляет конкурс из базы данных"""
    conn = sqlite3.connect("bazumi_bot.db")
    c = conn.cursor()
    c.execute("UPDATE contests SET status = 'inactive' WHERE id = ?", (contest_id,))
    conn.commit()
    conn.close()


def add_participant(contest_id, user_id, username, phone_number):
    """Добавляет участника конкурса в базу данных"""
    conn = sqlite3.connect("bazumi_bot.db")
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO participants (contest_id, user_id, username, phone_number) VALUES (?, ?, ?, ?)",
        (contest_id, user_id, username, phone_number),
    )
    conn.commit()
    conn.close()


def get_participants(contest_id):
    conn = sqlite3.connect("bazumi_bot.db")
    c = conn.cursor()
    c.execute(
        "SELECT username, phone_number FROM participants WHERE contest_id = ?",
        (contest_id,),
    )
    participants = c.fetchall()
    conn.close()
    return participants


def is_participant(contest_id, user_id):
    conn = sqlite3.connect("bazumi_bot.db")
    c = conn.cursor()
    c.execute(
        "SELECT 1 FROM participants WHERE contest_id = ? AND user_id = ?",
        (contest_id, user_id),
    )
    result = c.fetchone() is not None
    conn.close()
    return result


def create_post(photo_id, title, text):
    """Создает новый пост в базе данных"""
    conn = sqlite3.connect("bazumi_bot.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO posts (photo_id, title, text) VALUES (?, ?, ?)",
        (photo_id, title, text),
    )
    post_id = c.lastrowid
    conn.commit()
    conn.close()
    return post_id


# Состояния для ConversationHandler
(
    CREATE_CONTEST_PHOTO,
    CREATE_CONTEST_TITLE,
    CREATE_CONTEST_DATE,
    CREATE_CONTEST_PREVIEW,
) = range(4)
EDIT_CONTEST_PHOTO, EDIT_CONTEST_TITLE, EDIT_CONTEST_DATE, EDIT_CONTEST_PREVIEW = range(
    4, 8
)
CREATE_POST_PHOTO, CREATE_POST_TITLE, CREATE_POST_TEXT, CREATE_POST_PREVIEW = range(
    8, 12
)
PARTICIPATE_CONFIRM = 12


# Главная панель администратора
async def admin_panel(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("У вас нет доступа к админ-панели.")
        return
    keyboard = [
        [InlineKeyboardButton("Конкурс", callback_data="contest")],
        [InlineKeyboardButton("Пост", callback_data="post")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await update.message.reply_text(
            "Административная панель:", reply_markup=reply_markup
        )
    except NetworkError:
        await update.message.reply_text(
            "Ошибка сети. Проверьте подключение к интернету и попробуйте снова."
        )
    except Forbidden:
        await update.message.reply_text(
            "Бот был заблокирован вами. Разблокируйте бота, чтобы продолжить."
        )
        
        
async def back_to_admin_panel(update, context):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        await query.edit_message_text("У вас нет доступа к админ-панели.")
        return
    keyboard = [
        [InlineKeyboardButton("Конкурс", callback_data="contest")],
        [InlineKeyboardButton("Пост", callback_data="post")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.edit_message_text(
            "Административная панель:", reply_markup=reply_markup
        )
    except NetworkError:
        await query.edit_message_text(
            "Ошибка сети. Проверьте подключение к интернету и попробуйте снова."
        )
    except Forbidden:
        await query.edit_message_text(
            "Бот был заблокирован вами. Разблокируйте бота, чтобы продолжить."
        )


# Меню конкурса
async def contest_menu(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Создать новый конкурс", callback_data="create_contest")],
        [
            InlineKeyboardButton(
                "Редактировать текущий конкурс", callback_data="edit_contest"
            )
        ],
        [
            InlineKeyboardButton(
                "Удалить текущий конкурс", callback_data="delete_contest"
            )
        ],
        [
            InlineKeyboardButton(
                "Уведомление о текущем конкурсе", callback_data="notify_contest"
            )
        ],
        [
            InlineKeyboardButton(
                "Выгрузить участников", callback_data="export_participants"
            )
        ],
        [InlineKeyboardButton("Назад", callback_data="back_to_admin_panel")], 
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Управление конкурсом:", reply_markup=reply_markup)


# Создание конкурса
async def start_create_contest(update, context):
    # Важно: сначала сохраняем состояние, потом отвечаем
    logger.info(f"Starting create contest for user {update.effective_user.id}")

    # Явно устанавливаем состояние в контексте пользователя
    context.user_data["conversation_state"] = CREATE_CONTEST_PHOTO

    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Загрузите фото для конкурса.")

    # Логируем переход в состояние
    logger.info(
        f"Set state to CREATE_CONTEST_PHOTO for user {update.effective_user.id}"
    )

    return CREATE_CONTEST_PHOTO


async def create_contest_photo(update, context):
    # Проверяем, не обрабатывается ли уже это фото
    if (
        context.user_data.get("photo_being_processed")
        and context.user_data.get("photo_processed_id") == update.message.message_id
    ):
        logger.info(
            f"Skipping duplicate processing of photo {update.message.message_id}"
        )
        return CREATE_CONTEST_PHOTO

    logger.info(
        f"User {update.effective_user.id} sent a message in create_contest_photo."
    )
    logger.info(f"Message content: {update.message}")

    # Отмечаем, что это фото обрабатывается
    context.user_data["photo_being_processed"] = True
    context.user_data["photo_processed_id"] = update.message.message_id

    # Проверяем все возможные типы фото
    if update.message.photo:
        # Telegram отправляет несколько размеров, берем последний (самый большой)
        context.user_data["contest_photo"] = update.message.photo[-1].file_id
        logger.info(
            f"Photo received with file_id: {context.user_data['contest_photo']}"
        )

        try:
            # Обновляем состояние в user_data
            context.user_data["conversation_state"] = CREATE_CONTEST_TITLE

            await update.message.reply_text("Введите название разыгрываемого предмета.")
            logger.info(f"Photo accepted, moving to title.")

            # Сбрасываем флаг обработки
            context.user_data["photo_being_processed"] = False
            return CREATE_CONTEST_TITLE
        except Exception as e:
            logger.error(f"Error after photo upload: {e}")
            # Сбрасываем флаг обработки
            context.user_data["photo_being_processed"] = False
            return CREATE_CONTEST_PHOTO

    elif (
        update.message.document
        and update.message.document.mime_type
        and update.message.document.mime_type.startswith("image/")
    ):
        context.user_data["contest_photo"] = update.message.document.file_id
        logger.info(
            f"Document image received with file_id: {context.user_data['contest_photo']}"
        )

        try:
            await update.message.reply_text("Введите название разыгрываемого предмета.")
            logger.info(f"Document photo accepted, moving to title.")
            return CREATE_CONTEST_TITLE
        except Exception as e:
            logger.error(f"Error after document photo upload: {e}")
            return CREATE_CONTEST_PHOTO

    else:
        logger.warning(f"No photo detected in message: {update.message}")
        await update.message.reply_text(
            "Пожалуйста, загрузите фото (не документ или видео)."
        )
        # Сбрасываем флаг обработки
        context.user_data["photo_being_processed"] = False
        return CREATE_CONTEST_PHOTO


async def create_contest_title(update, context):
    context.user_data["contest_title"] = update.message.text
    try:
        await update.message.reply_text("Введите дату окончания (ДД.ММ.ГГГГ).")
    except NetworkError:
        await update.message.reply_text(
            "Ошибка сети. Проверьте подключение и попробуйте снова."
        )
        return CREATE_CONTEST_TITLE
    except Forbidden:
        await update.message.reply_text(
            "Бот заблокирован. Разблокируйте его в Telegram."
        )
        return CREATE_CONTEST_TITLE
    return CREATE_CONTEST_DATE


async def create_contest_date(update, context):
    date_str = update.message.text
    if not validate_date(date_str):
        try:
            await update.message.reply_text(
                "Некорректный формат даты. Введите в формате ДД.ММ.ГГГГ."
            )
        except NetworkError:
            await update.message.reply_text(
                "Ошибка сети. Проверьте подключение и попробуйте снова."
            )
        except Forbidden:
            await update.message.reply_text(
                "Бот заблокирован. Разблокируйте его в Telegram."
            )
        return CREATE_CONTEST_DATE
    context.user_data["contest_date"] = date_str
    preview = format_contest_preview(context.user_data["contest_title"], date_str)
    keyboard = [
        [InlineKeyboardButton("Опубликовать конкурс", callback_data="publish_contest")],
        [
            InlineKeyboardButton(
                "Редактировать конкурс", callback_data="edit_contest_preview"
            )
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await update.message.reply_photo(
            photo=context.user_data["contest_photo"],
            caption=preview,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    except NetworkError:
        await update.message.reply_text(
            "Ошибка сети. Проверьте подключение и попробуйте снова."
        )
        return CREATE_CONTEST_DATE
    except Forbidden:
        await update.message.reply_text(
            "Бот заблокирован. Разблокируйте его в Telegram."
        )
        return CREATE_CONTEST_DATE
    return CREATE_CONTEST_PREVIEW


async def create_contest_preview(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "publish_contest":
        try:
            contest_id = create_contest(
                context.user_data["contest_photo"],
                context.user_data["contest_title"],
                context.user_data["contest_date"],
            )
            preview = format_contest_preview(
                context.user_data["contest_title"], context.user_data["contest_date"]
            )

            # Добавляем кнопку "Принять участие в конкурсе"
            keyboard = [
                [
                    InlineKeyboardButton(
                        "Принять участие в конкурсе", callback_data="participate"
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Отправляем сообщение в канал и сохраняем message_id
            sent_message = await context.bot.send_photo(
                chat_id="@testkybik",
                photo=context.user_data["contest_photo"],
                caption=preview,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
            # Сохраняем message_id в базе данных, связав с contest_id
            conn = sqlite3.connect("bazumi_bot.db")
            c = conn.cursor()
            c.execute(
                "UPDATE contests SET message_id = ? WHERE id = ?",
                (sent_message.message_id, contest_id),
            )
            conn.commit()
            conn.close()

            # Отправляем подтверждение администратору
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text="Конкурс опубликован!"
            )

            # Возвращаем в меню конкурса после паузы
            await asyncio.sleep(1)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Управление конкурсом:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "Создать новый конкурс", callback_data="create_contest"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Редактировать текущий конкурс",
                                callback_data="edit_contest",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Удалить текущий конкурс",
                                callback_data="delete_contest",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Уведомление о текущем конкурсе",
                                callback_data="notify_contest",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Выгрузить участников",
                                callback_data="export_participants",
                            )
                        ],
                        [InlineKeyboardButton("Назад", callback_data="back_to_admin_panel")], 
                    ]
                ),
            )
        except Exception as e:
            logger.error(f"Error publishing contest: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Ошибка при публикации конкурса: {str(e)}",
            )
            await asyncio.sleep(1)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Управление конкурсом:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "Создать новый конкурс", callback_data="create_contest"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Редактировать текущий конкурс",
                                callback_data="edit_contest",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Удалить текущий конкурс",
                                callback_data="delete_contest",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Уведомление о текущем конкурсе",
                                callback_data="notify_contest",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Выгрузить участников",
                                callback_data="export_participants",
                            )
                        ],
                        [InlineKeyboardButton("Назад", callback_data="back_to_admin_panel")], 
                    ]
                ),
            )
    elif query.data == "edit_contest_preview":
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Загрузите фото для конкурса."
        )
        context.user_data["conversation_state"] = CREATE_CONTEST_PHOTO
        return CREATE_CONTEST_PHOTO

    return ConversationHandler.END


# Редактирование конкурса
async def start_edit_contest(update, context):
    contest = get_active_contest()
    if not contest:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "Нет активных конкурсов для редактирования."
        )
        return ConversationHandler.END

    # Сохраняем ID конкурса в user_data
    context.user_data["contest_id"] = contest[0]

    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Загрузите новое фото для конкурса.")

    # Устанавливаем состояние в user_data
    context.user_data["conversation_state"] = EDIT_CONTEST_PHOTO

    return EDIT_CONTEST_PHOTO


async def edit_contest_photo(update, context):
    # Проверяем, не обрабатывается ли уже это фото
    if (
        context.user_data.get("photo_being_processed")
        and context.user_data.get("photo_processed_id") == update.message.message_id
    ):
        logger.info(
            f"Skipping duplicate processing of photo {update.message.message_id} in edit_contest_photo"
        )
        return EDIT_CONTEST_TITLE

    logger.info(f"User {update.effective_user.id} sent a photo in edit_contest_photo.")

    # Отмечаем, что это фото обрабатывается
    context.user_data["photo_being_processed"] = True
    context.user_data["photo_processed_id"] = update.message.message_id

    try:
        if update.message.photo:
            context.user_data["contest_photo"] = update.message.photo[-1].file_id
            logger.info(
                f"Photo received with file_id: {context.user_data['contest_photo']}"
            )

            # Обновляем состояние в user_data
            context.user_data["conversation_state"] = EDIT_CONTEST_TITLE

            await update.message.reply_text(
                "Введите новое название разыгрываемого предмета."
            )
            logger.info(f"Photo accepted for edit, moving to title.")

            # Сбрасываем флаг обработки
            context.user_data["photo_being_processed"] = False
            return EDIT_CONTEST_TITLE
        else:
            logger.warning(f"No photo detected in message: {update.message}")
            await update.message.reply_text(
                "Пожалуйста, загрузите фото (не документ или видео)."
            )

            # Сбрасываем флаг обработки
            context.user_data["photo_being_processed"] = False
            return EDIT_CONTEST_PHOTO
    except Exception as e:
        logger.error(f"Error in edit_contest_photo: {e}")
        await update.message.reply_text(
            "Произошла ошибка при обработке фото. Пожалуйста, попробуйте снова."
        )

        # Сбрасываем флаг обработки
        context.user_data["photo_being_processed"] = False
        return EDIT_CONTEST_PHOTO


async def edit_contest_title(update, context):
    # Проверяем, не обрабатывается ли уже этот текст
    if (
        context.user_data.get("title_being_processed")
        and context.user_data.get("title_processed_id") == update.message.message_id
    ):
        logger.info(
            f"Skipping duplicate processing of title {update.message.message_id} in edit_contest_title"
        )
        return EDIT_CONTEST_DATE

    # Отмечаем, что этот текст обрабатывается
    context.user_data["title_being_processed"] = True
    context.user_data["title_processed_id"] = update.message.message_id

    try:
        context.user_data["contest_title"] = update.message.text
        logger.info(f"Title received: {context.user_data['contest_title']}")

        # Обновляем состояние в user_data
        context.user_data["conversation_state"] = EDIT_CONTEST_DATE

        await update.message.reply_text(
            "Введите новую дату окончания конкурса в формате ДД.ММ.ГГГГ"
        )

        # Сбрасываем флаг обработки
        context.user_data["title_being_processed"] = False
        return EDIT_CONTEST_DATE
    except Exception as e:
        logger.error(f"Error in edit_contest_title: {e}")
        await update.message.reply_text(
            "Произошла ошибка. Пожалуйста, введите название снова."
        )

        # Сбрасываем флаг обработки
        context.user_data["title_being_processed"] = False
        return EDIT_CONTEST_TITLE


async def edit_contest_date(update, context):
    date_str = update.message.text
    if not validate_date(date_str):
        await update.message.reply_text(
            "Некорректный формат даты. Введите в формате ДД.ММ.ГГГГ."
        )
        return EDIT_CONTEST_DATE
    context.user_data["contest_date"] = date_str
    preview = format_contest_preview(context.user_data["contest_title"], date_str)
    keyboard = [
        [
            InlineKeyboardButton(
                "Завершить редактирование", callback_data="finish_edit_contest"
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_photo(
        photo=context.user_data["contest_photo"],
        caption=preview,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )
    return EDIT_CONTEST_PREVIEW


async def edit_contest_preview(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "finish_edit_contest":
        try:
            # Проверяем наличие contest_id
            if "contest_id" not in context.user_data:
                contest = get_active_contest()
                if contest:
                    context.user_data["contest_id"] = contest[0]
                else:
                    logger.error("No active contest found for editing.")
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="Ошибка: не найден активный конкурс для редактирования.",
                    )
                    await asyncio.sleep(1)
                    await show_contest_menu(update, context)
                    return ConversationHandler.END

            # Обновляем данные конкурса в базе
            update_contest(
                context.user_data["contest_id"],
                context.user_data["contest_photo"],
                context.user_data["contest_title"],
                context.user_data["contest_date"],
            )

            # Получаем message_id из базы данных
            conn = sqlite3.connect("bazumi_bot.db")
            c = conn.cursor()
            c.execute(
                "SELECT message_id FROM contests WHERE id = ?",
                (context.user_data["contest_id"],),
            )
            result = c.fetchone()
            conn.close()

            logger.info(
                f"Retrieved message_id from DB for contest {context.user_data['contest_id']}: {result}"
            )

            preview = format_contest_preview(
                context.user_data["contest_title"], context.user_data["contest_date"]
            )
            keyboard = [
                [
                    InlineKeyboardButton(
                        "Принять участие в конкурсе", callback_data="participate"
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if result and result[0]:
                message_id = result[0]
                logger.info(
                    f"Attempting to edit message with message_id: {message_id} in chat @testkybik"
                )
                try:
                    await context.bot.edit_message_media(
                        chat_id="@testkybik",
                        message_id=message_id,
                        media=InputMediaPhoto(
                            media=context.user_data["contest_photo"],
                            caption=preview,
                            parse_mode="HTML",
                        ),
                        reply_markup=reply_markup,
                    )
                    logger.info("Contest successfully edited in channel.")
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="Конкурс успешно обновлен в канале!",
                    )
                except Exception as edit_error:
                    logger.error(f"Failed to edit message: {edit_error}")
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"Ошибка при редактировании сообщения в канале: {str(edit_error)}. Пожалуйста, проверьте права бота или удалите старое сообщение вручную.",
                    )
            else:
                logger.warning(
                    f"No message_id found for contest {context.user_data['contest_id']}. Publishing new message."
                )
                # Если message_id не найден, отправляем новое сообщение
                sent_message = await context.bot.send_photo(
                    chat_id="@testkybik",
                    photo=context.user_data["contest_photo"],
                    caption=preview,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
                # Сохраняем новый message_id
                conn = sqlite3.connect("bazumi_bot.db")
                c = conn.cursor()
                c.execute(
                    "UPDATE contests SET message_id = ? WHERE id = ?",
                    (sent_message.message_id, context.user_data["contest_id"]),
                )
                conn.commit()
                conn.close()
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, text="Конкурс обновлен, но оригинальное сообщение не найдено. Опубликовано новое.",
                )

            # Возвращаем в меню конкурса
            await asyncio.sleep(1)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Управление конкурсом:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "Создать новый конкурс", callback_data="create_contest"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Редактировать текущий конкурс",
                                callback_data="edit_contest",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Удалить текущий конкурс",
                                callback_data="delete_contest",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Уведомление о текущем конкурсе",
                                callback_data="notify_contest",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Выгрузить участников",
                                callback_data="export_participants",
                            )
                        ],
                        [InlineKeyboardButton("Назад", callback_data="back_to_admin_panel")], 
                    ]
                ),
            )
        except Exception as e:
            logger.error(f"Error updating contest: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Ошибка при обновлении конкурса: {str(e)}",
            )
            await asyncio.sleep(1)
            await show_contest_menu(update, context)

    return ConversationHandler.END


# Удаление конкурса
async def delete_contest(update, context):
    query = update.callback_query
    await query.answer()

    contest = get_active_contest()
    if not contest:
        await query.edit_message_text("Нет активных конкурсов для удаления.")
        return

    # Сохраняем ID конкурса в user_data для последующего использования
    context.user_data["contest_id"] = contest[0]
    context.user_data["contest_title"] = contest[2]

    await query.edit_message_text(
        f"Уверены, что хотите удалить конкурс {contest[2]}?",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Да", callback_data="confirm_delete")],
                [InlineKeyboardButton("Нет", callback_data="cancel_delete")],
            ]
        ),
    )


async def confirm_delete(update, context):
    query = update.callback_query
    await query.answer()

    # Получаем ID конкурса из user_data
    contest_id = context.user_data.get("contest_id")

    if not contest_id:
        logger.error("No contest_id found in user_data for deletion.")
        await query.edit_message_text("Ошибка: не найден конкурс для удаления.")
        await asyncio.sleep(1)
        await show_contest_menu(update, context)
        return

    try:
        # Извлекаем message_id из базы данных
        conn = sqlite3.connect("bazumi_bot.db")
        c = conn.cursor()
        c.execute("SELECT message_id FROM contests WHERE id = ?", (contest_id,))
        result = c.fetchone()
        conn.close()

        logger.info(f"Retrieved message_id for contest {contest_id}: {result}")

        if result and result[0]:
            message_id = result[0]
            logger.info(
                f"Attempting to delete message {message_id} from channel @testkybik"
            )
            try:
                await context.bot.delete_message(
                    chat_id="@testkybik", message_id=message_id
                )
                logger.info(f"Message {message_id} successfully deleted from channel.")
            except Exception as delete_error:
                logger.warning(f"Failed to delete message from channel: {delete_error}")
                # Продолжаем удаление из базы, даже если сообщение не удалось удалить
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"Предупреждение: не удалось удалить сообщение из канала: {str(delete_error)}. Конкурс будет удален из базы данных.",
                )

        # Удаляем конкурс из базы данных
        delete_contest_db(contest_id)
        logger.info(f"Contest {contest_id} successfully removed from database.")

        await query.edit_message_text("Конкурс успешно удален.")
        await asyncio.sleep(1)
        await show_contest_menu(update, context)
    except Exception as e:
        logger.error(f"Error deleting contest: {e}")
        await query.edit_message_text(f"Ошибка при удалении конкурса: {str(e)}")
        await asyncio.sleep(1)
        await show_contest_menu(update, context)


async def cancel_delete(update, context):
    query = update.callback_query
    await query.answer()

    # Очищаем данные о конкурсе из user_data
    if "contest_id" in context.user_data:
        del context.user_data["contest_id"]
    if "contest_title" in context.user_data:
        del context.user_data["contest_title"]

    # Возвращаемся в меню конкурса
    keyboard = [
        [InlineKeyboardButton("Создать новый конкурс", callback_data="create_contest")],
        [
            InlineKeyboardButton(
                "Редактировать текущий конкурс", callback_data="edit_contest"
            )
        ],
        [
            InlineKeyboardButton(
                "Удалить текущий конкурс", callback_data="delete_contest"
            )
        ],
        [
            InlineKeyboardButton(
                "Уведомление о текущем конкурсе", callback_data="notify_contest"
            )
        ],
        [
            InlineKeyboardButton(
                "Выгрузить участников", callback_data="export_participants"
            )
        ],
        [InlineKeyboardButton("Назад", callback_data="back_to_admin_panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Управление конкурсом:", reply_markup=reply_markup)


# Уведомление о конкурсе
async def notify_contest(update, context):
    query = update.callback_query
    await query.answer()
    
    contest = get_active_contest()
    if not contest:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Нет активного конкурса для уведомления."
        )
        await asyncio.sleep(1)
        await show_contest_menu(update, context)
        return
    
    notification = format_contest_notification(contest[2], contest[3])
    keyboard = [
        [InlineKeyboardButton("Принять участие в конкурсе", callback_data="participate")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        # Отправляем уведомление в личный чат администратора (или текущего пользователя)
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,  # Личный чат, а не канал
            photo=contest[1],
            caption=notification,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Уведомление о конкурсе отправлено в ваш чат!"
        )
        await asyncio.sleep(1)
        await show_contest_menu(update, context)
    except Exception as e:
        logger.error(f"Error sending contest notification: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Ошибка при отправке уведомления: {str(e)}"
        )
        await asyncio.sleep(1)
        await show_contest_menu(update, context)


# Участие в конкурсе
async def participate(update, context):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id  # ID канала или личного чата
    channel_id = "@BAZUMI_discountt"
    
    logger.info(f"participate called for user {user_id} from chat {chat_id}")
    
    try:
        contest = get_active_contest()
        if not contest:
            # Если действие из канала, отправляем в личку
            is_channel_or_group = update.effective_chat.type in ['channel', 'group', 'supergroup']
            target_chat_id = user_id if is_channel_or_group else chat_id
            await context.bot.send_message(
                chat_id=target_chat_id, 
                text="К сожалению, в данный момент нет активных конкурсов."
            )
            return ConversationHandler.END
        
        contest_id = contest[0]
        context.user_data["contest_id"] = contest_id
        logger.info(f"Setting contest_id={contest_id} in user_data for user {user_id}")
        
        # Проверяем, является ли пользователь уже участником
        already_participant = is_participant(contest_id, user_id)
        logger.info(f"User {user_id} is already participant: {already_participant}")
        
        if already_participant:
            text = "Вы уже зарегистрированы в этом конкурсе!"
            is_channel_or_group = update.effective_chat.type in ['channel', 'group', 'supergroup']
            logger.info(f"User {user_id} is already registered, chat type: {update.effective_chat.type}")
            
            if is_channel_or_group:
                try:
                    await context.bot.send_message(
                        chat_id=user_id, 
                        text=text, 
                        parse_mode='HTML'
                    )
                    logger.info(f"Sent 'already registered' message to user {user_id} in private chat")
                except Exception as e:
                    logger.error(f"Error sending private message to user {user_id}: {e}")
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"@{update.effective_user.username}, пожалуйста, начните диалог с ботом, чтобы продолжить: https://t.me/{context.bot.username}"
                    )
            else:
                keyboard = [[InlineKeyboardButton('Назад', callback_data='go_back')],
                           [InlineKeyboardButton('В главное меню', callback_data='go_to_main_menu')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=text, 
                    reply_markup=reply_markup, 
                    parse_mode='HTML'
                )
                logger.info(f"Sent 'already registered' message with buttons to user {user_id}")
            return ConversationHandler.END
        
        # Проверяем подписку на канал
        try:
            chat_member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            status = chat_member.status
            logger.info(f"User {user_id} subscription status: {status}")
        except Exception as e:
            logger.error(f"Error checking subscription for user {user_id}: {e}")
            is_channel_or_group = update.effective_chat.type in ['channel', 'group', 'supergroup']
            target_chat_id = user_id if is_channel_or_group else chat_id
            await context.bot.send_message(
                chat_id=target_chat_id, 
                text="Произошла ошибка при проверке подписки. Пожалуйста, попробуйте позже."
            )
            return ConversationHandler.END
        
        if status in ["member", "administrator", "creator"]:
            is_channel_or_group = update.effective_chat.type in ['channel', 'group', 'supergroup']
            
            context.user_data["conversation_state"] = PARTICIPATE_CONFIRM
            logger.info(f"Setting conversation_state to PARTICIPATE_CONFIRM for user {user_id}")
            
            if is_channel_or_group:
                context.user_data['started_from_channel'] = True
                logger.info(f"Setting started_from_channel=True for user {user_id}")
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="Чтобы принять участие – подтвердите, что вы не бот. Мы не передаем ваши данные третьим лицам.",
                        reply_markup=ReplyKeyboardMarkup(
                            [[KeyboardButton("Я не бот🤖", request_contact=True)]],
                            one_time_keyboard=True,
                            resize_keyboard=True
                        )
                    )
                    logger.info(f"Requesting contact for user {user_id} in personal chat")
                    return PARTICIPATE_CONFIRM
                except Exception as e:
                    logger.error(f"Error sending private message: {e}")
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"@{update.effective_user.username}, пожалуйста, начните диалог с ботом, чтобы принять участие: https://t.me/{context.bot.username}"
                    )
                    return ConversationHandler.END
            # Логика для личного чата
            await context.bot.send_message(
                chat_id=chat_id,
                text="Чтобы принять участие – подтвердите, что вы не бот. Мы не передаем ваши данные третьим лицам.",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("Я не бот🤖", request_contact=True)]],
                    one_time_keyboard=True,
                    resize_keyboard=True
                )
            )
            logger.info(f"Requesting contact for user {user_id} in chat {chat_id}")
            return PARTICIPATE_CONFIRM
        
        else:
            # Отправляем сообщение о подписке в личный чат, а не в канал
            is_channel_or_group = update.effective_chat.type in ['channel', 'group', 'supergroup']
            target_chat_id = user_id if is_channel_or_group else chat_id
            try:
                await context.bot.send_message(
                    chat_id=target_chat_id,
                    text="Чтобы участвовать в конкурсе, подпишитесь на канал @BAZUMI_discountt!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Подписаться", url="https://t.me/BAZUMI_discountt")],
                        [InlineKeyboardButton("Проверить подписку", callback_data="check_subscription")]
                    ])
                )
                logger.info(f"Sent subscription prompt to user {user_id} in chat {target_chat_id}")
            except Exception as e:
                logger.error(f"Error sending subscription message to {target_chat_id}: {e}")
                if is_channel_or_group:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"@{update.effective_user.username}, пожалуйста, начните диалог с ботом, чтобы продолжить: https://t.me/{context.bot.username}"
                    )
            return ConversationHandler.END
    
    except Exception as e:
        logger.error(f"Error in participate for user {user_id}: {e}", exc_info=True)
        is_channel_or_group = update.effective_chat.type in ['channel', 'group', 'supergroup']
        target_chat_id = user_id if is_channel_or_group else chat_id
        try:
            await context.bot.send_message(
                chat_id=target_chat_id, 
                text="Произошла ошибка при проверке подписки. Пожалуйста, попробуйте позже."
            )
        except Exception as e2:
            logger.error(f"Error sending error message: {e2}")
        return ConversationHandler.END


async def check_subscription(update, context):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    channel_id = "@BAZUMI_discountt"

    # Защита от повторных нажатий
    if context.user_data.get("checking_subscription"):
        logger.info(f"User {user_id} already checking subscription, skipping")
        return ConversationHandler.END
    context.user_data["checking_subscription"] = True

    try:
        chat_member = await context.bot.get_chat_member(
            chat_id=channel_id, user_id=user_id
        )
        status = chat_member.status
        logger.info(f"User {user_id} subscription status: {status}")

        if status in ["member", "administrator", "creator"]:
            # Пользователь подписан
            contest = get_active_contest()
            if not contest:
                await query.edit_message_text(
                    text="К сожалению, в данный момент нет активных конкурсов.",
                    reply_markup=None  # Удаляем клавиатуру
                )
                context.user_data["checking_subscription"] = False
                return ConversationHandler.END

            context.user_data["contest_id"] = contest[0]
            # Отправляем новое сообщение вместо редактирования, чтобы избежать конфликта клавиатур
            await query.message.reply_text(
                text="Отлично, вы подписаны! Подтвердите, что вы не бот.",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("Я не бот🤖", request_contact=True)]],
                    one_time_keyboard=True,
                    resize_keyboard=True,
                ),
            )
            # Удаляем старое сообщение с inline-клавиатурой
            await query.message.delete()
            logger.info(f"User {user_id} subscribed, requesting contact")
            context.user_data["checking_subscription"] = False
            return PARTICIPATE_CONFIRM

        else:
            # Пользователь не подписан
            current_text = query.message.text
            new_text = "Вы ещё не подписаны на @BAZUMI_discountt. Подпишитесь, чтобы участвовать!"
            new_reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Подписаться", url="https://t.me/BAZUMI_discountt"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "Проверить подписку", callback_data="check_subscription"
                        )
                    ],
                ]
            )

            if current_text == new_text:
                logger.info(f"User {user_id} not subscribed, message unchanged, skipping edit")
                context.user_data["checking_subscription"] = False
                return ConversationHandler.END

            await query.edit_message_text(
                text=new_text,
                reply_markup=new_reply_markup
            )
            logger.info(f"User {user_id} not subscribed, prompting again")
            context.user_data["checking_subscription"] = False
            return ConversationHandler.END

    except telegram.error.BadRequest as e:
        logger.error(f"BadRequest error for user {user_id}: {e}")
        await query.edit_message_text(
            text="Ошибка при проверке подписки. Попробуйте снова позже.",
            reply_markup=None
        )
        context.user_data["checking_subscription"] = False
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Unexpected error re-checking subscription for user {user_id}: {e}", exc_info=True)
        await query.edit_message_text(
            text="Ошибка при проверке подписки. Попробуйте снова позже.",
            reply_markup=None
        )
        context.user_data["checking_subscription"] = False
        return ConversationHandler.END


async def check_subscription_gifts(update, context):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    channel_id = "@BAZUMI_discountt"

    try:
        chat_member = await context.bot.get_chat_member(
            chat_id=channel_id, user_id=user_id
        )
        status = chat_member.status

        if status in ["member", "administrator", "creator"]:
            contest = get_active_contest()
            if not contest:
                await query.edit_message_text(
                    "К сожалению, в данный момент нет активных конкурсов."
                )
                return

            contest_id = contest[0]
            context.user_data["contest_id"] = contest_id

            if is_participant(contest_id, user_id):
                text = "Вы уже зарегистрированы в этом конкурсе!"
                keyboard = [
                    [InlineKeyboardButton("Назад", callback_data="go_back")],
                    [
                        InlineKeyboardButton(
                            "В главное меню", callback_data="go_to_main_menu"
                        )
                    ],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
                # await show_main_menu(update, context, is_end_of_flow=True)
                return

            if is_user_verified(user_id):
                conn = sqlite3.connect("bazumi_bot.db")
                c = conn.cursor()
                c.execute(
                    "SELECT phone_number FROM verified_users WHERE user_id = ?",
                    (user_id,),
                )
                result = c.fetchone()
                conn.close()

                if result and result[0]:
                    phone_number = result[0]
                    add_participant(
                        contest_id,
                        user_id,
                        update.effective_user.username,
                        phone_number,
                    )
                    text = "Отлично, вы зарегистрированы как участник. Желаем вам удачи и остаемся на связи! Ваш Bazumi ♥️"
                    keyboard = [
                        [InlineKeyboardButton("Назад", callback_data="go_back")],
                        [
                            InlineKeyboardButton(
                                "В главное меню", callback_data="go_to_main_menu"
                            )
                        ],
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode="HTML",
                    )
                    # await show_main_menu(update, context, is_end_of_flow=True)
                    return

            # Устанавливаем section для корректной обработки
            context.user_data["section"] = "gifts"
            text = "Чтобы принять участие – подтвердите, что вы не бот. Мы не передаем ваши данные третьим лицам."
            keyboard = [[KeyboardButton("Я не бот🤖", request_contact=True)]]
            reply_markup = ReplyKeyboardMarkup(
                keyboard, one_time_keyboard=True, resize_keyboard=True
            )
            await context.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="HTML"
            )
            return PARTICIPATE_CONFIRM

        else:
            await query.edit_message_text(
                "Вы ещё не подписаны на @BAZUMI_discountt. Подпишитесь, чтобы участвовать!",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "Подписаться", url="https://t.me/BAZUMI_discountt"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Проверить подписку",
                                callback_data="check_subscription_gifts",
                            )
                        ],
                    ]
                ),
            )
            return

    except Exception as e:
        logger.error(f"Error re-checking subscription in check_subscription_gifts: {e}")
        await query.edit_message_text(
            "Ошибка при проверке подписки. Попробуйте снова позже."
        )
        return


async def confirm_participate(update, context):
    query = update.callback_query
    await query.answer()
    logger.info(f"confirm_participate called for user {update.effective_user.id}")
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    channel_id = "@BAZUMI_discountt"

    try:
        contest = get_active_contest()
        if not contest:
            await context.bot.send_message(
                chat_id=chat_id,
                text="К сожалению, в данный момент нет активных конкурсов.",
            )
            return

        contest_id = contest[0]
        # Важно: сохраняем contest_id в user_data для последующего использования в receive_contact
        context.user_data["contest_id"] = contest_id
        logger.info(f"Setting contest_id={contest_id} in user_data for user {user_id}")

        if is_participant(contest_id, user_id):
            text = "Вы уже зарегистрированы в этом конкурсе!"
            keyboard = [
                [InlineKeyboardButton("Назад", callback_data="go_back")],
                [
                    InlineKeyboardButton(
                        "В главное меню", callback_data="go_to_main_menu"
                    )
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="HTML"
            )
            # await show_main_menu(update, context, is_end_of_flow=True)
            return

        chat_member = await context.bot.get_chat_member(
            chat_id=channel_id, user_id=user_id
        )
        status = chat_member.status

        if status in ["member", "administrator", "creator"]:
            # Явно устанавливаем состояние в контексте пользователя
            context.user_data["conversation_state"] = PARTICIPATE_CONFIRM
            logger.info(f"Setting conversation_state to PARTICIPATE_CONFIRM for user {user_id}")
            
            text = "Чтобы принять участие – подтвердите, что вы не бот. Мы не передаем ваши данные третьим лицам."
            keyboard = [[KeyboardButton("Я не бот🤖", request_contact=True)]]
            reply_markup = ReplyKeyboardMarkup(
                keyboard, one_time_keyboard=True, resize_keyboard=True
            )
            await context.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="HTML"
            )
            logger.info(f"Returning PARTICIPATE_CONFIRM for user {update.effective_user.id}")
            return PARTICIPATE_CONFIRM

        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Чтобы участвовать в конкурсе, подпишитесь на канал @BAZUMI_discountt!",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "Подписаться", url="https://t.me/BAZUMI_discountt"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "Проверить подписку",
                                callback_data="check_subscription_gifts",
                            )
                        ],
                    ]
                ),
            )
            return
    except Exception as e:
        logger.error(f"Error in confirm_participate: {e}")
        await context.bot.send_message(
            chat_id=chat_id, text="Произошла ошибка при проверке подписки..."
        )
        return


async def receive_contact(update, context):
    user = update.effective_user
    contact = update.message.contact
    logger.info(f"receive_contact called for user {user.id} with contact {contact.phone_number}")

    # Проверяем, находится ли пользователь в состоянии ConversationHandler
    is_in_conversation = False
    for group, handlers in context.application.handlers.items():
        for handler in handlers:
            if isinstance(handler, ConversationHandler) and handler.name == "participate_conversation":
                state = handler._conversations.get((update.effective_chat.id, user.id))
                if state is not None:
                    is_in_conversation = True
                    logger.info(f"User {user.id} is in conversation state: {state}")
                    break
        if is_in_conversation:
            break

    # Если контакт пришел вне ConversationHandler и нет флага обработки
    if not is_in_conversation and not context.user_data.get("contact_processed"):
        logger.info(f"User {user.id} is not in conversation, processing contact from channel")
        context.user_data["contact_processed"] = True  # Устанавливаем флаг обработки
    elif is_in_conversation and not context.user_data.get("contact_processed"):
        logger.info(f"User {user.id} is in conversation, processing contact")
        context.user_data["contact_processed"] = True  # Устанавливаем флаг обработки
    else:
        logger.info(f"Contact for user {user.id} already processed, skipping")
        return ConversationHandler.END

    try:
        contest_id = context.user_data.get("contest_id")
        if not contest_id:
            contest = get_active_contest()
            if contest:
                contest_id = contest[0]
                context.user_data["contest_id"] = contest_id
                logger.info(f"Retrieved contest_id from active contest: {contest_id}")
            else:
                logger.warning("No active contest found in receive_contact")
                await update.message.reply_text(
                    "Ошибка: не найден активный конкурс.",
                    reply_markup=ReplyKeyboardRemove()
                )
                context.user_data["contact_processed"] = False
                return ConversationHandler.END

        if is_participant(contest_id, user.id):
            text = "Вы уже зарегистрированы в этом конкурсе!"
            keyboard = [
                [InlineKeyboardButton('Назад', callback_data='go_back')],
                [InlineKeyboardButton('В главное меню', callback_data='go_to_main_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            await show_main_menu(update, context, is_end_of_flow=True)
            context.user_data["contact_processed"] = False
            return ConversationHandler.END

        logger.info(f"Adding participant: contest_id={contest_id}, user_id={user.id}")
        add_participant(contest_id, user.id, user.username, contact.phone_number)
        logger.info(f"Marking user {user.id} as verified with phone {contact.phone_number}")
        mark_user_verified(user.id, contact.phone_number)

        text = "Отлично, вы зарегистрированы как участник. Желаем вам удачи и остаемся на связи! Ваш Bazumi ♥️"
        logger.info(f"Sending confirmation message to user {user.id}")

        await update.message.reply_text(
            text=text,
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"Confirmation message sent to user {user.id}")

        is_channel_or_group = context.user_data.get('started_from_channel', False)
        if not is_channel_or_group:
            keyboard = [
                [InlineKeyboardButton('Назад', callback_data='go_back')],
                [InlineKeyboardButton('В главное меню', callback_data='go_to_main_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=user.id,
                text="Вы можете вернуться в меню:",
                reply_markup=reply_markup
            )

        await show_main_menu(update, context, is_end_of_flow=True)
        logger.info(f"Successfully registered user {user.id} in contest {contest_id}")

        # Очистка состояния
        if 'awaiting_contact' in context.user_data:
            del context.user_data['awaiting_contact']
        if 'started_from_channel' in context.user_data:
            del context.user_data['started_from_channel']
        if 'checking_subscription' in context.user_data:
            del context.user_data['checking_subscription']
        context.user_data["contact_processed"] = False

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in receive_contact for user {user.id}: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "Произошла ошибка при регистрации. Пожалуйста, попробуйте снова.",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data["contact_processed"] = False
        return ConversationHandler.END


# Выгрузка участников
async def export_participants(update, context):
    query = update.callback_query
    await query.answer()

    contest = get_active_contest()
    if not contest:
        logger.info("No active contest found for exporting participants.")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Нет активного конкурса для выгрузки участников.",
        )
        await asyncio.sleep(1)
        await show_contest_menu(update, context)
        return

    logger.info(f"Exporting participants for contest ID: {contest[0]}")
    participants = get_participants(contest[0])

    if not participants:
        logger.info(f"No participants found for contest ID: {contest[0]}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Нет участников для выгрузки."
        )
        await asyncio.sleep(1)
        await show_contest_menu(update, context)
        return

    # Формируем список участников
    participants_text = (
        f"Список участников конкурса '{contest[2]}' (ID: {contest[0]}):\n\n"
    )
    for p in participants:
        username = p[0] if p[0] else "Без имени"  # p[0] - username
        phone_number = p[1]  # p[1] - phone_number
        participants_text += f"@{username} - {phone_number}\n"

    logger.info(f"Participants exported: {len(participants)} entries")

    # Отправляем список участников
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=participants_text
    )

    await asyncio.sleep(1)
    await show_contest_menu(update, context)


# Создание поста
async def start_create_post(update, context):
    """Начало создания поста"""
    logger.info(f"Starting create post for user {update.effective_user.id}")

    # Устанавливаем состояние в user_data
    context.user_data["conversation_state"] = CREATE_POST_PHOTO

    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Загрузите фото для поста.")

    return CREATE_POST_PHOTO


async def create_post_photo(update, context):
    # Проверяем, не обрабатывается ли уже это фото
    if (
        context.user_data.get("photo_being_processed")
        and context.user_data.get("photo_processed_id") == update.message.message_id
    ):
        logger.info(
            f"Skipping duplicate processing of photo {update.message.message_id} in create_post_photo"
        )
        return CREATE_POST_TITLE

    logger.info(f"User {update.effective_user.id} sent a photo in create_post_photo.")

    # Отмечаем, что это фото обрабатывается
    context.user_data["photo_being_processed"] = True
    context.user_data["photo_processed_id"] = update.message.message_id

    try:
        if update.message.photo:
            context.user_data["post_photo"] = update.message.photo[-1].file_id
            logger.info(
                f"Photo received with file_id: {context.user_data['post_photo']}"
            )

            # Обновляем состояние в user_data
            context.user_data["conversation_state"] = CREATE_POST_TITLE

            await update.message.reply_text("Введите заголовок поста.")
            logger.info(f"Photo accepted for post, moving to title.")

            # Сбрасываем флаг обработки
            context.user_data["photo_being_processed"] = False
            return CREATE_POST_TITLE
        else:
            logger.warning(f"No photo detected in message: {update.message}")
            await update.message.reply_text(
                "Пожалуйста, загрузите фото (не документ или видео)."
            )

            # Сбрасываем флаг обработки
            context.user_data["photo_being_processed"] = False
            return CREATE_POST_PHOTO
    except Exception as e:
        logger.error(f"Error in create_post_photo: {e}")
        await update.message.reply_text(
            "Произошла ошибка при обработке фото. Пожалуйста, попробуйте снова."
        )

        # Сбрасываем флаг обработки
        context.user_data["photo_being_processed"] = False
        return CREATE_POST_PHOTO


async def create_post_title(update, context):
    # Проверяем, не обрабатывается ли уже этот текст
    if (
        context.user_data.get("title_being_processed")
        and context.user_data.get("title_processed_id") == update.message.message_id
    ):
        logger.info(
            f"Skipping duplicate processing of title {update.message.message_id} in create_post_title"
        )
        return CREATE_POST_TEXT

    # Отмечаем, что этот текст обрабатывается
    context.user_data["title_being_processed"] = True
    context.user_data["title_processed_id"] = update.message.message_id

    try:
        context.user_data["post_title"] = update.message.text
        logger.info(f"Post title received: {context.user_data['post_title']}")

        # Обновляем состояние в user_data
        context.user_data["conversation_state"] = CREATE_POST_TEXT

        await update.message.reply_text("Введите основной текст поста.")

        # Сбрасываем флаг обработки
        context.user_data["title_being_processed"] = False
        return CREATE_POST_TEXT
    except Exception as e:
        logger.error(f"Error in create_post_title: {e}")
        await update.message.reply_text(
            "Произошла ошибка. Пожалуйста, введите заголовок снова."
        )

        # Сбрасываем флаг обработки
        context.user_data["title_being_processed"] = False
        return CREATE_POST_TITLE


async def create_post_text(update, context):
    # Проверяем, не обрабатывается ли уже этот текст
    if (
        context.user_data.get("text_being_processed")
        and context.user_data.get("text_processed_id") == update.message.message_id
    ):
        logger.info(
            f"Skipping duplicate processing of text {update.message.message_id} in create_post_text"
        )
        return CREATE_POST_PREVIEW

    # Отмечаем, что этот текст обрабатывается
    context.user_data["text_being_processed"] = True
    context.user_data["text_processed_id"] = update.message.message_id

    try:
        context.user_data["post_text"] = update.message.text
        logger.info(f"Post text received: {context.user_data['post_text']}")

        # Обновляем состояние в user_data
        context.user_data["conversation_state"] = CREATE_POST_PREVIEW

        # Формируем превью поста
        preview = format_post_preview(
            context.user_data["post_title"], context.user_data["post_text"]
        )

        # Отправляем превью с фото
        keyboard = [
            [InlineKeyboardButton("Опубликовать пост", callback_data="publish_post")],
            [
                InlineKeyboardButton(
                    "Редактировать пост", callback_data="edit_post_preview"
                )
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=context.user_data["post_photo"],
            caption=preview,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )

        # Сбрасываем флаг обработки
        context.user_data["text_being_processed"] = False
        return CREATE_POST_PREVIEW
    except Exception as e:
        logger.error(f"Error in create_post_text: {e}")
        await update.message.reply_text(
            "Произошла ошибка. Пожалуйста, введите текст поста снова."
        )

        # Сбрасываем флаг обработки
        context.user_data["text_being_processed"] = False
        return CREATE_POST_TEXT


async def create_post_preview(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "publish_post":
        try:
            post_id = create_post(
                context.user_data["post_photo"],
                context.user_data["post_title"],
                context.user_data["post_text"],
            )
            preview = format_post_preview(
                context.user_data["post_title"], context.user_data["post_text"]
            )

            # Проверяем, есть ли message_id для редактирования
            conn = sqlite3.connect("bazumi_bot.db")
            c = conn.cursor()
            c.execute("SELECT message_id FROM posts WHERE id = ?", (post_id,))
            result = c.fetchone()
            conn.close()

            if result and result[0]:
                # Редактируем существующее сообщение
                await context.bot.edit_message_media(
                    chat_id="@testkybik",
                    message_id=result[0],
                    media=telegram.InputMediaPhoto(
                        media=context.user_data["post_photo"],
                        caption=preview,
                        parse_mode="HTML",
                    ),
                )
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Пост успешно обновлен в канале!",
                )
            else:
                # Отправляем новое сообщение и сохраняем message_id
                sent_message = await context.bot.send_photo(
                    chat_id="@testkybik",
                    photo=context.user_data["post_photo"],
                    caption=preview,
                    parse_mode="HTML",
                )
                conn = sqlite3.connect("bazumi_bot.db")
                c = conn.cursor()
                c.execute(
                    "UPDATE posts SET message_id = ? WHERE id = ?",
                    (sent_message.message_id, post_id),
                )
                conn.commit()
                conn.close()
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, text="Пост опубликован!"
                )

            # Возвращаем в меню админа
            await asyncio.sleep(1)
            keyboard = [
                [InlineKeyboardButton("Конкурс", callback_data="contest")],
                [InlineKeyboardButton("Пост", callback_data="post")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Административная панель:",
                reply_markup=reply_markup,
            )
        except Exception as e:
            logger.error(f"Error publishing post: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Ошибка при публикации поста: {str(e)}",
            )
            await asyncio.sleep(1)
            keyboard = [
                [InlineKeyboardButton("Конкурс", callback_data="contest")],
                [InlineKeyboardButton("Пост", callback_data="post")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Административная панель:",
                reply_markup=reply_markup,
            )
    elif query.data == "edit_post_preview":
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Загрузите фото для поста."
        )
        context.user_data["conversation_state"] = CREATE_POST_PHOTO
        return CREATE_POST_PHOTO

    return ConversationHandler.END


# Отмена диалога
async def cancel(update, context):
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END


# Управление администраторами
async def add_admin_command(update, context):
    if update.effective_user.id != 6357518457:
        await update.message.reply_text(
            "Только суперадминистратор может добавлять администраторов."
        )
        return
    try:
        user_id = int(context.args[0])
        add_admin(user_id)
        await update.message.reply_text(f"Администратор {user_id} добавлен.")
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Укажите Telegram ID администратора: /add_admin <ID>"
        )


async def remove_admin_command(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("У вас нет прав администратора.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("Использование: /remove_admin user_id")
        return

    user_id = int(context.args[0])
    remove_admin(user_id)
    await update.message.reply_text(
        f"Пользователь {user_id} удален из администраторов."
    )


async def verify_user_command(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("У вас нет прав администратора.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /verify_user user_id phone_number"
        )
        return

    try:
        user_id = int(context.args[0])
        phone_number = context.args[1]

        result = verify_specific_user(user_id, phone_number)

        if result:
            await update.message.reply_text(
                f"Пользователь {user_id} успешно верифицирован с номером {phone_number}."
            )
        else:
            await update.message.reply_text(
                f"Пользователь {user_id} уже был верифицирован ранее."
            )
    except ValueError:
        await update.message.reply_text("Ошибка: user_id должен быть числом.")
    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка: {str(e)}")


# Основные функции бота для пользователей
async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    context.user_data["history"] = ["main_menu"]  # Инициализируем историю
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"<b>Привет, {user.first_name}!</b> Я бот <b>Bazumi</b> - ваш помощник в мире игрушек. Чем могу помочь?",
        parse_mode="HTML",
    )
    await show_main_menu(update, context)


async def show_main_menu(
    update: Update, context: CallbackContext, is_end_of_flow: bool = False
) -> None:
    keyboard = [
        [InlineKeyboardButton("Служба заботы ♥️", callback_data="support")],
        [InlineKeyboardButton("Еженедельные подарки 🎁", callback_data="gifts")],
        [InlineKeyboardButton("Видеоинструкции 📹", callback_data="videos")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if "history" not in context.user_data:
        context.user_data["history"] = []
    if "main_menu" not in context.user_data["history"]:
        context.user_data["history"].append("main_menu")

    if is_end_of_flow:
        image_path = "images/question.png"
        try:
            with open(image_path, "rb") as photo:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=photo,
                    caption="<b>Если у вас остались вопросы, выберите нужный раздел</b>",
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
        except FileNotFoundError:
            logger.error(f"Image file {image_path} not found.")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="<b>Если у вас остались вопросы, выберите нужный раздел</b>",
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Error sending photo: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="<b>Если у вас остались вопросы, выберите нужный раздел</b>",
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="<b>Выберите раздел:</b>",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )


async def support_section(update: Update, context: CallbackContext) -> None:
    text = (
        "<b>Трудности иногда случаются, но Bazumi всегда на связи.</b> Здесь вы можете:\n"
        "• Получить <i>консультации</i> по выбору игрушек\n"
        "• Решить вопрос с <i>браком или поломкой</i>\n"
        "• Получить помощь в <i>выборе подарка</i>\n"
        "• Оставить ваш <i>отзыв или пожелание</i>"
    )
    keyboard = [
        [
            InlineKeyboardButton(
                "Связаться с менеджером", callback_data="contact_manager"
            )
        ],
        [InlineKeyboardButton("В главное меню", callback_data="go_to_main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    image_path = "images/care.png"

    context.user_data["history"].append("support_section")

    try:
        with open(image_path, "rb") as photo:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo,
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
    except FileNotFoundError:
        logger.error(f"Image file {image_path} not found.")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Error sending photo: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )


async def contact_manager(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    context.user_data["history"].append("contact_manager")

    if is_user_verified(user_id):
        text = "Это <b>Алексей</b> – ваш личный менеджер <u>Службы заботы</u>. Напишите и мы поможем с решением любого вопроса."
        keyboard = [
            [InlineKeyboardButton("Написать Алексею", url="https://t.me/AlexeyBazumi")],
            [InlineKeyboardButton("Назад", callback_data="go_back")],
            [InlineKeyboardButton("В главное меню", callback_data="go_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        # await show_main_menu(update, context, is_end_of_flow=True)
    else:
        text = "Чтобы продолжить – подтвердите, что вы <b>не бот</b>. Мы <u>не передаем</u> ваши данные третьим лицам."
        keyboard = [
            [
                InlineKeyboardButton(
                    "Я не бот🤖", callback_data="confirm_not_bot_support"
                )
            ],
            [InlineKeyboardButton("Назад", callback_data="go_back")],
            [InlineKeyboardButton("В главное меню", callback_data="go_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        except NetworkError:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Ошибка сети. Проверьте подключение и попробуйте снова.",
            )


async def confirm_not_bot_support(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    context.user_data['history'].append('confirm_not_bot_support')
    
    if is_user_verified(user_id):
        context.user_data['section'] = 'support'
        text = 'Это Алексей – ваш личный менеджер Службы заботы. Напишите и мы поможем с решением любого вопроса.'
        keyboard = [
            [InlineKeyboardButton('Написать Алексею', url='https://t.me/AlexeyBazumi')],
            [InlineKeyboardButton('Назад', callback_data='go_back')],
            [InlineKeyboardButton('В главное меню', callback_data='go_to_main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        # await show_main_menu(update, context, is_end_of_flow=True)
    else:
        context.user_data['section'] = 'support'
        text = (
            'Чтобы продолжить – подтвердите, что вы <b>не бот</b>. '
            'Мы <u>не передаем</u> ваши данные третьим лицам.\n'
            'Пожалуйста, поделитесь своим номером телефона.'
        )
        keyboard = [
            [KeyboardButton('Я не бот🤖', request_contact=True)]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        # Здесь можно добавить обработку контакта через ConversationHandler, если требуется

async def confirm_not_bot_videos(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    
    if is_user_verified(user_id):
        context.user_data['section'] = 'videos'
        video_type = context.user_data.get('video_type')
        
        if video_type == 'bazumi':
            text = 'Спасибо! Отправляем вам ссылки на плейлист с нашими инструкциями. Выберите удобную для вас площадку.'
            keyboard = [
                [InlineKeyboardButton('Rutube', url='https://rutube.ru/playlist')],
                [InlineKeyboardButton('Youtube', url='https://youtube.com/playlist')],
                            [InlineKeyboardButton('Назад', callback_data='go_back')],
            [InlineKeyboardButton('В главное меню', callback_data='go_to_main_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)
        elif video_type == 'other':
            text = 'Спасибо! К сожалению, у нас нет инструкций к другим игрушкам в открытом доступе – но у нас есть Служба заботы, где вам всегда помогут.'
            keyboard = [[InlineKeyboardButton('Написать Алексею', url='https://t.me/AlexeyBazumi')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)
        
        # await show_main_menu(update, context)
    else:
        context.user_data['section'] = 'videos'
        await request_contact(update, context)


async def gifts_section(update: Update, context: CallbackContext) -> None:
    text = (
        "<b>Еженедельные подарки 🎁</b>\n"
        "Два раза в неделю мы проводим <u>розыгрыш</u> среди подписчиков нашего канала. "
        "У каждого есть шанс выиграть <b>самые топовые модели</b> из нашего ассортимента!"
    )
    keyboard = [
        [InlineKeyboardButton("Отлично, я в деле!", callback_data="participate_gifts")],
        [InlineKeyboardButton("В главное меню", callback_data="go_to_main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    image_path = "images/contest.png"

    context.user_data["history"].append("gifts_section")

    try:
        with open(image_path, "rb") as photo:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo,
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
    except FileNotFoundError:
        logger.error(f"Image file {image_path} not found.")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Error sending photo: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )


async def participate_gifts(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    context.user_data["history"].append("participate_gifts")
    contest = get_active_contest()

    if contest:
        text = format_contest_preview(contest[2], contest[3])
        contest_id = contest[0]
    else:
        text = (
            "На этой неделе мы разыгрываем Набор Bazumi Ultra Puper Super\n"
            "Условия очень простые:\n"
            '- нажать "принять участие"\n'
            "- быть подписанным на канал @testkybik\n"
            "- дождаться результатов, они будут скоро в нашем канале"
        )
        contest_id = None  # Если конкурса нет, contest_id не используется

    # Проверяем, участвует ли пользователь уже в конкурсе
    if contest and is_participant(contest_id, user_id):
        text = "Вы уже зарегистрированы в этом конкурсе!"
        keyboard = [
            [InlineKeyboardButton("Назад", callback_data="go_back")],
            [InlineKeyboardButton("В главное меню", callback_data="go_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        # await show_main_menu(update, context, is_end_of_flow=True)
        await update.callback_query.answer()
        return

    # Если пользователь верифицирован и конкурс есть
    if is_user_verified(user_id) and contest:
        conn = sqlite3.connect("bazumi_bot.db")
        c = conn.cursor()
        c.execute(
            "SELECT phone_number FROM verified_users WHERE user_id = ?", (user_id,)
        )
        result = c.fetchone()
        conn.close()

        if result and result[0]:
            phone_number = result[0]
            add_participant(
                contest_id, user_id, update.effective_user.username, phone_number
            )
            text = "Отлично, вы зарегистрированы как участник. Желаем вам удачи и остаемся на связи! Ваш Bazumi ♥️"
            keyboard = [
                [InlineKeyboardButton("Назад", callback_data="go_back")],
                [InlineKeyboardButton("В главное меню", callback_data="go_to_main_menu")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
            # await show_main_menu(update, context, is_end_of_flow=True)
            await update.callback_query.answer()
            return

    # Если пользователь не верифицирован или конкурса нет
    keyboard = [
        [InlineKeyboardButton("Принять участие", callback_data="confirm_participate")],
        [InlineKeyboardButton("Назад", callback_data="go_back")],
        [InlineKeyboardButton("В главное меню", callback_data="go_to_main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )
    await update.callback_query.answer()


async def confirm_not_bot_gifts(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    # Check if user is already verified
    if is_user_verified(user_id):
        # Skip verification and proceed directly
        context.user_data["section"] = "gifts"
        contest = get_active_contest()
        if contest:
            # Get phone number from verified_users table
            conn = sqlite3.connect("bazumi_bot.db")
            c = conn.cursor()
            c.execute(
                "SELECT phone_number FROM verified_users WHERE user_id = ?", (user_id,)
            )
            result = c.fetchone()
            conn.close()

            if result and result[0]:
                phone_number = result[0]
                add_participant(
                    contest[0], user_id, update.effective_user.username, phone_number
                )
                text = "Отлично, вы зарегистрированы как участник. Желаем вам удачи и остаемся на связи! Ваш Bazumi ♥️"
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, text=text
                )
                await show_main_menu(update, context)
            else:
                # Fallback if phone number not found
                await request_contact(update, context)
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="В данный момент нет активных конкурсов.",
            )
            await show_main_menu(update, context)
    else:
        # User needs to verify
        context.user_data["section"] = "gifts"
        await request_contact(update, context)


async def request_contact(update, context):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Пожалуйста, поделитесь своим номером телефона.",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("Отправить контакт 💌", request_contact=True)]],
            one_time_keyboard=True,
        ),
    )


async def videos_section(update: Update, context: CallbackContext) -> None:
    text = "Сначала давайте определимся — с <b>какой игрушкой</b> вам нужна помощь!"
    keyboard = [
        [InlineKeyboardButton("Роботы Bazumi", callback_data="videos_bazumi")],
        [InlineKeyboardButton("Другое", callback_data="videos_other")],
        [InlineKeyboardButton("В главное меню", callback_data="go_to_main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    image_path = "images/video.png"

    context.user_data["history"].append("videos_section")

    try:
        with open(image_path, "rb") as photo:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo,
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
    except FileNotFoundError:
        logger.error(f"Image file {image_path} not found.")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Error sending photo: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )


async def videos_bazumi(update: Update, context: CallbackContext) -> None:
    context.user_data["video_type"] = "bazumi"
    context.user_data["section"] = "videos"
    context.user_data["history"].append("videos_bazumi")

    user_id = update.effective_user.id
    if is_user_verified(user_id):
        text = "<b>Спасибо!</b> Отправляем вам ссылки на плейлист с нашими <u>инструкциями</u>. Выберите удобную для вас площадку."
        keyboard = [
            [InlineKeyboardButton("Rutube", url="https://rutube.ru/playlist")],
            [InlineKeyboardButton("Youtube", url="https://youtube.com/playlist")],
            [InlineKeyboardButton("Назад", callback_data="go_back")],
            [InlineKeyboardButton("В главное меню", callback_data="go_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        # await show_main_menu(update, context, is_end_of_flow=True)
    else:
        text = "Чтобы получить доступ к инструкциям – подтвердите, что вы <b>не бот</b>. Мы <u>не передаем</u> ваши данные третьим лицам."
        keyboard = [
            [InlineKeyboardButton("Я не бот🤖", callback_data="confirm_not_bot_videos")],
            [InlineKeyboardButton("Назад", callback_data="go_back")],
            [InlineKeyboardButton("В главное меню", callback_data="go_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )

    await update.callback_query.answer()


async def videos_other(update: Update, context: CallbackContext) -> None:
    context.user_data["video_type"] = "other"
    context.user_data["section"] = "videos"
    context.user_data["history"].append("videos_other")

    user_id = update.effective_user.id
    if is_user_verified(user_id):
        text = "<b>Спасибо!</b> К сожалению, у нас нет инструкций к другим игрушкам в открытом доступе – но у нас есть <u>Служба заботы</u>, где вам всегда помогут."
        keyboard = [
            [InlineKeyboardButton("Написать Алексею", url="https://t.me/AlexeyBazumi")],
            [InlineKeyboardButton("Назад", callback_data="go_back")],
            [InlineKeyboardButton("В главное меню", callback_data="go_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        # await show_main_menu(update, context, is_end_of_flow=True)
    else:
        text = "Чтобы получить доступ к инструкциям – подтвердите, что вы <b>не бот</b>. Мы <u>не передаем</u> ваши данные третьим лицам."
        keyboard = [
            [InlineKeyboardButton("Я не бот🤖", callback_data="confirm_not_bot_videos")],
            [InlineKeyboardButton("Назад", callback_data="go_back")],
            [InlineKeyboardButton("В главное меню", callback_data="go_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )

    await update.callback_query.answer()


async def confirm_not_bot_videos(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    
    if is_user_verified(user_id):
        context.user_data['section'] = 'videos'
        video_type = context.user_data.get('video_type')
        
        if video_type == 'bazumi':
            text = 'Спасибо! Отправляем вам ссылки на плейлист с нашими инструкциями. Выберите удобную для вас площадку.'
            keyboard = [
                [InlineKeyboardButton('Rutube', url='https://rutube.ru/playlist')],
                [InlineKeyboardButton('Youtube', url='https://youtube.com/playlist')],
                [InlineKeyboardButton('Назад', callback_data='go_back')],
                [InlineKeyboardButton('В главное меню', callback_data='go_to_main_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)
        elif video_type == 'other':
            text = 'Спасибо! К сожалению, у нас нет инструкций к другим игрушкам в открытом доступе – но у нас есть Служба заботы, где вам всегда помогут.'
            keyboard = [[InlineKeyboardButton('Написать Алексею', url='https://t.me/AlexeyBazumi')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)
        
        # await show_main_menu(update, context)
    else:
        context.user_data['section'] = 'videos'
        await request_contact(update, context)
        # Здесь можно добавить обработку контакта через ConversationHandler, если требуется


# async def handle_contact(update: Update, context: CallbackContext) -> None:
#     section = context.user_data.get("section")
#     if update.message.contact:
#         user_id = update.effective_user.id
#         phone_number = update.message.contact.phone_number
#         mark_user_verified(user_id, phone_number)

#         if section == "support":
#             text = "Это <b>Алексей</b> – ваш личный менеджер <u>Службы заботы</u>. Напишите и мы поможем с решением любого вопроса."
#             keyboard = [
#                 [
#                     InlineKeyboardButton(
#                         "Написать Алексею", url="https://t.me/AlexeyBazumi"
#                     )
#                 ],
#                 [InlineKeyboardButton("Назад", callback_data="go_back")],
#                 [
#                     InlineKeyboardButton(
#                         "В главное меню", callback_data="go_to_main_menu"
#                     )
#                 ],
#             ]
#             reply_markup = InlineKeyboardMarkup(keyboard)
#             await context.bot.send_message(
#                 chat_id=update.effective_chat.id,
#                 text=text,
#                 reply_markup=reply_markup,
#                 parse_mode="HTML",
#             )
#         elif section == "videos":
#             video_type = context.user_data.get("video_type")
#             if video_type == "bazumi":
#                 text = "<b>Спасибо!</b> Отправляем вам ссылки на плейлист с нашими <u>инструкциями</u>. Выберите удобную для вас площадку."
#                 keyboard = [
#                     [InlineKeyboardButton("Rutube", url="https://rutube.ru/playlist")],
#                     [
#                         InlineKeyboardButton(
#                             "Youtube", url="https://youtube.com/playlist"
#                         )
#                     ],
#                     [InlineKeyboardButton("Назад", callback_data="go_back")],
#                     [
#                         InlineKeyboardButton(
#                             "В главное меню", callback_data="go_to_main_menu"
#                         )
#                     ],
#                 ]
#                 reply_markup = InlineKeyboardMarkup(keyboard)
#                 await context.bot.send_message(
#                     chat_id=update.effective_chat.id,
#                     text=text,
#                     reply_markup=reply_markup,
#                     parse_mode="HTML",
#                 )
#             elif video_type == "other":
#                 text = "<b>Спасибо!</b> К сожалению, у нас нет инструкций к другим игрушкам в открытом доступе – но у нас есть <u>Служба заботы</u>, где вам всегда помогут."
#                 keyboard = [
#                     [
#                         InlineKeyboardButton(
#                             "Написать Алексею", url="https://t.me/AlexeyBazumi"
#                         )
#                     ],
#                     [InlineKeyboardButton("Назад", callback_data="go_back")],
#                     [
#                         InlineKeyboardButton(
#                             "В главное меню", callback_data="go_to_main_menu"
#                         )
#                     ],
#                 ]
#                 reply_markup = InlineKeyboardMarkup(keyboard)
#                 await context.bot.send_message(
#                     chat_id=update.effective_chat.id,
#                     text=text,
#                     reply_markup=reply_markup,
#                     parse_mode="HTML",
#                 )
#         # Для 'gifts' ничего не делаем, так как это обрабатывает receive_contact
#         await show_main_menu(update, context, is_end_of_flow=True)
#     else:
#         await context.bot.send_message(
#             chat_id=update.effective_chat.id,
#             text="Пожалуйста, <b>отправьте ваш контакт</b>.",
#             parse_mode="HTML",
#         )


async def handle_photo_for_conversation(update, context):
    """Обработчик фотографий для всех состояний разговора"""
    user_id = update.effective_user.id
    message_id = update.message.message_id
    logger.info(f"Received photo from user {user_id}, message_id: {message_id}")

    # Проверяем, не обрабатывается ли уже это фото
    if context.user_data.get("photo_processed_id") == message_id:
        logger.info(f"Photo {message_id} is already being processed, skipping")
        return

    # Проверяем состояние в user_data
    state = context.user_data.get("conversation_state")
    logger.info(f"Current state for user {user_id}: {state}")

    # Вместо проверки ConversationHandler.conversations, просто используем состояние из user_data
    if state == CREATE_CONTEST_PHOTO:
        # Проверяем, не обрабатывается ли уже это сообщение в ConversationHandler
        if not context.user_data.get("photo_being_processed"):
            # Устанавливаем флаг, что фото обрабатывается
            context.user_data["photo_being_processed"] = True
            context.user_data["photo_processed_id"] = message_id
            logger.info(f"Redirecting to create_contest_photo for user {user_id}")
            try:
                return await create_contest_photo(update, context)
            finally:
                # Сбрасываем флаг после обработки
                context.user_data["photo_being_processed"] = False
        else:
            logger.info(f"Photo is already being processed for user {user_id}")
    elif state == EDIT_CONTEST_PHOTO:
        if not context.user_data.get("photo_being_processed"):
            context.user_data["photo_being_processed"] = True
            context.user_data["photo_processed_id"] = message_id
            logger.info(f"Redirecting to edit_contest_photo for user {user_id}")
            try:
                return await edit_contest_photo(update, context)
            finally:
                context.user_data["photo_being_processed"] = False
        else:
            logger.info(f"Photo is already being processed for user {user_id}")
    elif state == CREATE_POST_PHOTO:
        if not context.user_data.get("photo_being_processed"):
            context.user_data["photo_being_processed"] = True
            context.user_data["photo_processed_id"] = message_id
            logger.info(f"Redirecting to create_post_photo for user {user_id}")
            try:
                return await create_post_photo(update, context)
            finally:
                context.user_data["photo_being_processed"] = False
        else:
            logger.info(f"Photo is already being processed for user {user_id}")
    else:
        logger.info(f"No active photo-expecting state for user {user_id}")
        # Если нет активного состояния, просто игнорируем фото
        return


# Добавьте эту функцию перед main()
async def check_state(update, context):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Получаем состояние из всех ConversationHandler
    states = []
    for group, handlers in application.handlers.items():
        for h in handlers:
            if isinstance(h, ConversationHandler):
                state = h.conversations.get((chat_id, user_id))
                if state is not None:
                    states.append(f"{h.name}: {state}")

    if states:
        await update.message.reply_text(f"Текущие состояния:\n{', '.join(states)}")
    else:
        await update.message.reply_text("Нет активных состояний разговора.")


# Добавьте эту функцию перед main()
async def debug_state(update, context):
    """Отладочная команда для проверки текущего состояния пользователя"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Проверяем состояние в user_data
    user_state = context.user_data.get("conversation_state", "No state in user_data")

    # Проверяем состояние в ConversationHandler
    conv_states = []
    if context.application:
        for group, handlers in context.application.handlers.items():
            for handler in handlers:
                if isinstance(handler, ConversationHandler):
                    state = handler.check_update(update)
                    if state is not None:
                        conv_states.append(f"{handler.name}: {state}")
    if not conv_states:
        conv_states = ["No active conversation states"]

    await update.message.reply_text(
        f"Debug info:\n"
        f"User ID: {user_id}\n"
        f"Chat ID: {chat_id}\n"
        f"User data state: {user_state}\n"
        f"Conversation states: {', '.join(conv_states)}"
    )

async def error_handler(update, context):
    """Логирует ошибки, вызванные обновлениями."""
    logger.error(f"Update {update} caused error {context.error}")

    # Отправляем сообщение пользователю
    if update and update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте снова.",
        )


async def show_contest_menu(update, context):
    """Показывает меню управления конкурсом"""
    keyboard = [
        [InlineKeyboardButton("Создать новый конкурс", callback_data="create_contest")],
        [
            InlineKeyboardButton(
                "Редактировать текущий конкурс", callback_data="edit_contest"
            )
        ],
        [
            InlineKeyboardButton(
                "Удалить текущий конкурс", callback_data="delete_contest"
            )
        ],
        [
            InlineKeyboardButton(
                "Уведомление о текущем конкурсе", callback_data="notify_contest"
            )
        ],
        [
            InlineKeyboardButton(
                "Выгрузить участников", callback_data="export_participants"
            )
        ],
        [InlineKeyboardButton("Назад", callback_data="back_to_admin_panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Всегда отправляем новое сообщение
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Управление конкурсом:",
        reply_markup=reply_markup,
    )


async def go_back(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    if "history" in context.user_data and len(context.user_data["history"]) > 1:
        # Удаляем текущий шаг из истории
        context.user_data["history"].pop()
        # Берем предыдущий шаг
        previous_step = context.user_data["history"][-1]

        # Возвращаемся к предыдущему шагу
        if previous_step == "main_menu":
            await show_main_menu(update, context, is_end_of_flow=False)
        elif previous_step == "support_section":
            await support_section(update, context)
        elif previous_step == "gifts_section":
            await gifts_section(update, context)
        elif previous_step == "videos_section":
            await videos_section(update, context)
        elif previous_step == "contact_manager":
            await contact_manager(update, context)
        elif previous_step == "participate_gifts":
            await participate_gifts(update, context)
        elif previous_step == "videos_bazumi":
            await videos_bazumi(update, context)
        elif previous_step == "videos_other":
            await videos_other(update, context)
        else:
            await query.edit_message_text("Не удалось вернуться назад.")
    else:
        await show_main_menu(update, context, is_end_of_flow=False)


async def go_to_main_menu(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    # Очищаем историю и возвращаемся в главное меню
    context.user_data["history"] = ["main_menu"]
    await show_main_menu(update, context, is_end_of_flow=False)

def main():
    global application, participate_handler
    init_db()
    application = Application.builder().token("7972510069:AAGEWyXr5BQlydxbkwsziyfGxxtscsMTPfs").build()
    
    application.add_error_handler(error_handler)
    
    # Инициализируем participate_handler
    participate_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(participate, pattern="^participate$"),
            CallbackQueryHandler(confirm_participate, pattern="^confirm_participate$")
        ],
        states={
            PARTICIPATE_CONFIRM: [MessageHandler(filters.CONTACT, receive_contact)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        name="participate_conversation"
    )
    application.add_handler(participate_handler, group=-1)

    # Остальные ConversationHandler
    create_contest_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_create_contest, pattern="^create_contest$")],
        states={
            CREATE_CONTEST_PHOTO: [
                MessageHandler(filters.PHOTO, create_contest_photo),
                MessageHandler(filters.Document.IMAGE, create_contest_photo)
            ],
            CREATE_CONTEST_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_contest_title)],
            CREATE_CONTEST_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_contest_date)],
            CREATE_CONTEST_PREVIEW: [CallbackQueryHandler(create_contest_preview, pattern="^(publish_contest|edit_contest_preview)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        name="create_contest_conversation"
    )
    application.add_handler(create_contest_handler, group=0)

    edit_contest_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_edit_contest, pattern="^edit_contest$")],
        states={
            EDIT_CONTEST_PHOTO: [
                MessageHandler(filters.PHOTO, edit_contest_photo),
                MessageHandler(filters.Document.IMAGE, edit_contest_photo)
            ],
            EDIT_CONTEST_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_contest_title)],
            EDIT_CONTEST_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_contest_date)],
            EDIT_CONTEST_PREVIEW: [CallbackQueryHandler(edit_contest_preview, pattern="^finish_edit_contest$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        name="edit_contest_conversation"
    )
    application.add_handler(edit_contest_handler, group=0)

    create_post_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_create_post, pattern="^post$")],
        states={
            CREATE_POST_PHOTO: [
                MessageHandler(filters.PHOTO, create_post_photo),
                MessageHandler(filters.Document.IMAGE, create_post_photo)
            ],
            CREATE_POST_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_post_title)],
            CREATE_POST_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_post_text)],
            CREATE_POST_PREVIEW: [CallbackQueryHandler(create_post_preview, pattern="^(publish_post|edit_post_preview)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        name="create_post_conversation"
    )
    application.add_handler(create_post_handler, group=0)

    # Остальные обработчики
    application.add_handler(CommandHandler("admin", admin_panel), group=1)
    application.add_handler(CommandHandler("add_admin", add_admin_command), group=1)
    application.add_handler(CommandHandler("remove_admin", remove_admin_command), group=1)
    application.add_handler(CommandHandler("verify_user", verify_user_command), group=1)
    
    application.add_handler(CallbackQueryHandler(contest_menu, pattern="^contest$"), group=1)
    application.add_handler(CallbackQueryHandler(delete_contest, pattern="^delete_contest$"), group=1)
    application.add_handler(CallbackQueryHandler(notify_contest, pattern="^notify_contest$"), group=1)
    application.add_handler(CallbackQueryHandler(export_participants, pattern="^export_participants$"), group=1)
    application.add_handler(CallbackQueryHandler(confirm_delete, pattern="^confirm_delete$"), group=1)
    application.add_handler(CallbackQueryHandler(cancel_delete, pattern="^cancel_delete$"), group=1)
    application.add_handler(CallbackQueryHandler(check_subscription, pattern="^check_subscription$"), group=1)
    application.add_handler(CallbackQueryHandler(check_subscription_gifts, pattern="^check_subscription_gifts$"), group=1)
    
    application.add_handler(CommandHandler("start", start), group=1)
    application.add_handler(CallbackQueryHandler(support_section, pattern='^support$'), group=1)
    application.add_handler(CallbackQueryHandler(gifts_section, pattern='^gifts$'), group=1)
    application.add_handler(CallbackQueryHandler(videos_section, pattern='^videos$'), group=1)
    application.add_handler(CallbackQueryHandler(contact_manager, pattern='^contact_manager$'), group=1)
    application.add_handler(CallbackQueryHandler(confirm_not_bot_support, pattern='^confirm_not_bot_support$'), group=1)
    application.add_handler(CallbackQueryHandler(participate_gifts, pattern='^participate_gifts$'), group=1)
    application.add_handler(CallbackQueryHandler(confirm_not_bot_gifts, pattern='^confirm_not_bot_gifts$'), group=1)
    application.add_handler(CallbackQueryHandler(videos_bazumi, pattern='^videos_bazumi$'), group=1)
    application.add_handler(CallbackQueryHandler(videos_other, pattern='^videos_other$'), group=1)
    application.add_handler(CallbackQueryHandler(confirm_not_bot_videos, pattern='^confirm_not_bot_videos$'), group=1)
    application.add_handler(CallbackQueryHandler(go_back, pattern='^go_back$'), group=1)
    application.add_handler(CallbackQueryHandler(go_to_main_menu, pattern='^go_to_main_menu$'), group=1)
    application.add_handler(CallbackQueryHandler(back_to_admin_panel, pattern="^back_to_admin_panel$"), group=1)
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_for_conversation), group=1)
    
    # Добавляем обработчик контактов вне ConversationHandler для надежности
    application.add_handler(MessageHandler(filters.CONTACT, receive_contact), group=2)

    application.add_handler(CommandHandler("state", check_state), group=0)
    application.add_handler(CommandHandler("debug", debug_state), group=0)
    logger.info("Application handlers initialized")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()