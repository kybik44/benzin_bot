import asyncio
import sqlite3
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext, ConversationHandler
from telegram.error import NetworkError, Forbidden

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bazumi_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS contests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        photo_id TEXT,
        title TEXT,
        end_date TEXT,
        status TEXT DEFAULT 'active'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS participants (
        contest_id INTEGER,
        user_id INTEGER,
        username TEXT,
        phone_number TEXT,
        PRIMARY KEY (contest_id, user_id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        photo_id TEXT,
        title TEXT,
        text TEXT
    )''')
    c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (6357518457,))
    conn.commit()
    conn.close()

# Проверка администратора
def is_admin(user_id):
    conn = sqlite3.connect('bazumi_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    result = c.fetchone() is not None
    conn.close()
    return result

# Вспомогательные функции
def validate_date(date_str):
    try:
        datetime.strptime(date_str, '%d.%m.%Y')
        return True
    except ValueError:
        return False

def format_contest_preview(title, date):
    return f"""Супер, на этой неделе мы разыгрываем {title}
Условия очень простые:
нажать "принять участие"
быть подписанным на канал @BAZUMI_discountt
дождаться результатов, они будут {date} в нашем канале"""

def format_contest_notification(title, date):
    return f"""Привет! На этой неделе мы разыгрываем {title}
Условия очень простые:
нажать "принять участие"
быть подписанным на канал @BAZUMI_discountt
дождаться результатов, они будут {date} в нашем канале
Присоединяйся!"""

def format_post_preview(title, text):
    return f"{title}\n{text}"

# Работа с базой данных
def add_admin(user_id):
    conn = sqlite3.connect('bazumi_bot.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def remove_admin(user_id):
    conn = sqlite3.connect('bazumi_bot.db')
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def create_contest(photo_id, title, end_date):
    conn = sqlite3.connect('bazumi_bot.db')
    c = conn.cursor()
    c.execute("INSERT INTO contests (photo_id, title, end_date) VALUES (?, ?, ?)", (photo_id, title, end_date))
    contest_id = c.lastrowid
    conn.commit()
    conn.close()
    return contest_id

def get_active_contest():
    conn = sqlite3.connect('bazumi_bot.db')
    c = conn.cursor()
    c.execute("SELECT * FROM contests WHERE status = 'active' LIMIT 1")
    contest = c.fetchone()
    conn.close()
    return contest

def update_contest(contest_id, photo_id, title, end_date):
    conn = sqlite3.connect('bazumi_bot.db')
    c = conn.cursor()
    c.execute("UPDATE contests SET photo_id = ?, title = ?, end_date = ? WHERE id = ?", 
              (photo_id, title, end_date, contest_id))
    conn.commit()
    conn.close()

def delete_contest_db(contest_id):
    """Удаляет конкурс из базы данных"""
    conn = sqlite3.connect('bazumi_bot.db')
    c = conn.cursor()
    c.execute("UPDATE contests SET status = 'inactive' WHERE id = ?", (contest_id,))
    conn.commit()
    conn.close()

def add_participant(contest_id, user_id, username, phone_number):
    """Добавляет участника конкурса в базу данных"""
    conn = sqlite3.connect('bazumi_bot.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO participants (contest_id, user_id, username, phone_number) VALUES (?, ?, ?, ?)",
              (contest_id, user_id, username, phone_number))
    conn.commit()
    conn.close()

def get_participants(contest_id):
    conn = sqlite3.connect('bazumi_bot.db')
    c = conn.cursor()
    c.execute("SELECT username, phone_number FROM participants WHERE contest_id = ?", (contest_id,))
    participants = c.fetchall()
    conn.close()
    return participants

def create_post(photo_id, title, text):
    """Создает новый пост в базе данных"""
    conn = sqlite3.connect('bazumi_bot.db')
    c = conn.cursor()
    c.execute("INSERT INTO posts (photo_id, title, text) VALUES (?, ?, ?)", 
              (photo_id, title, text))
    post_id = c.lastrowid
    conn.commit()
    conn.close()
    return post_id

# Состояния для ConversationHandler
CREATE_CONTEST_PHOTO, CREATE_CONTEST_TITLE, CREATE_CONTEST_DATE, CREATE_CONTEST_PREVIEW = range(4)
EDIT_CONTEST_PHOTO, EDIT_CONTEST_TITLE, EDIT_CONTEST_DATE, EDIT_CONTEST_PREVIEW = range(4, 8)
CREATE_POST_PHOTO, CREATE_POST_TITLE, CREATE_POST_TEXT, CREATE_POST_PREVIEW = range(8, 12)
PARTICIPATE_CONFIRM = 12

# Главная панель администратора
async def admin_panel(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("У вас нет доступа к админ-панели.")
        return
    keyboard = [
        [InlineKeyboardButton("Конкурс", callback_data="contest")],
        [InlineKeyboardButton("Пост", callback_data="post")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await update.message.reply_text("Административная панель:", reply_markup=reply_markup)
    except NetworkError:
        await update.message.reply_text("Ошибка сети. Проверьте подключение к интернету и попробуйте снова.")
    except Forbidden:
        await update.message.reply_text("Бот был заблокирован вами. Разблокируйте бота, чтобы продолжить.")

# Меню конкурса
async def contest_menu(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Создать новый конкурс", callback_data="create_contest")],
        [InlineKeyboardButton("Редактировать текущий конкурс", callback_data="edit_contest")],
        [InlineKeyboardButton("Удалить текущий конкурс", callback_data="delete_contest")],
        [InlineKeyboardButton("Уведомление о текущем конкурсе", callback_data="notify_contest")],
        [InlineKeyboardButton("Выгрузить участников", callback_data="export_participants")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Управление конкурсом:", reply_markup=reply_markup)

# Создание конкурса
async def start_create_contest(update, context):
    # Важно: сначала сохраняем состояние, потом отвечаем
    logger.info(f"Starting create contest for user {update.effective_user.id}")
    
    # Явно устанавливаем состояние в контексте пользователя
    context.user_data['conversation_state'] = CREATE_CONTEST_PHOTO
    
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Загрузите фото для конкурса.")
    
    # Логируем переход в состояние
    logger.info(f"Set state to CREATE_CONTEST_PHOTO for user {update.effective_user.id}")
    
    return CREATE_CONTEST_PHOTO

async def create_contest_photo(update, context):
    # Проверяем, не обрабатывается ли уже это фото
    if context.user_data.get('photo_being_processed') and context.user_data.get('photo_processed_id') == update.message.message_id:
        logger.info(f"Skipping duplicate processing of photo {update.message.message_id}")
        return CREATE_CONTEST_PHOTO
    
    logger.info(f"User {update.effective_user.id} sent a message in create_contest_photo.")
    logger.info(f"Message content: {update.message}")
    
    # Отмечаем, что это фото обрабатывается
    context.user_data['photo_being_processed'] = True
    context.user_data['photo_processed_id'] = update.message.message_id
    
    # Проверяем все возможные типы фото
    if update.message.photo:
        # Telegram отправляет несколько размеров, берем последний (самый большой)
        context.user_data["contest_photo"] = update.message.photo[-1].file_id
        logger.info(f"Photo received with file_id: {context.user_data['contest_photo']}")
        
        try:
            # Обновляем состояние в user_data
            context.user_data['conversation_state'] = CREATE_CONTEST_TITLE
            
            await update.message.reply_text("Введите название разыгрываемого предмета.")
            logger.info(f"Photo accepted, moving to title.")
            
            # Сбрасываем флаг обработки
            context.user_data['photo_being_processed'] = False
            return CREATE_CONTEST_TITLE
        except Exception as e:
            logger.error(f"Error after photo upload: {e}")
            # Сбрасываем флаг обработки
            context.user_data['photo_being_processed'] = False
            return CREATE_CONTEST_PHOTO
            
    elif update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith('image/'):
        context.user_data["contest_photo"] = update.message.document.file_id
        logger.info(f"Document image received with file_id: {context.user_data['contest_photo']}")
        
        try:
            await update.message.reply_text("Введите название разыгрываемого предмета.")
            logger.info(f"Document photo accepted, moving to title.")
            return CREATE_CONTEST_TITLE
        except Exception as e:
            logger.error(f"Error after document photo upload: {e}")
            return CREATE_CONTEST_PHOTO
            
    else:
        logger.warning(f"No photo detected in message: {update.message}")
        await update.message.reply_text("Пожалуйста, загрузите фото (не документ или видео).")
        # Сбрасываем флаг обработки
        context.user_data['photo_being_processed'] = False
        return CREATE_CONTEST_PHOTO

async def create_contest_title(update, context):
    context.user_data["contest_title"] = update.message.text
    try:
        await update.message.reply_text("Введите дату окончания (ДД.ММ.ГГГГ).")
    except NetworkError:
        await update.message.reply_text("Ошибка сети. Проверьте подключение и попробуйте снова.")
        return CREATE_CONTEST_TITLE
    except Forbidden:
        await update.message.reply_text("Бот заблокирован. Разблокируйте его в Telegram.")
        return CREATE_CONTEST_TITLE
    return CREATE_CONTEST_DATE

async def create_contest_date(update, context):
    date_str = update.message.text
    if not validate_date(date_str):
        try:
            await update.message.reply_text("Некорректный формат даты. Введите в формате ДД.ММ.ГГГГ.")
        except NetworkError:
            await update.message.reply_text("Ошибка сети. Проверьте подключение и попробуйте снова.")
        except Forbidden:
            await update.message.reply_text("Бот заблокирован. Разблокируйте его в Telegram.")
        return CREATE_CONTEST_DATE
    context.user_data["contest_date"] = date_str
    preview = format_contest_preview(context.user_data["contest_title"], date_str)
    keyboard = [
        [InlineKeyboardButton("Опубликовать конкурс", callback_data="publish_contest")],
        [InlineKeyboardButton("Редактировать конкурс", callback_data="edit_contest_preview")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await update.message.reply_photo(
            photo=context.user_data["contest_photo"],
            caption=preview,
            reply_markup=reply_markup
        )
    except NetworkError:
        await update.message.reply_text("Ошибка сети. Проверьте подключение и попробуйте снова.")
        return CREATE_CONTEST_DATE
    except Forbidden:
        await update.message.reply_text("Бот заблокирован. Разблокируйте его в Telegram.")
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
                context.user_data["contest_date"]
            )
            preview = format_contest_preview(context.user_data["contest_title"], context.user_data["contest_date"])
            
            # Добавляем кнопку "Принять участие в конкурсе"
            keyboard = [
                [InlineKeyboardButton("Принять участие в конкурсе", callback_data="participate")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Отправляем в канал
            try:
                # Используем правильный ID канала
                await context.bot.send_photo(
                    chat_id="@testkybik",  # Канал из ТЗ
                    photo=context.user_data["contest_photo"],
                    caption=preview,
                    reply_markup=reply_markup  # Добавляем кнопку
                )
                # Отправляем новое сообщение вместо редактирования
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Конкурс опубликован!"
                )
                
                # Возвращаем в меню конкурса после короткой паузы
                await asyncio.sleep(1)
                # Используем send_message вместо edit_message_text
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Управление конкурсом:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Создать новый конкурс", callback_data="create_contest")],
                        [InlineKeyboardButton("Редактировать текущий конкурс", callback_data="edit_contest")],
                        [InlineKeyboardButton("Удалить текущий конкурс", callback_data="delete_contest")],
                        [InlineKeyboardButton("Уведомление о текущем конкурсе", callback_data="notify_contest")],
                        [InlineKeyboardButton("Выгрузить участников", callback_data="export_participants")]
                    ])
                )
            except Exception as e:
                logger.error(f"Error publishing contest: {e}")
                # Отправляем новое сообщение об ошибке
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"Ошибка при публикации конкурса: {str(e)}"
                )
                
                # Возвращаем в меню конкурса после короткой паузы даже при ошибке
                await asyncio.sleep(1)
                # Используем send_message вместо edit_message_text
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Управление конкурсом:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Создать новый конкурс", callback_data="create_contest")],
                        [InlineKeyboardButton("Редактировать текущий конкурс", callback_data="edit_contest")],
                        [InlineKeyboardButton("Удалить текущий конкурс", callback_data="delete_contest")],
                        [InlineKeyboardButton("Уведомление о текущем конкурсе", callback_data="notify_contest")],
                        [InlineKeyboardButton("Выгрузить участников", callback_data="export_participants")]
                    ])
                )
        except Exception as e:
            logger.error(f"Error creating contest: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Ошибка при создании конкурса: {str(e)}"
            )
            
            # Возвращаем в меню конкурса после короткой паузы даже при ошибке
            await asyncio.sleep(1)
            # Используем send_message вместо edit_message_text
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Управление конкурсом:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Создать новый конкурс", callback_data="create_contest")],
                    [InlineKeyboardButton("Редактировать текущий конкурс", callback_data="edit_contest")],
                    [InlineKeyboardButton("Удалить текущий конкурс", callback_data="delete_contest")],
                    [InlineKeyboardButton("Уведомление о текущем конкурсе", callback_data="notify_contest")],
                    [InlineKeyboardButton("Выгрузить участников", callback_data="export_participants")]
                ])
            )
    elif query.data == "edit_contest_preview":
        # Отправляем новое сообщение вместо редактирования
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Загрузите фото для конкурса."
        )
        # Устанавливаем состояние в user_data
        context.user_data['conversation_state'] = CREATE_CONTEST_PHOTO
        return CREATE_CONTEST_PHOTO
    
    return ConversationHandler.END

# Редактирование конкурса
async def start_edit_contest(update, context):
    contest = get_active_contest()
    if not contest:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Нет активных конкурсов для редактирования.")
        return ConversationHandler.END
    
    # Сохраняем ID конкурса в user_data
    context.user_data["contest_id"] = contest[0]
    
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Загрузите новое фото для конкурса.")
    
    # Устанавливаем состояние в user_data
    context.user_data['conversation_state'] = EDIT_CONTEST_PHOTO
    
    return EDIT_CONTEST_PHOTO

async def edit_contest_photo(update, context):
    # Проверяем, не обрабатывается ли уже это фото
    if context.user_data.get('photo_being_processed') and context.user_data.get('photo_processed_id') == update.message.message_id:
        logger.info(f"Skipping duplicate processing of photo {update.message.message_id} in edit_contest_photo")
        return EDIT_CONTEST_TITLE
    
    logger.info(f"User {update.effective_user.id} sent a photo in edit_contest_photo.")
    
    # Отмечаем, что это фото обрабатывается
    context.user_data['photo_being_processed'] = True
    context.user_data['photo_processed_id'] = update.message.message_id
    
    try:
        if update.message.photo:
            context.user_data["contest_photo"] = update.message.photo[-1].file_id
            logger.info(f"Photo received with file_id: {context.user_data['contest_photo']}")
            
            # Обновляем состояние в user_data
            context.user_data['conversation_state'] = EDIT_CONTEST_TITLE
            
            await update.message.reply_text("Введите новое название разыгрываемого предмета.")
            logger.info(f"Photo accepted for edit, moving to title.")
            
            # Сбрасываем флаг обработки
            context.user_data['photo_being_processed'] = False
            return EDIT_CONTEST_TITLE
        else:
            logger.warning(f"No photo detected in message: {update.message}")
            await update.message.reply_text("Пожалуйста, загрузите фото (не документ или видео).")
            
            # Сбрасываем флаг обработки
            context.user_data['photo_being_processed'] = False
            return EDIT_CONTEST_PHOTO
    except Exception as e:
        logger.error(f"Error in edit_contest_photo: {e}")
        await update.message.reply_text("Произошла ошибка при обработке фото. Пожалуйста, попробуйте снова.")
        
        # Сбрасываем флаг обработки
        context.user_data['photo_being_processed'] = False
        return EDIT_CONTEST_PHOTO

async def edit_contest_title(update, context):
    # Проверяем, не обрабатывается ли уже этот текст
    if context.user_data.get('title_being_processed') and context.user_data.get('title_processed_id') == update.message.message_id:
        logger.info(f"Skipping duplicate processing of title {update.message.message_id} in edit_contest_title")
        return EDIT_CONTEST_DATE
    
    # Отмечаем, что этот текст обрабатывается
    context.user_data['title_being_processed'] = True
    context.user_data['title_processed_id'] = update.message.message_id
    
    try:
        context.user_data["contest_title"] = update.message.text
        logger.info(f"Title received: {context.user_data['contest_title']}")
        
        # Обновляем состояние в user_data
        context.user_data['conversation_state'] = EDIT_CONTEST_DATE
        
        await update.message.reply_text("Введите новую дату окончания конкурса в формате ДД.ММ.ГГГГ")
        
        # Сбрасываем флаг обработки
        context.user_data['title_being_processed'] = False
        return EDIT_CONTEST_DATE
    except Exception as e:
        logger.error(f"Error in edit_contest_title: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, введите название снова.")
        
        # Сбрасываем флаг обработки
        context.user_data['title_being_processed'] = False
        return EDIT_CONTEST_TITLE

async def edit_contest_date(update, context):
    date_str = update.message.text
    if not validate_date(date_str):
        await update.message.reply_text("Некорректный формат даты. Введите в формате ДД.ММ.ГГГГ.")
        return EDIT_CONTEST_DATE
    context.user_data["contest_date"] = date_str
    preview = format_contest_preview(context.user_data["contest_title"], date_str)
    keyboard = [[InlineKeyboardButton("Завершить редактирование", callback_data="finish_edit_contest")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_photo(
        photo=context.user_data["contest_photo"],
        caption=preview,
        reply_markup=reply_markup
    )
    return EDIT_CONTEST_PREVIEW

async def edit_contest_preview(update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == "finish_edit_contest":
        try:
            # Получаем активный конкурс, если contest_id не сохранен в user_data
            if "contest_id" not in context.user_data:
                contest = get_active_contest()
                if contest:
                    context.user_data["contest_id"] = contest[0]
                else:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="Ошибка: не найден активный конкурс для редактирования."
                    )
                    
                    # Возвращаем в меню конкурса после короткой паузы
                    await asyncio.sleep(1)
                    # Используем send_message вместо edit_message_text
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="Управление конкурсом:",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("Создать новый конкурс", callback_data="create_contest")],
                            [InlineKeyboardButton("Редактировать текущий конкурс", callback_data="edit_contest")],
                            [InlineKeyboardButton("Удалить текущий конкурс", callback_data="delete_contest")],
                            [InlineKeyboardButton("Уведомление о текущем конкурсе", callback_data="notify_contest")],
                            [InlineKeyboardButton("Выгрузить участников", callback_data="export_participants")]
                        ])
                    )
                    return ConversationHandler.END
            
            # Теперь вызываем update_contest с правильными параметрами
            update_contest(
                context.user_data["contest_id"],  # Передаем ID конкурса
                context.user_data["contest_photo"],
                context.user_data["contest_title"],
                context.user_data["contest_date"]
            )
            
            # Формируем превью конкурса для отправки в канал
            preview = format_contest_preview(context.user_data["contest_title"], context.user_data["contest_date"])
            
            # Добавляем кнопку "Принять участие в конкурсе"
            keyboard = [
                [InlineKeyboardButton("Принять участие в конкурсе", callback_data="participate")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Отправляем обновленный конкурс в канал
            try:
                await context.bot.send_photo(
                    chat_id="@testkybik",  # Канал из ТЗ
                    photo=context.user_data["contest_photo"],
                    caption=preview,
                    reply_markup=reply_markup
                )
                
                # Отправляем сообщение об успешном обновлении
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Конкурс успешно обновлен и опубликован в канале!"
                )
            except Exception as e:
                logger.error(f"Error publishing updated contest: {e}")
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"Конкурс обновлен в базе данных, но произошла ошибка при публикации в канале: {str(e)}"
                )
            
            # Возвращаем в меню конкурса после короткой паузы
            await asyncio.sleep(1)
            # Используем send_message вместо edit_message_text
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Управление конкурсом:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Создать новый конкурс", callback_data="create_contest")],
                    [InlineKeyboardButton("Редактировать текущий конкурс", callback_data="edit_contest")],
                    [InlineKeyboardButton("Удалить текущий конкурс", callback_data="delete_contest")],
                    [InlineKeyboardButton("Уведомление о текущем конкурсе", callback_data="notify_contest")],
                    [InlineKeyboardButton("Выгрузить участников", callback_data="export_participants")]
                ])
            )
        except Exception as e:
            logger.error(f"Error updating contest: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Ошибка при обновлении конкурса: {str(e)}"
            )
            
            # Возвращаем в меню конкурса после короткой паузы даже при ошибке
            await asyncio.sleep(1)
            # Используем send_message вместо edit_message_text
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Управление конкурсом:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Создать новый конкурс", callback_data="create_contest")],
                    [InlineKeyboardButton("Редактировать текущий конкурс", callback_data="edit_contest")],
                    [InlineKeyboardButton("Удалить текущий конкурс", callback_data="delete_contest")],
                    [InlineKeyboardButton("Уведомление о текущем конкурсе", callback_data="notify_contest")],
                    [InlineKeyboardButton("Выгрузить участников", callback_data="export_participants")]
                ])
            )
    
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
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Да", callback_data="confirm_delete")],
            [InlineKeyboardButton("Нет", callback_data="cancel_delete")]
        ])
    )

async def confirm_delete(update, context):
    query = update.callback_query
    await query.answer()
    
    # Получаем ID конкурса из user_data
    contest_id = context.user_data.get("contest_id")
    
    if not contest_id:
        await query.edit_message_text("Ошибка: не найден конкурс для удаления.")
        # Возвращаем в меню конкурса
        await show_contest_menu(update, context)
        return
    
    try:
        # Вызываем функцию для удаления конкурса из БД
        delete_contest_db(contest_id)
        await query.edit_message_text("Конкурс успешно удален.")
        
        # Возвращаем в меню конкурса после короткой паузы
        await asyncio.sleep(1)
        await show_contest_menu(update, context)
    except Exception as e:
        logger.error(f"Error deleting contest: {e}")
        await query.edit_message_text(f"Ошибка при удалении конкурса: {str(e)}")
        
        # Возвращаем в меню конкурса после короткой паузы даже при ошибке
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
        [InlineKeyboardButton("Редактировать текущий конкурс", callback_data="edit_contest")],
        [InlineKeyboardButton("Удалить текущий конкурс", callback_data="delete_contest")],
        [InlineKeyboardButton("Уведомление о текущем конкурсе", callback_data="notify_contest")],
        [InlineKeyboardButton("Выгрузить участников", callback_data="export_participants")]
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
        
        # Возвращаем в меню конкурса после короткой паузы
        await asyncio.sleep(1)
        await show_contest_menu(update, context)
        return
    
    notification = format_contest_notification(contest[2], contest[3])
    keyboard = [
        [InlineKeyboardButton("Принять участие в конкурсе", callback_data="participate")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        # Используем правильный ID канала
        await context.bot.send_photo(
            chat_id="@testkybik",  # Канал из ТЗ
            photo=contest[1],
            caption=notification,
            reply_markup=reply_markup
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Уведомление о конкурсе отправлено!"
        )
        
        # Возвращаем в меню конкурса после короткой паузы
        await asyncio.sleep(1)
        await show_contest_menu(update, context)
    except Exception as e:
        logger.error(f"Error sending contest notification: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Ошибка при отправке уведомления: {str(e)}"
        )
        
        # Возвращаем в меню конкурса после короткой паузы даже при ошибке
        await asyncio.sleep(1)
        await show_contest_menu(update, context)

# Участие в конкурсе
async def participate(update, context):
    query = update.callback_query
    await query.answer()
    
    # Проверяем, является ли чат каналом или группой
    is_channel_or_group = update.effective_chat.type in ['channel', 'group', 'supergroup']
    
    if is_channel_or_group:
        # Если нажатие произошло в канале или группе, отправляем личное сообщение пользователю
        try:
            contest = get_active_contest()
            if not contest:
                await context.bot.send_message(
                    chat_id=update.effective_user.id,
                    text="К сожалению, в данный момент нет активных конкурсов."
                )
                return
            
            # Сохраняем ID конкурса в user_data
            context.user_data["contest_id"] = contest[0]
            
            # Отправляем личное сообщение пользователю
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text="Чтобы принять участие – подтвердите, что вы не бот. Мы не передаем ваши данные третьим лицам.",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("Я не бот", request_contact=True)]],
                    one_time_keyboard=True,
                    resize_keyboard=True
                )
            )
            return PARTICIPATE_CONFIRM
        except Exception as e:
            logger.error(f"Error sending private message: {e}")
            # Если не удалось отправить личное сообщение, просим пользователя начать диалог с ботом
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"@{update.effective_user.username}, пожалуйста, начните диалог с ботом, чтобы принять участие в конкурсе: https://t.me/{context.bot.username}"
                )
            except Exception as e2:
                logger.error(f"Error sending channel message: {e2}")
            return
    
    # Проверяем, есть ли в сообщении фото
    elif hasattr(query.message, 'photo') and query.message.photo:
        # Если сообщение содержит фото, отправляем новое сообщение вместо редактирования
        contest = get_active_contest()
        if not contest:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="К сожалению, в данный момент нет активных конкурсов."
            )
            return
        
        # Сохраняем ID конкурса в user_data
        context.user_data["contest_id"] = contest[0]
        
        # Отправляем сообщение с подтверждением
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Чтобы принять участие – подтвердите, что вы не бот. Мы не передаем ваши данные третьим лицам.",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("Я не бот", request_contact=True)]],
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return PARTICIPATE_CONFIRM
    else:
        # Если сообщение не содержит фото, можем редактировать текст
        try:
            contest = get_active_contest()
            if not contest:
                await query.edit_message_text("К сожалению, в данный момент нет активных конкурсов.")
                return
            
            # Сохраняем ID конкурса в user_data
            context.user_data["contest_id"] = contest[0]
            
            await query.edit_message_text(
                "Чтобы принять участие – подтвердите, что вы не бот. Мы не передаем ваши данные третьим лицам.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Я не бот", callback_data="confirm_participate")]
                ])
            )
            return
        except Exception as e:
            logger.error(f"Error in participate: {e}")
            # Если редактирование не удалось, отправляем новое сообщение
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Чтобы принять участие – подтвердите, что вы не бот. Мы не передаем ваши данные третьим лицам.",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("Я не бот", request_contact=True)]],
                    one_time_keyboard=True,
                    resize_keyboard=True
                )
            )
            return PARTICIPATE_CONFIRM

async def confirm_participate(update, context):
    query = update.callback_query
    await query.answer()
    
    try:
        # Отправляем новое сообщение с запросом контакта
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Пожалуйста, поделитесь своим контактом для участия в конкурсе.",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("Поделиться контактом", request_contact=True)]],
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return PARTICIPATE_CONFIRM
    except Exception as e:
        logger.error(f"Error in confirm_participate: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Произошла ошибка. Пожалуйста, попробуйте снова."
        )
        return ConversationHandler.END

async def receive_contact(update, context):
    user = update.effective_user
    contact = update.message.contact
    
    try:
        # Получаем ID конкурса из user_data
        contest_id = context.user_data.get("contest_id")
        if not contest_id:
            # Если ID конкурса не найден, получаем активный конкурс
            contest = get_active_contest()
            if contest:
                contest_id = contest[0]
            else:
                await update.message.reply_text(
                    "Ошибка: не найден активный конкурс.",
                    reply_markup=ReplyKeyboardRemove()
                )
                return ConversationHandler.END
        
        # Сохраняем контакт в базе данных
        add_participant(contest_id, user.id, user.username, contact.phone_number)
        
        await update.message.reply_text(
            "Отлично, вы зарегистрированы как участник. Желаем вам удачи и остаемся на связи! Ваш Bazumi ♥️",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in receive_contact: {e}")
        await update.message.reply_text(
            "Произошла ошибка при регистрации. Пожалуйста, попробуйте снова.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

# Выгрузка участников
async def export_participants(update, context):
    query = update.callback_query
    await query.answer()
    
    contest = get_active_contest()
    if not contest:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Нет активного конкурса для выгрузки участников."
        )
        
        # Возвращаем в меню конкурса после короткой паузы
        await asyncio.sleep(1)
        await show_contest_menu(update, context)
        return
    
    participants = get_participants(contest[0])
    if not participants:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Нет участников для выгрузки."
        )
        
        # Возвращаем в меню конкурса после короткой паузы
        await asyncio.sleep(1)
        await show_contest_menu(update, context)
        return
    
    # Формируем список участников
    participants_text = "Список участников конкурса:\n\n"
    for p in participants:
        username = p[2] if p[2] else f"ID: {p[1]}"
        participants_text += f"{username} - {p[3]}\n"
    
    # Отправляем список участников
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=participants_text
    )
    
    # Возвращаем в меню конкурса после короткой паузы
    await asyncio.sleep(1)
    await show_contest_menu(update, context)

# Создание поста
async def start_create_post(update, context):
    """Начало создания поста"""
    logger.info(f"Starting create post for user {update.effective_user.id}")
    
    # Устанавливаем состояние в user_data
    context.user_data['conversation_state'] = CREATE_POST_PHOTO
    
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Загрузите фото для поста.")
    
    return CREATE_POST_PHOTO

async def create_post_photo(update, context):
    # Проверяем, не обрабатывается ли уже это фото
    if context.user_data.get('photo_being_processed') and context.user_data.get('photo_processed_id') == update.message.message_id:
        logger.info(f"Skipping duplicate processing of photo {update.message.message_id} in create_post_photo")
        return CREATE_POST_TITLE
    
    logger.info(f"User {update.effective_user.id} sent a photo in create_post_photo.")
    
    # Отмечаем, что это фото обрабатывается
    context.user_data['photo_being_processed'] = True
    context.user_data['photo_processed_id'] = update.message.message_id
    
    try:
        if update.message.photo:
            context.user_data["post_photo"] = update.message.photo[-1].file_id
            logger.info(f"Photo received with file_id: {context.user_data['post_photo']}")
            
            # Обновляем состояние в user_data
            context.user_data['conversation_state'] = CREATE_POST_TITLE
            
            await update.message.reply_text("Введите заголовок поста.")
            logger.info(f"Photo accepted for post, moving to title.")
            
            # Сбрасываем флаг обработки
            context.user_data['photo_being_processed'] = False
            return CREATE_POST_TITLE
        else:
            logger.warning(f"No photo detected in message: {update.message}")
            await update.message.reply_text("Пожалуйста, загрузите фото (не документ или видео).")
            
            # Сбрасываем флаг обработки
            context.user_data['photo_being_processed'] = False
            return CREATE_POST_PHOTO
    except Exception as e:
        logger.error(f"Error in create_post_photo: {e}")
        await update.message.reply_text("Произошла ошибка при обработке фото. Пожалуйста, попробуйте снова.")
        
        # Сбрасываем флаг обработки
        context.user_data['photo_being_processed'] = False
        return CREATE_POST_PHOTO

async def create_post_title(update, context):
    # Проверяем, не обрабатывается ли уже этот текст
    if context.user_data.get('title_being_processed') and context.user_data.get('title_processed_id') == update.message.message_id:
        logger.info(f"Skipping duplicate processing of title {update.message.message_id} in create_post_title")
        return CREATE_POST_TEXT
    
    # Отмечаем, что этот текст обрабатывается
    context.user_data['title_being_processed'] = True
    context.user_data['title_processed_id'] = update.message.message_id
    
    try:
        context.user_data["post_title"] = update.message.text
        logger.info(f"Post title received: {context.user_data['post_title']}")
        
        # Обновляем состояние в user_data
        context.user_data['conversation_state'] = CREATE_POST_TEXT
        
        await update.message.reply_text("Введите основной текст поста.")
        
        # Сбрасываем флаг обработки
        context.user_data['title_being_processed'] = False
        return CREATE_POST_TEXT
    except Exception as e:
        logger.error(f"Error in create_post_title: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, введите заголовок снова.")
        
        # Сбрасываем флаг обработки
        context.user_data['title_being_processed'] = False
        return CREATE_POST_TITLE

async def create_post_text(update, context):
    # Проверяем, не обрабатывается ли уже этот текст
    if context.user_data.get('text_being_processed') and context.user_data.get('text_processed_id') == update.message.message_id:
        logger.info(f"Skipping duplicate processing of text {update.message.message_id} in create_post_text")
        return CREATE_POST_PREVIEW
    
    # Отмечаем, что этот текст обрабатывается
    context.user_data['text_being_processed'] = True
    context.user_data['text_processed_id'] = update.message.message_id
    
    try:
        context.user_data["post_text"] = update.message.text
        logger.info(f"Post text received: {context.user_data['post_text']}")
        
        # Обновляем состояние в user_data
        context.user_data['conversation_state'] = CREATE_POST_PREVIEW
        
        # Формируем превью поста
        preview = format_post_preview(context.user_data["post_title"], context.user_data["post_text"])
        
        # Отправляем превью с фото
        keyboard = [
            [InlineKeyboardButton("Опубликовать пост", callback_data="publish_post")],
            [InlineKeyboardButton("Редактировать пост", callback_data="edit_post_preview")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=context.user_data["post_photo"],
            caption=preview,
            reply_markup=reply_markup
        )
        
        # Сбрасываем флаг обработки
        context.user_data['text_being_processed'] = False
        return CREATE_POST_PREVIEW
    except Exception as e:
        logger.error(f"Error in create_post_text: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, введите текст поста снова.")
        
        # Сбрасываем флаг обработки
        context.user_data['text_being_processed'] = False
        return CREATE_POST_TEXT

async def create_post_preview(update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == "publish_post":
        try:
            # Создаем пост в базе данных
            post_id = create_post(
                context.user_data["post_photo"],
                context.user_data["post_title"],
                context.user_data["post_text"]
            )
            
            # Формируем текст поста
            preview = format_post_preview(context.user_data["post_title"], context.user_data["post_text"])
            
            # Отправляем в канал или чат
            try:
                await context.bot.send_photo(
                    chat_id="@testkybik",  # Замените на нужный канал
                    photo=context.user_data["post_photo"],
                    caption=preview
                )
                
                # Отправляем новое сообщение вместо редактирования
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Пост опубликован!"
                )
                
                # Возвращаем в меню админа после короткой паузы
                await asyncio.sleep(1)
                await admin_panel(update, context)
            except Exception as e:
                logger.error(f"Error publishing post: {e}")
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Ошибка при публикации поста. Проверьте права бота в канале."
                )
                
                # Возвращаем в меню админа после короткой паузы даже при ошибке
                await asyncio.sleep(1)
                await admin_panel(update, context)
        except Exception as e:
            logger.error(f"Error creating post: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Ошибка при создании поста: {str(e)}"
            )
            
            # Возвращаем в меню админа после короткой паузы даже при ошибке
            await asyncio.sleep(1)
            await admin_panel(update, context)
    elif query.data == "edit_post_preview":
        # Отправляем новое сообщение вместо редактирования
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Загрузите фото для поста."
        )
        
        # Устанавливаем состояние в user_data
        context.user_data['conversation_state'] = CREATE_POST_PHOTO
        return CREATE_POST_PHOTO
    
    return ConversationHandler.END

# Отмена диалога
async def cancel(update, context):
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END

# Управление администраторами
async def add_admin_command(update, context):
    if update.effective_user.id != 6357518457:
        await update.message.reply_text("Только суперадминистратор может добавлять администраторов.")
        return
    try:
        user_id = int(context.args[0])
        add_admin(user_id)
        await update.message.reply_text(f"Администратор {user_id} добавлен.")
    except (IndexError, ValueError):
        await update.message.reply_text("Укажите Telegram ID администратора: /add_admin <ID>")

async def remove_admin_command(update, context):
    if update.effective_user.id != 6357518457:
        await update.message.reply_text("Только суперадминистратор может удалять администраторов.")
        return
    try:
        user_id = int(context.args[0])
        remove_admin(user_id)
        await update.message.reply_text(f"Администратор {user_id} удален.")
    except (IndexError, ValueError):
        await update.message.reply_text("Укажите Telegram ID администратора: /remove_admin <ID>")

# Основные функции бота для пользователей
async def start(update: Update, context: CallbackContext) -> None:
    welcome_text = (
        'Привет, это Базуми! Рады приветствовать вас в нашей службе заботы. Здесь вы сможете:\n'
        '- получить поддержку и ответ на любой вопрос по нашей продукции\n'
        '- поучаствовать в конкурсе и выиграть классные игрушки\n'
        '- найти видеоинструкции к игрушкам'
    )
    try:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome_text)
        await show_main_menu(update, context)
    except NetworkError:
        await update.message.reply_text("Ошибка сети. Проверьте подключение и попробуйте снова.")
    except Forbidden:
        await update.message.reply_text("Бот заблокирован вами. Разблокируйте бота, чтобы продолжить.")

async def show_main_menu(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton('Служба заботы ♥️', callback_data='support')],
        [InlineKeyboardButton('Еженедельные подарки 🎁', callback_data='gifts')],
        [InlineKeyboardButton('Видеоинструкции 📹', callback_data='videos')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.effective_chat.id, text='Выберите раздел:', reply_markup=reply_markup)

async def support_section(update: Update, context: CallbackContext) -> None:
    text = (
        'Трудности иногда случаются, но Bazumi всегда на связи. Здесь вы можете:\n'
        '- Получить консультации по выбору игрушек\n'
        '- Решить вопрос с браком или поломкой\n'
        '- Получить помощь в выборе подарка\n'
        '- Оставить ваш отзыв или пожелание'
    )
    keyboard = [[InlineKeyboardButton('Связаться с менеджером', callback_data='contact_manager')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)

async def contact_manager(update: Update, context: CallbackContext) -> None:
    text = 'Чтобы продолжить – подтвердите, что вы не бот. Мы не передаем ваши данные третьим лицам.'
    keyboard = [[InlineKeyboardButton('Я не бот ✅', callback_data='confirm_not_bot_support')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)
    except NetworkError:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Ошибка сети. Проверьте подключение и попробуйте снова.")
    except Forbidden:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Бот заблокирован вами. Разблокируйте бота, чтобы продолжить.")

async def confirm_not_bot_support(update: Update, context: CallbackContext) -> None:
    context.user_data['section'] = 'support'
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Пожалуйста, поделитесь своим номером телефона.',
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton('Отправить контакт', request_contact=True)]], one_time_keyboard=True)
    )

async def gifts_section(update: Update, context: CallbackContext) -> None:
    text = (
        'Еженедельные подарки 🎁\n'
        'Два раза в неделю мы проводим розыгрыш среди подписчиков нашего канала. У каждого есть шанс выиграть самые топовые модели из нашего ассортимента!'
    )
    keyboard = [[InlineKeyboardButton('Отлично, я в деле!', callback_data='participate_gifts')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)

async def participate_gifts(update: Update, context: CallbackContext) -> None:
    contest = get_active_contest()
    if contest:
        text = format_contest_preview(contest[2], contest[3])
    else:
        text = (
            'Супер, на этой неделе мы разыгрываем Набор Bazumi Ultra Puper Super\n'
            'Условия очень простые:\n'
            '- нажать "принять участие"\n'
            '- быть подписанным на канал @testkybik\n'
            '- дождаться результатов, они будут скоро в нашем канале'
        )
    keyboard = [[InlineKeyboardButton('Принять участие', callback_data='confirm_participate')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)

async def confirm_not_bot_gifts(update: Update, context: CallbackContext) -> None:
    context.user_data['section'] = 'gifts'
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Пожалуйста, поделитесь своим номером телефона.',
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton('Отправить контакт', request_contact=True)]], one_time_keyboard=True)
    )

async def videos_section(update: Update, context: CallbackContext) -> None:
    text = 'Сначала давайте определимся — с какой игрушкой вам нужна помощь!'
    keyboard = [
        [InlineKeyboardButton('Роботы Bazumi', callback_data='videos_bazumi')],
        [InlineKeyboardButton('Другое', callback_data='videos_other')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)

async def videos_bazumi(update: Update, context: CallbackContext) -> None:
    context.user_data['video_type'] = 'bazumi'
    context.user_data['section'] = 'videos'
    text = 'Чтобы получить доступ к инструкциям – подтвердите, что вы не бот. Мы не передаем ваши данные третьим лицам.'
    keyboard = [[InlineKeyboardButton('Я не бот', callback_data='confirm_not_bot_videos')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)
    await update.callback_query.answer()

async def videos_other(update: Update, context: CallbackContext) -> None:
    context.user_data['video_type'] = 'other'
    context.user_data['section'] = 'videos'
    text = 'Чтобы получить доступ к инструкциям – подтвердите, что вы не бот. Мы не передаем ваши данные третьим лицам.'
    keyboard = [[InlineKeyboardButton('Я не бот', callback_data='confirm_not_bot_videos')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)
    await update.callback_query.answer()

async def confirm_not_bot_videos(update: Update, context: CallbackContext) -> None:
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Пожалуйста, поделитесь своим номером телефона.',
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton('Отправить контакт', request_contact=True)]], one_time_keyboard=True)
    )

async def handle_contact(update: Update, context: CallbackContext) -> None:
    section = context.user_data.get('section')
    if update.message.contact:
        if section == 'support':
            text = 'Это Алексей – ваш личный менеджер Службы заботы. Напишите и мы поможем с решением любого вопроса.'
            keyboard = [[InlineKeyboardButton('Написать Алексею', url='https://t.me/AlexeyBazumi')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)
        elif section == 'gifts':
            contest = get_active_contest()
            if contest:
                add_participant(contest[0], update.effective_user.id, update.effective_user.username, update.message.contact.phone_number)
            text = 'Отлично, вы зарегистрированы как участник. Желаем вам удачи и остаемся на связи! Ваш Bazumi ♥️'
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
        elif section == 'videos':
            video_type = context.user_data.get('video_type')
            if video_type == 'bazumi':
                text = 'Спасибо! Отправляем вам ссылки на плейлист с нашими инструкциями. Выберите удобную для вас площадку.'
                keyboard = [
                    [InlineKeyboardButton('Rutube', url='https://rutube.ru/playlist')],
                    [InlineKeyboardButton('Youtube', url='https://youtube.com/playlist')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)
            elif video_type == 'other':
                text = 'Спасибо! К сожалению, у нас нет инструкций к другим игрушкам в открытом доступе – но у нас есть Служба заботы, где вам всегда помогут.'
                keyboard = [[InlineKeyboardButton('Написать Алексею', url='https://t.me/AlexeyBazumi')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)
        await context.bot.send_message(chat_id=update.effective_chat.id, text='Спасибо!', reply_markup=ReplyKeyboardRemove())
        await show_main_menu(update, context)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text='Пожалуйста, отправьте ваш контакт.')

async def handle_photo_for_conversation(update, context):
    """Обработчик фотографий для всех состояний разговора"""
    user_id = update.effective_user.id
    message_id = update.message.message_id
    logger.info(f"Received photo from user {user_id}, message_id: {message_id}")
    
    # Проверяем, не обрабатывается ли уже это фото
    if context.user_data.get('photo_processed_id') == message_id:
        logger.info(f"Photo {message_id} is already being processed, skipping")
        return
    
    # Проверяем состояние в user_data
    state = context.user_data.get('conversation_state')
    logger.info(f"Current state for user {user_id}: {state}")
    
    # Вместо проверки ConversationHandler.conversations, просто используем состояние из user_data
    if state == CREATE_CONTEST_PHOTO:
        # Проверяем, не обрабатывается ли уже это сообщение в ConversationHandler
        if not context.user_data.get('photo_being_processed'):
            # Устанавливаем флаг, что фото обрабатывается
            context.user_data['photo_being_processed'] = True
            context.user_data['photo_processed_id'] = message_id
            logger.info(f"Redirecting to create_contest_photo for user {user_id}")
            try:
                return await create_contest_photo(update, context)
            finally:
                # Сбрасываем флаг после обработки
                context.user_data['photo_being_processed'] = False
        else:
            logger.info(f"Photo is already being processed for user {user_id}")
    elif state == EDIT_CONTEST_PHOTO:
        if not context.user_data.get('photo_being_processed'):
            context.user_data['photo_being_processed'] = True
            context.user_data['photo_processed_id'] = message_id
            logger.info(f"Redirecting to edit_contest_photo for user {user_id}")
            try:
                return await edit_contest_photo(update, context)
            finally:
                context.user_data['photo_being_processed'] = False
        else:
            logger.info(f"Photo is already being processed for user {user_id}")
    elif state == CREATE_POST_PHOTO:
        if not context.user_data.get('photo_being_processed'):
            context.user_data['photo_being_processed'] = True
            context.user_data['photo_processed_id'] = message_id
            logger.info(f"Redirecting to create_post_photo for user {user_id}")
            try:
                return await create_post_photo(update, context)
            finally:
                context.user_data['photo_being_processed'] = False
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
    user_state = context.user_data.get('conversation_state', 'No state in user_data')
    
    # Проверяем состояние в ConversationHandler
    conv_states = []
    for group, handlers in application.handlers.items():
        for handler in handlers:
            if isinstance(handler, ConversationHandler):
                state = handler.conversations.get((chat_id, user_id))
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
            text="Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте снова."
        )

async def show_contest_menu(update, context):
    """Показывает меню управления конкурсом"""
    keyboard = [
        [InlineKeyboardButton("Создать новый конкурс", callback_data="create_contest")],
        [InlineKeyboardButton("Редактировать текущий конкурс", callback_data="edit_contest")],
        [InlineKeyboardButton("Удалить текущий конкурс", callback_data="delete_contest")],
        [InlineKeyboardButton("Уведомление о текущем конкурсе", callback_data="notify_contest")],
        [InlineKeyboardButton("Выгрузить участников", callback_data="export_participants")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Всегда отправляем новое сообщение
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Управление конкурсом:",
        reply_markup=reply_markup
    )

def main():
    init_db()
    application = Application.builder().token("7972510069:AAGEWyXr5BQlydxbkwsziyfGxxtscsMTPfs").build()

    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)

    # ConversationHandler для создания конкурса - перемещаем его в начало
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
        per_chat=True,
        name="create_contest_conversation"
    )
    
    # ConversationHandler для редактирования конкурса
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
    
    # ConversationHandler для создания поста
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
    
    # Добавляем обработчики с высоким приоритетом
    application.add_handler(create_contest_handler, group=0)
    application.add_handler(edit_contest_handler, group=0)
    application.add_handler(create_post_handler, group=0)
    
    # Остальные обработчики с более низким приоритетом
    application.add_handler(CommandHandler("admin", admin_panel), group=1)
    application.add_handler(CommandHandler("add_admin", add_admin_command), group=1)
    application.add_handler(CommandHandler("remove_admin", remove_admin_command), group=1)
    
    # Обработчики для меню и других действий
    application.add_handler(CallbackQueryHandler(contest_menu, pattern="^contest$"), group=1)
    application.add_handler(CallbackQueryHandler(delete_contest, pattern="^delete_contest$"), group=1)
    application.add_handler(CallbackQueryHandler(notify_contest, pattern="^notify_contest$"), group=1)
    application.add_handler(CallbackQueryHandler(export_participants, pattern="^export_participants$"), group=1)
    application.add_handler(CallbackQueryHandler(participate, pattern="^participate$"), group=1)
    application.add_handler(CallbackQueryHandler(confirm_participate, pattern="^confirm_participate$"), group=1)
    application.add_handler(CallbackQueryHandler(confirm_delete, pattern="^confirm_delete$"), group=1)
    application.add_handler(CallbackQueryHandler(cancel_delete, pattern="^cancel_delete$"), group=1)
    
    # ConversationHandler для участия в конкурсе
    participate_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(participate, pattern="^participate$")],
        states={
            PARTICIPATE_CONFIRM: [MessageHandler(filters.CONTACT, receive_contact)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        name="participate_conversation"
    )
    application.add_handler(participate_handler, group=0)
    
    # Обработчики основного бота
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
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact), group=1)

    # Добавляем обработчик фотографий с более низким приоритетом
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_for_conversation), group=1)

    # Добавьте в конец main() перед run_polling:
    application.add_handler(CommandHandler("state", check_state), group=0)
    application.add_handler(CommandHandler("debug", debug_state), group=0)

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()