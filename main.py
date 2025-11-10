# main.py
import configparser
import logging
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from database import (
    initialize_database, add_user, add_account, get_user_accounts,
    delete_account, get_groups_created_today, increment_groups_created,
    get_account_details
)
import telethon_handler
from telethon import TelegramClient

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Constants ---
# You can modify these values to change the bot's behavior.

# The maximum number of groups a single account can create per day.
MAX_GROUPS_PER_DAY = 50

# The time delay (in seconds) between the creation of each group.
# IMPORTANT: A longer delay is safer to avoid account restrictions.
GROUP_CREATION_INTERVAL = 60

# Conversation states
(
    # Add Account
    ASK_API_ID, ASK_API_HASH, ASK_PHONE, ASK_CODE, ASK_2FA_PASS,
    # Create Groups
    SELECT_ACCOUNT_FOR_CREATION, ASK_GROUP_COUNT,
) = range(7)

(
    # Main Menu callbacks
    ADD_ACCOUNT, MY_ACCOUNTS, START_CREATION,
    # Other callbacks
    DELETE_ACCOUNT, CHOOSE_ACCOUNT_FOR_CREATION,
) = map(str, range(7, 12))


# --- Main Menu & Common Handlers ---
def get_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ إضافة حساب", callback_data=ADD_ACCOUNT)],
        [InlineKeyboardButton("🗂️ حساباتي", callback_data=MY_ACCOUNTS)],
        [InlineKeyboardButton("🚀 بدء الإنشاء", callback_data=START_CREATION)],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    add_user(user.id, user.first_name)
    await update.message.reply_html(
        rf'أهلاً بك {user.mention_html()}!',
        reply_markup=get_main_menu_keyboard(),
    )

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text="القائمة الرئيسية:", reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END


# --- Account Management ---
async def my_accounts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    accounts = get_user_accounts(update.effective_user.id)
    if not accounts:
        await query.edit_message_text(text="لم تقم بإضافة أي حسابات بعد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("عودة", callback_data='back_to_main')]]))
        return
    keyboard = [[InlineKeyboardButton(f"🗑️ {acc}", callback_data=f"{DELETE_ACCOUNT}:{acc}")] for acc in accounts]
    keyboard.append([InlineKeyboardButton("عودة", callback_data='back_to_main')])
    await query.edit_message_text(text="قائمة حساباتك:", reply_markup=InlineKeyboardMarkup(keyboard))

async def delete_account_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    phone_number = query.data.split(':')[1]
    delete_account(phone_number)
    session_file = f"{phone_number}.session"
    if os.path.exists(session_file):
        os.remove(session_file)
    await query.edit_message_text(text=f"تم حذف الحساب {phone_number} بنجاح.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("عودة إلى الحسابات", callback_data=MY_ACCOUNTS)]]))

# --- Add Account Conversation ---
add_account_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(lambda u, c: c.bot.send_message(u.effective_chat.id, "أرسل `API_ID` الخاص بك.") or ASK_API_ID, pattern='^' + ADD_ACCOUNT + '$')],
    states={
        ASK_API_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: c.user_data.update({'api_id': u.message.text}) or u.message.reply_text("عظيم! الآن أرسل `API_HASH` الخاص بك.") or ASK_API_HASH)],
        ASK_API_HASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: c.user_data.update({'api_hash': u.message.text}) or u.message.reply_text("ممتاز. الآن أرسل رقم الهاتف مع رمز الدولة (مثال: +1234567890).") or ASK_PHONE)],
        ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_code)],
        ASK_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_2fa)],
        ASK_2FA_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_with_2fa)],
    },
    fallbacks=[CommandHandler('cancel', lambda u, c: u.message.reply_text('تم إلغاء العملية.', reply_markup=get_main_menu_keyboard()) or ConversationHandler.END)],
)
async def ask_code(update, context):
    context.user_data['phone'] = update.message.text
    await update.message.reply_text("جاري محاولة تسجيل الدخول...")
    client, error = await telethon_handler.start_client_login(context.user_data['api_id'], context.user_data['api_hash'], context.user_data['phone'])
    if error:
        await update.message.reply_text(f"حدث خطأ: {error}\n\nالرجاء المحاولة مرة أخرى.")
        return ConversationHandler.END
    context.user_data['client'] = client
    await update.message.reply_text("تم إرسال رمز التحقق إلى حسابك في تيليجرام. الرجاء إرساله هنا.")
    return ASK_CODE
async def ask_2fa(update, context):
    result, error = await telethon_handler.submit_login_code(context.user_data['client'], context.user_data['phone'], update.message.text)
    if result == "SUCCESS":
        add_account(update.effective_user.id, context.user_data['phone'], context.user_data['api_id'], context.user_data['api_hash'])
        await update.message.reply_text("تم تسجيل الدخول بنجاح! تم حفظ الحساب.")
        await context.user_data['client'].disconnect()
        return ConversationHandler.END
    elif result == "2FA_NEEDED":
        await update.message.reply_text("الحساب محمي بكلمة مرور التحقق بخطوتين. الرجاء إرسالها.")
        return ASK_2FA_PASS
    else:
        await update.message.reply_text(f"حدث خطأ: {error}\n\nالرجاء المحاولة مرة أخرى.")
        await context.user_data['client'].disconnect()
        return ConversationHandler.END
