import logging
import os
import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
)
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from database import (
    initialize_database, add_user_if_not_exists, get_user_accounts,
    delete_account, get_session_string, save_reserved_channel, get_reserved_channels_by_phone,
    set_admin_status, get_admins, save_account
)
from telethon_handler import (
    connect_and_send_code,
    sign_in_with_code,
    sign_in_with_password,
    check_username_availability,
    create_channel_and_set_username
)
from username_generator import generate_usernames

# --- Configuration ---
# You need to get these from my.telegram.org and @BotFather
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
API_ID = os.environ.get("API_ID", "YOUR_API_ID_HERE")
API_HASH = os.environ.get("API_HASH", "YOUR_API_HASH_HERE")
ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", "YOUR_ADMIN_ID_HERE"))

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Bot Handlers (will be implemented in the next steps) ---

# --- Global State & Admin Config ---
BOT_IS_ACTIVE = True
ADMINS = []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command and displays the main menu."""
    user = update.effective_user
    add_user_if_not_exists(user.id)

    if not BOT_IS_ACTIVE and user.id not in ADMINS:
        await update.message.reply_text("البوت قيد الصيانة حالياً. الرجاء المحاولة لاحقاً.")
        return

    welcome_message = f"👋 أهلاً بك يا {user.first_name}!\n\nأنا بوت فحص وحجز أسماء المستخدمين."
    keyboard = [
        [InlineKeyboardButton("➕ إضافة حساب جديد", callback_data='add_account')],
        [InlineKeyboardButton("👤 حساباتي", callback_data='my_accounts')],
        [InlineKeyboardButton("🔍 فحص أسماء المستخدمين", callback_data='check_usernames')],
        [InlineKeyboardButton("📺 عرض القنوات المحجوزة", callback_data='view_channels')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(welcome_message, reply_markup=reply_markup)
    else:
        await update.message.reply_text(welcome_message, reply_markup=reply_markup)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /admin command and shows the admin panel."""
    user_id = update.effective_user.id
    if user_id in ADMINS:
        status_text = "🟢 مفعل" if BOT_IS_ACTIVE else "🔴 موقف"
        keyboard = [
            [InlineKeyboardButton(f"تشغيل/إيقاف البوت ({status_text})", callback_data='admin_toggle_bot')],
            [InlineKeyboardButton("➕ إضافة مشرف", callback_data='admin_add_admin')],
            [InlineKeyboardButton("➖ حذف مشرف", callback_data='admin_remove_admin')],
            [InlineKeyboardButton("⭐ (قريباً) تفعيل الاشتراك المدفوع", callback_data='admin_soon')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("--== لوحة تحكم المدير ==--", reply_markup=reply_markup)
    else:
        logger.warning(f"Unauthorized /admin attempt by user {user_id}")

# --- Conversation States ---
PHONE, CODE, PASSWORD = range(3)

# --- Conversation Handlers ---
async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation to add a new account."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="الرجاء إرسال رقم هاتفك مع الرمز الدولي (مثال: +967xxxxxxxxx).")
    return PHONE

async def received_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the phone number and sends the login code."""
    phone_number = update.message.text
    context.user_data['phone_number'] = phone_number

    await update.message.reply_text("جاري الاتصال بـ Telegram لإرسال الكود...")

    client, phone_code_hash = await connect_and_send_code(API_ID, API_HASH, phone_number)

    if client and phone_code_hash:
        context.user_data['client'] = client
        context.user_data['phone_code_hash'] = phone_code_hash
        await update.message.reply_text("تم إرسال الكود. الرجاء إرساله هنا.")
        return CODE
    else:
        await update.message.reply_text("حدث خطأ أثناء إرسال الكود. الرجاء المحاولة مرة أخرى.")
        return ConversationHandler.END

async def received_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the login code, and checks if 2FA is needed."""
    code = update.message.text
    client = context.user_data['client']
    phone_number = context.user_data['phone_number']
    phone_code_hash = context.user_data['phone_code_hash']

    try:
        # Try to sign in with the code
        user = await sign_in_with_code(client, phone_number, code, phone_code_hash)
        # If sign_in_with_code returns a user, it means 2FA was NOT needed and login is complete.
        if user:
            await update.message.reply_text("تم تسجيل الدخول بنجاح (لم يكن التحقق بخطوتين مطلوباً).")
            await finalize_login(update, context, client)
            return ConversationHandler.END
        # If it returns None without an exception, it's an unknown error.
        else:
            await update.message.reply_text("حدث خطأ غير متوقع أثناء محاولة تسجيل الدخول.")
            await client.disconnect()
            return ConversationHandler.END

    except SessionPasswordNeededError:
        # This is the expected case for 2FA. Telegram is asking for the password.
        logger.info(f"2FA password needed for {phone_number}.")
        await update.message.reply_text("الحساب محمي. الرجاء إرسال كلمة مرور التحقق بخطوتين.")
        return PASSWORD

    except PhoneCodeInvalidError:
        logger.warning(f"Invalid code entered for {phone_number}.")
        await update.message.reply_text("الرمز الذي أدخلته غير صحيح. تم إلغاء العملية.")
        await client.disconnect()
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"An unexpected error occurred during code sign-in for {phone_number}: {e}")
        await update.message.reply_text("حدث خطأ فادح أثناء التحقق من الرمز. تم إلغاء العملية.")
        if client.is_connected():
            await client.disconnect()
        return ConversationHandler.END

async def received_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the 2FA password."""
    password = update.message.text
    client = context.user_data['client']

    user = await sign_in_with_password(client, password)
    if user:
        await finalize_login(update, context, client)
    else:
        await update.message.reply_text("كلمة المرور غير صحيحة. تم إلغاء العملية.")

    return ConversationHandler.END

async def finalize_login(update: Update, context: ContextTypes.DEFAULT_TYPE, client):
    """Saves the session and informs the user."""
    session_string = client.session.save()
    phone_number = context.user_data['phone_number']
    user_id = update.effective_user.id

    if save_account(user_id, phone_number, session_string):
        await update.message.reply_text("تم تسجيل الدخول بنجاح وحفظ الحساب!")
    else:
        await update.message.reply_text("حدث خطأ أثناء حفظ الحساب.")

    if client and client.is_connected():
        await client.disconnect()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    await update.message.reply_text("تم إلغاء العملية.")
    if 'client' in context.user_data and context.user_data['client'].is_connected():
        await context.user_data['client'].disconnect()
    return ConversationHandler.END

async def show_my_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays a list of the user's accounts with delete buttons."""
    query = update.callback_query
    user_id = update.effective_user.id
    accounts = get_user_accounts(user_id)

    if not accounts:
        message_text = "لم تقم بإضافة أي حسابات بعد."
        keyboard = [[InlineKeyboardButton("🔙 العودة إلى القائمة الرئيسية", callback_data='main_menu')]]
    else:
        message_text = "حساباتك المسجلة. اضغط على 'حذف' لإزالة حساب."
        keyboard = []
        for phone in accounts:
            # Note: Using a prefix `delete_` for the callback data
            keyboard.append([
                InlineKeyboardButton(f"📱 {phone}", callback_data=f"info_{phone}"),
                InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_{phone}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 العودة إلى القائمة الرئيسية", callback_data='main_menu')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=message_text, reply_markup=reply_markup)


# --- Global dictionary to hold active checking tasks ---
# Structure: {user_id: asyncio.Task}
active_checkers = {}


async def choose_account_for_checking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asks the user to choose an account to start checking usernames."""
    query = update.callback_query
    user_id = update.effective_user.id
    accounts = get_user_accounts(user_id)

    if not accounts:
        await query.edit_message_text(text="الرجاء إضافة حساب أولاً لبدء الفحص.")
        return

    keyboard = []
    for phone in accounts:
        keyboard.append([InlineKeyboardButton(f"📱 {phone}", callback_data=f"startcheck_{phone}")])
    keyboard.append([InlineKeyboardButton("🔙 عودة", callback_data='main_menu')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text="اختر الحساب الذي تريد استخدامه لفحص أسماء المستخدمين:", reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parses the CallbackQuery and delegates the action to the respective function."""
    query = update.callback_query
    command = query.data
    user_id = update.effective_user.id
    logger.info(f"User {user_id} pressed button: {command}")

    # --- DELETION LOGIC ---
    if command.startswith('delete_'):
        phone_to_delete = command.split('_', 1)[1]
        delete_account(phone_to_delete)
        await query.answer("تم حذف الحساب بنجاح!")
        return await show_my_accounts(update, context)

    # --- CHECKER CONTROL ---
    elif command.startswith('startcheck_'):
        return await start_checker_callback(update, context)
    elif command == 'stop_check':
        return await stop_checker_callback(update, context)

    # --- ADMIN BUTTONS ---
    elif command == 'admin_toggle_bot':
        if user_id not in ADMINS:
            await query.answer("ليس لديك صلاحية لتنفيذ هذا الإجراء.", show_alert=True)
            return
        return await toggle_bot_status_callback(update, context)

    # --- ROUTER LOGIC ---
    # Using a dictionary to map commands to functions for cleaner code
    command_routes = {
        'my_accounts': show_my_accounts,
        'main_menu': start,
        'check_usernames': choose_account_for_checking,
        'view_channels': choose_account_for_viewing_channels,
    }

    if command in command_routes:
        await command_routes[command](update, context)
    elif command.startswith('viewch_'):
        phone_to_view = command.split('_', 1)[1]
        await show_reserved_channels(update, context, phone_to_view)
    elif not command.startswith(('info_', 'add_account', 'admin_')):
        await query.edit_message_text(text="Unknown command.")

# --- Callback Helper Functions ---
async def start_checker_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the button press to start the username checker."""
    query = update.callback_query
    user_id = update.effective_user.id
    if user_id in active_checkers and not active_checkers[user_id].done():
        await query.answer("لديك عملية فحص نشطة بالفعل.", show_alert=True)
        return

    phone_to_use = query.data.split('_', 1)[1]
    await query.edit_message_text(text=f"تم بدء عملية الفحص باستخدام الرقم {phone_to_use}. سأرسل لك تحديثات...")

    task = asyncio.create_task(run_username_checker(update, context, user_id, phone_to_use))
    active_checkers[user_id] = task

async def stop_checker_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the button press to stop the username checker."""
    query = update.callback_query
    user_id = update.effective_user.id
    if user_id in active_checkers and not active_checkers[user_id].done():
        active_checkers[user_id].cancel()
        del active_checkers[user_id]
        await query.edit_message_text(text="تم إيقاف عملية الفحص.")
    else:
        await query.answer("لا توجد عملية فحص نشطة لإيقافها.", show_alert=True)

async def toggle_bot_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the button press to toggle bot's active status and refreshes the panel."""
    query = update.callback_query
    global BOT_IS_ACTIVE
    BOT_IS_ACTIVE = not BOT_IS_ACTIVE
    await query.answer(f"تم {'تفعيل' if BOT_IS_ACTIVE else 'إيقاف'} البوت للمستخدمين.")

    # Correctly refresh the admin panel
    status_text = "🟢 مفعل" if BOT_IS_ACTIVE else "🔴 موقف"
    keyboard = [
        [InlineKeyboardButton(f"تشغيل/إيقاف البوت ({status_text})", callback_data='admin_toggle_bot')],
        [InlineKeyboardButton("➕ إضافة مشرف", callback_data='admin_add_admin')],
        [InlineKeyboardButton("➖ حذف مشرف", callback_data='admin_remove_admin')],
        [InlineKeyboardButton("⭐ (قريباً) تفعيل الاشتراك المدفوع", callback_data='admin_soon')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("--== لوحة تحكم المدير ==-- (تم التحديث)", reply_markup=reply_markup)


async def choose_account_for_viewing_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asks the user to choose an account to view its reserved channels."""
    query = update.callback_query
    user_id = update.effective_user.id
    accounts = get_user_accounts(user_id)

    if not accounts:
        await query.edit_message_text(text="ليس لديك أي حسابات لعرض قنواتها.")
        return

    keyboard = []
    for phone in accounts:
        keyboard.append([InlineKeyboardButton(f"📱 {phone}", callback_data=f"viewch_{phone}")])
    keyboard.append([InlineKeyboardButton("🔙 عودة", callback_data='main_menu')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text="اختر الحساب الذي تريد عرض قنواته المحجوزة:", reply_markup=reply_markup)

async def show_reserved_channels(update: Update, context: ContextTypes.DEFAULT_TYPE, phone_number):
    """Displays a list of reserved channels for a given phone number."""
    query = update.callback_query
    channels = get_reserved_channels_by_phone(phone_number)

    if not channels:
        message_text = f"لا توجد قنوات محجوزة لهذا الحساب: `{phone_number}`"
    else:
        message_text = f"القنوات المحجوزة بواسطة `{phone_number}`:\n\n"
        message_text += "\n".join([f"@{ch}" for ch in channels])

    keyboard = [[InlineKeyboardButton("🔙 العودة إلى اختيار الحساب", callback_data='view_channels')],
                [InlineKeyboardButton("🔝 القائمة الرئيسية", callback_data='main_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')


# --- Username Checker Logic ---

async def run_username_checker(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, phone_number):
    """The main async task for checking usernames with live message updates."""
    session_string = get_session_string(phone_number)
    if not session_string:
        await context.bot.send_message(user_id, "خطأ: لم يتم العثور على جلسة لهذا الحساب.")
        return

    # Send initial status message and store its ID
    status_message = await context.bot.send_message(
        user_id, "Starting username check...",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 إيقاف الفحص", callback_data='stop_check')]])
    )
    last_update_time = asyncio.get_event_loop().time()

    client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
    stats = {"total": 0, "available": [], "unavailable": 0}

    try:
        await client.connect()
        username_gen = generate_usernames()

        for username in username_gen:
            await asyncio.sleep(5)  # Configurable Delay

            stats["total"] += 1
            status, wait_time = await check_username_availability(client, username)

            if status == 'flood':
                await context.bot.send_message(user_id, f"تم حظري مؤقتاً. سأنتظر لمدة {wait_time} ثانية ثم أكمل.")
                await asyncio.sleep(wait_time)
                continue

            if status == 'invalid' or status == 'error':
                stats["unavailable"] += 1
            elif status == 'occupied':
                stats["unavailable"] += 1
            elif status == 'available':
                stats["available"].append(username)
                reserved = await create_channel_and_set_username(client, username)
                if reserved:
                    save_reserved_channel(username, phone_number)
                    # Send a notification to the user
                    await context.bot.send_message(
                        user_id,
                        f"🎉 **تم بنجاح حجز اسم المستخدم:** @{username}",
                        parse_mode='Markdown'
                    )

            # Throttle updates to avoid hitting Telegram API limits
            current_time = asyncio.get_event_loop().time()
            if current_time - last_update_time >= 1: # Update at most once per second
                status_text = (
                    f"🔄 **جاري فحص أسماء المستخدمين...**\n\n"
                    f"📞 **رقم الهاتف:** `{phone_number}`\n"
                    f"📝 **اسم المستخدم الحالي:** `{username}`\n"
                    f"✅ **المتاحة والمحجوزة:** {len(stats['available'])}\n"
                    f"   └ {' | '.join(stats['available']) if stats['available'] else 'لا يوجد'}\n"
                    f"❌ **غير المتاحة:** {stats['unavailable']}\n"
                    f"📊 **الإجمالي:** {stats['total']}"
                )
                try:
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=status_message.message_id,
                        text=status_text,
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 إيقاف الفحص", callback_data='stop_check')]])
                    )
                    last_update_time = current_time
                except Exception as e:
                    logger.warning(f"Could not update status message: {e}")

    except asyncio.CancelledError:
        logger.info(f"Checker task for user {user_id} was cancelled.")
        await context.bot.edit_message_text(chat_id=user_id, message_id=status_message.message_id, text="تم إيقاف عملية الفحص.")
    except Exception as e:
        logger.error(f"An error occurred in the checker for user {user_id}: {e}")
        await context.bot.send_message(user_id, "حدث خطأ فادح وتوقفت عملية الفحص.")
    finally:
        if client.is_connected():
            await client.disconnect()
        if user_id in active_checkers:
            del active_checkers[user_id]
        logger.info(f"Checker task for user {user_id} finished.")
        # Final update message
        final_text = f"انتهت عملية الفحص. \nالإجمالي: {stats['total']}, المتاحة: {len(stats['available'])}"
        await context.bot.edit_message_text(chat_id=user_id, message_id=status_message.message_id, text=final_text)


# --- Main Application Logic ---

def main():
    """Starts the bot."""
    global ADMINS
    logger.info("Initializing database...")
    initialize_database()
    # Set the super admin
    set_admin_status(ADMIN_USER_ID, True)
    ADMINS = get_admins()
    logger.info(f"Loaded admins: {ADMINS}")

    logger.info("Setting up bot...")
    application = Application.builder().token(BOT_TOKEN).build()

    # --- Conversation Handler for adding/removing admins ---
    async def ask_for_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
        """Helper to start the admin add/remove conversation."""
        query = update.callback_query
        user_id = update.effective_user.id

        if user_id not in ADMINS:
            await query.answer("ليس لديك صلاحية لتنفيذ هذا الإجراء.", show_alert=True)
            return ConversationHandler.END

        await query.answer()
        prompt = "أرسل ID المشرف الجديد الذي تريد إضافته:" if action == "add" else "أرسل ID المشرف الذي تريد حذفه:"
        await query.edit_message_text(text=prompt)
        return 0 # Move to the state where we wait for the ID

    add_admin_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u, c: ask_for_admin_id(u, c, "add"), pattern='^admin_add_admin$')],
        states={0: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_received)]},
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    remove_admin_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u, c: ask_for_admin_id(u, c, "remove"), pattern='^admin_remove_admin$')],
        states={0: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_admin_received)]},
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # --- Conversation Handler for adding accounts ---
    add_account_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_account_start, pattern='^add_account$')],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_phone)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_code)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_password)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # --- Register Handlers ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(add_account_conv)
    application.add_handler(add_admin_handler)
    application.add_handler(remove_admin_handler)
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot is starting...")
    try:
        application.run_polling()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutting down...")
        # Cancel any running checker tasks
        for task in active_checkers.values():
            if not task.done():
                task.cancel()
        logger.info("All checker tasks cancelled. Goodbye!")


async def add_admin_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives the ID for the new admin."""
    try:
        new_admin_id = int(update.message.text)
        set_admin_status(new_admin_id, True)
        ADMINS.append(new_admin_id)
        await update.message.reply_text(f"تمت إضافة {new_admin_id} كمشرف بنجاح.")
    except ValueError:
        await update.message.reply_text("الرجاء إرسال ID صحيح (رقم).")
    return ConversationHandler.END

async def remove_admin_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives the ID for the admin to remove."""
    try:
        admin_id_to_remove = int(update.message.text)
        if admin_id_to_remove == ADMIN_USER_ID:
            await update.message.reply_text("لا يمكن حذف المدير الخارق.")
            return ConversationHandler.END

        set_admin_status(admin_id_to_remove, False)
        if admin_id_to_remove in ADMINS:
            ADMINS.remove(admin_id_to_remove)
        await update.message.reply_text(f"تم حذف المشرف {admin_id_to_remove} بنجاح.")
    except ValueError:
        await update.message.reply_text("الرجاء إرسال ID صحيح (رقم).")
    return ConversationHandler.END


if __name__ == '__main__':
    main()