async def login_with_2fa(update, context):
    result, error = await telethon_handler.submit_2fa_password(context.user_data['client'], update.message.text)
    if result == "SUCCESS":
        add_account(update.effective_user.id, context.user_data['phone'], context.user_data['api_id'], context.user_data['api_hash'])
        await update.message.reply_text("تم تسجيل الدخول بنجاح! تم حفظ الحساب.")
    else:
        await update.message.reply_text(f"حدث خطأ: {error}\n\nالرجاء المحاولة مرة أخرى.")
    await context.user_data['client'].disconnect()
    return ConversationHandler.END

# --- Create Groups Conversation ---
async def start_creation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    accounts = get_user_accounts(update.effective_user.id)
    if not accounts:
        await query.edit_message_text(text="يجب إضافة حساب واحد على الأقل أولاً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("عودة", callback_data='back_to_main')]]))
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(acc, callback_data=f"{CHOOSE_ACCOUNT_FOR_CREATION}:{acc}")] for acc in accounts]
    keyboard.append([InlineKeyboardButton("إلغاء", callback_data='cancel_creation')])
    await query.edit_message_text(text="اختر الحساب الذي تريد استخدامه لإنشاء المجموعات:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_ACCOUNT_FOR_CREATION

async def ask_group_count_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    phone = query.data.split(':')[1]
    context.user_data['selected_phone'] = phone
    groups_today = get_groups_created_today(phone)
    remaining = MAX_GROUPS_PER_DAY - groups_today
    if remaining <= 0:
        await query.edit_message_text(text=f"لقد وصلت إلى الحد الأقصى لإنشاء المجموعات لهذا الحساب اليوم ({MAX_GROUPS_PER_DAY} مجموعة).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("عودة", callback_data='back_to_main')]]))
        return ConversationHandler.END
    await query.edit_message_text(text=f"تم إنشاء {groups_today} مجموعة اليوم.\nيمكنك إنشاء {remaining} مجموعة إضافية.\n\nأرسل عدد المجموعات التي تريد إنشاءها:")
    return ASK_GROUP_COUNT

async def create_groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        count = int(update.message.text)
    except ValueError:
        await update.message.reply_text("الرجاء إرسال رقم صحيح.")
        return ASK_GROUP_COUNT

    phone = context.user_data['selected_phone']
    groups_today = get_groups_created_today(phone)
    remaining = MAX_GROUPS_PER_DAY - groups_today

    if not (0 < count <= remaining):
        await update.message.reply_text(f"رقم غير صالح. يمكنك إنشاء من 1 إلى {remaining} مجموعة.")
        return ASK_GROUP_COUNT

    await update.message.reply_text(f"حسنًا! سأقوم بإنشاء {count} مجموعة باستخدام الحساب {phone}.\nقد تستغرق هذه العملية بعض الوقت...")

    api_id, api_hash = get_account_details(phone)
    client = TelegramClient(f"{phone}.session", api_id, api_hash)

    try:
        await client.connect()
        if not await client.is_user_authorized():
            await update.message.reply_text("فشل تسجيل الدخول. يرجى حذف الحساب وإضافته مرة أخرى.", reply_markup=get_main_menu_keyboard())
            return ConversationHandler.END

        for i in range(count):
            group_num = groups_today + i + 1
            group_name = f"Group {group_num}"
            await update.message.reply_text(f"جاري إنشاء المجموعة رقم {i+1}/{count}: {group_name}...")

            result, error = await telethon_handler.create_group(client, group_name)

            if error:
                await update.message.reply_text(f"فشل إنشاء المجموعة {group_name}. الخطأ: {error}")
                await asyncio.sleep(5) # Wait a bit before next try
                continue

            increment_groups_created(phone)
            await update.message.reply_text(f"✅ تم إنشاء المجموعة {group_name} بنجاح.")

            # This is the delay between group creations. You can change the value of GROUP_CREATION_INTERVAL.
            await asyncio.sleep(GROUP_CREATION_INTERVAL)

    except Exception as e:
        logger.error(f"Error during group creation: {e}")
        await update.message.reply_text(f"حدث خطأ فادح: {e}", reply_markup=get_main_menu_keyboard())
    finally:
        if client.is_connected():
            await client.disconnect()

    await update.message.reply_text("🎉 اكتملت عملية إنشاء جميع المجموعات!", reply_markup=get_main_menu_keyboard())
    return ConversationHandler.END

async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="تم إلغاء عملية الإنشاء.", reply_markup=get_main_menu_keyboard())
    return ConversationHandler.END


# --- Main Application Setup ---
def main() -> None:
    config = configparser.ConfigParser()
    config.read('config.ini')
    bot_token = config['bot']['bot_token']
    if 'YOUR_BOT_TOKEN' in bot_token:
        logger.error("Please replace 'YOUR_BOT_TOKEN' in config.ini")
        return

    initialize_database()
    application = Application.builder().token(bot_token).build()

    create_groups_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_creation_handler, pattern='^' + START_CREATION + '$')],
        states={
            SELECT_ACCOUNT_FOR_CREATION: [CallbackQueryHandler(ask_group_count_handler, pattern=f'^{CHOOSE_ACCOUNT_FOR_CREATION}:.*$')],
            ASK_GROUP_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_groups_handler)],
        },
        fallbacks=[CallbackQueryHandler(cancel_creation, pattern='^cancel_creation$')],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(add_account_conv)
    application.add_handler(create_groups_conv)
    application.add_handler(CallbackQueryHandler(my_accounts_handler, pattern='^' + MY_ACCOUNTS + '$'))
    application.add_handler(CallbackQueryHandler(delete_account_handler, pattern=f'^{DELETE_ACCOUNT}:.*$'))
    application.add_handler(CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main$'))

    application.run_polling()

if __name__ == '__main__':
    main()
