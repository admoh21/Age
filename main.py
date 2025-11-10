# main.py
import configparser
import logging
import asyncio
import os
from datetime import datetime, timedelta
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
    add_group, get_user_groups, update_account_ban_status, get_total_groups_by_phone,
    get_total_groups_by_user, update_account_status
)
import telethon_handler
from telethon import TelegramClient
from telethon.errors.rpcerrorlist import FloodWaitError

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
    ASK_PHONE, ASK_CODE, ASK_2FA_PASS,
    # Create Groups
    SELECT_ACCOUNT_FOR_CREATION, ASK_GROUP_COUNT,
) = range(5)

(
    # Main Menu callbacks
    ADD_ACCOUNT, MY_ACCOUNTS, START_CREATION,
    # Other callbacks
    DELETE_ACCOUNT, CHOOSE_ACCOUNT_FOR_CREATION,
) = map(str, range(5, 10))

# --- Global Config ---
config = configparser.ConfigParser()
config.read('config.ini')
API_ID = config['telegram']['api_id']
API_HASH = config['telegram']['api_hash']
BOT_TOKEN = config['bot']['bot_token']


# --- Main Menu & Common Handlers ---
def get_main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("➕ إضافة حساب", callback_data=ADD_ACCOUNT),
            InlineKeyboardButton("🗂️ حساباتي", callback_data=MY_ACCOUNTS)
        ],
        [
            InlineKeyboardButton("🚀 بدء الإنشاء", callback_data=START_CREATION),
            InlineKeyboardButton("📂 عرض المجموعات", callback_data="show_groups")
        ],
        [
            InlineKeyboardButton("⚖️ إخلاء المسؤولية", callback_data="disclaimer")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    add_user(user.id, user.first_name)
    welcome_message = f"""
👋 **أهلاً بك يا {user.mention_html()} في بوت إنشاء المجموعات!**

أنا هنا لمساعدتك على إنشاء مجموعات تيليجرام بكل سهولة وسرعة.

**ماذا يمكنك أن تفعل؟**
- **إضافة حسابات:** قم بإضافة حسابات تيليجرام التي تريد استخدامها.
- **بدء الإنشاء:** ابدأ عملية إنشاء المجموعات بضغطة زر.
- **إدارة حساباتك:** عرض وإدارة جميع حساباتك المضافة.

**استمتع بتجربة سلسة ومميزة!** ✨
"""
    await update.message.reply_html(
        welcome_message,
        reply_markup=get_main_menu_keyboard(),
    )

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text="القائمة الرئيسية:", reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END


async def disclaimer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the disclaimer button."""
    query = update.callback_query
    await query.answer()
    disclaimer_text = """
⚖️ **إخلاء مسؤولية** ⚖️

- هذا البوت هو أداة لمساعدتك في إنشاء المجموعات بشكل آلي.
- استخدامك للبوت على مسؤوليتك الشخصية.
- قد يؤدي إنشاء عدد كبير من المجموعات في فترة قصيرة إلى تقييد أو حظر حسابك من قبل تيليجرام.
- نحن لا نتحمل أي مسؤولية عن أي ضرر أو حظر قد يلحق بحساباتك.

**نصائح لتجنب الحظر:**
- لا تقم بإنشاء عدد كبير جداً من المجموعات في اليوم الواحد.
- قم بضبط فترة زمنية كافية بين إنشاء كل مجموعة.

**المطور:** @urrrrn
"""
    await query.edit_message_text(
        text=disclaimer_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 عودة للرئيسية", callback_data='back_to_main')]]),
        parse_mode='Markdown'
    )

async def show_groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the list of groups created by the user."""
    query = update.callback_query
    await query.answer()
    groups = get_user_groups(update.effective_user.id)
    if not groups:
        await query.edit_message_text(
            text="لم تقم بإنشاء أي مجموعات بعد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 عودة للرئيسية", callback_data='back_to_main')]])
        )
        return

    message = "**📂 قائمة المجموعات التي تم إنشاؤها:**\n\n"
    for name, link in groups:
        message += f"- [{name}]({link})\n"

    await query.edit_message_text(
        text=message,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 عودة للرئيسية", callback_data='back_to_main')]]),
        parse_mode='Markdown',
        disable_web_page_preview=True
    )


# --- Account Management ---
async def my_accounts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    accounts = get_user_accounts(update.effective_user.id)
    if not accounts:
        await query.edit_message_text(
            text="لم تقم بإضافة أي حسابات بعد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 عودة للرئيسية", callback_data='back_to_main')]])
        )
        return

    keyboard = []
    for phone, status in accounts:
        status_emoji = "✅" if status == 'active' else "⏸️"
        toggle_text = "إيقاف" if status == 'active' else "تنشيط"
        row = [
            InlineKeyboardButton(f"{status_emoji} {phone}", callback_data=f"info:{phone}"),
            InlineKeyboardButton(toggle_text, callback_data=f"toggle_status:{phone}:{status}"),
            InlineKeyboardButton("🗑️", callback_data=f"{DELETE_ACCOUNT}:{phone}")
        ]
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("🔙 عودة للرئيسية", callback_data='back_to_main')])
    await query.edit_message_text(
        text="**🗂️ قائمة حساباتك:**\n\n- ✅: نشط\n- ⏸️: موقوف\n- 🚫: محظور",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def delete_account_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    phone_number = query.data.split(':')[1]
    delete_account(phone_number)
    session_file = f"{phone_number}.session"
    if os.path.exists(session_file):
        os.remove(session_file)
    await query.edit_message_text(text=f"تم حذف الحساب {phone_number} بنجاح.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("عودة إلى الحسابات", callback_data=MY_ACCOUNTS)]]))

async def toggle_account_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggles the account status between active and paused."""
    query = update.callback_query
    await query.answer()
    _, phone, current_status = query.data.split(':')
    new_status = 'paused' if current_status == 'active' else 'active'
    update_account_status(phone, new_status)

    # Refresh the accounts list
    await my_accounts_handler(update, context)

# --- Add Account Conversation Functions ---
async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation to add a new account."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="أرسل رقم الهاتف مع رمز الدولة (مثال: +1234567890).")
    return ASK_PHONE

async def ask_code(update, context):
    context.user_data['phone'] = update.message.text
    await update.message.reply_text("جاري محاولة تسجيل الدخول...")
    client, error = await telethon_handler.start_client_login(API_ID, API_HASH, context.user_data['phone'])
    if error:
        await update.message.reply_text(f"حدث خطأ: {error}\n\nالرجاء المحاولة مرة أخرى.")
        return ConversationHandler.END
    context.user_data['client'] = client
    await update.message.reply_text("تم إرسال رمز التحقق إلى حسابك في تيليجرام. الرجاء إرساله هنا.")
    return ASK_CODE
async def ask_2fa(update, context):
    result, error = await telethon_handler.submit_login_code(context.user_data['client'], context.user_data['phone'], update.message.text)
    if result == "SUCCESS":
        add_account(update.effective_user.id, context.user_data['phone'])
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
        add_account(update.effective_user.id, context.user_data['phone'])
        await update.message.reply_text("تم تسجيل الدخول بنجاح! تم حفظ الحساب.")
    else:
        await update.message.reply_text(f"حدث خطأ: {error}\n\nالرجاء المحاولة مرة أخرى.")
    await context.user_data['client'].disconnect()
    return ConversationHandler.END
async def cancel_add_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('تم إلغاء العملية.', reply_markup=get_main_menu_keyboard())
    return ConversationHandler.END

# --- Add Account Conversation Handler ---
add_account_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(add_account_start, pattern='^' + ADD_ACCOUNT + '$')],
    states={
        ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_code)],
        ASK_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_2fa)],
        ASK_2FA_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_with_2fa)],
    },
    fallbacks=[CommandHandler('cancel', cancel_add_account)],
)


# --- Create Groups Conversation ---
async def start_creation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    accounts = get_user_accounts(update.effective_user.id)
    active_accounts = [acc for acc in accounts if acc[1] == 'active']

    if not active_accounts:
        await query.edit_message_text(
            text="*ليس لديك حسابات نشطة!*\n\nقم بتنشيط حساب واحد على الأقل لبدء الإنشاء.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 عودة للرئيسية", callback_data='back_to_main')]]),
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(acc[0], callback_data=f"{CHOOSE_ACCOUNT_FOR_CREATION}:{acc[0]}")] for acc in active_accounts]
    keyboard.append([InlineKeyboardButton("🔙 عودة للرئيسية", callback_data='cancel_creation')])
    await query.edit_message_text(
        text="**🚀 اختر الحساب النشط الذي تريد استخدامه:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SELECT_ACCOUNT_FOR_CREATION

async def ask_group_count_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    phone = query.data.split(':')[1]
    context.user_data['selected_phone'] = phone

    groups_today = get_groups_created_today(phone)
    total_groups = get_total_groups_by_phone(phone)
    remaining_today = MAX_GROUPS_PER_DAY - groups_today

    if remaining_today <= 0:
        await query.edit_message_text(
            text=f"لقد وصلت إلى الحد الأقصى لإنشاء المجموعات لهذا الحساب اليوم ({MAX_GROUPS_PER_DAY} مجموعة).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 عودة للرئيسية", callback_data='back_to_main')]])
        )
        return ConversationHandler.END

    message = f"""
**📊 حالة إنشاء المجموعات:**

- **إجمالي المجموعات المنشأة:** `{total_groups}`
- **المجموعات المنشأة اليوم:** `{groups_today}`
- **المتبقي لهذا اليوم:** `{remaining_today}`

*أرسل عدد المجموعات التي تريد إنشاءها الآن:*
"""
    await query.edit_message_text(text=message, parse_mode='Markdown')
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

    # --- Live Update Message ---
    status_message = await update.message.reply_text("جاري التحضير...", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 إيقاف الإنشاء", callback_data='stop_creation')]]))
    context.user_data['status_message_id'] = status_message.message_id
    context.user_data['stop_creation'] = False

    client = TelegramClient(f"{phone}.session", API_ID, API_HASH)
    # Define the 5 welcome messages
    messages_to_send = [
        "✨ أهلًا وسهلًا بكم في مجموعتنا! نتمنى لكم وقتًا ممتعًا ومفيدًا. ✨",
        "🎉 مرحبًا بالجميع! يسعدنا انضمامكم إلينا.",
        "👋 تحية طيبة! هذه المجموعة هي مساحتكم للتواصل والنقاش.",
        "🚀 انطلقنا! مرحبًا بكم على متن مجموعتنا الجديدة.",
        "💬 بداية جديدة! شاركونا أفكاركم وآراءكم. أهلًا بكم."
    ]

    try:
        await client.connect()
        if not await client.is_user_authorized():
            await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_message.message_id, text="فشل تسجيل الدخول. يرجى حذف الحساب وإضافته مرة أخرى.", reply_markup=get_main_menu_keyboard())
            return ConversationHandler.END

        # Get the total number of groups the USER has created so far as a starting point.
        initial_user_groups = get_total_groups_by_user(update.effective_user.id)

        for i in range(count):
            if context.user_data.get('stop_creation'):
                await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_message.message_id, text="تم إيقاف الإنشاء بناءً على طلبك.", reply_markup=get_main_menu_keyboard())
                return ConversationHandler.END

            # Calculate the correct group number and name based on user's total groups
            group_num = initial_user_groups + i + 1
            current_date = datetime.now().strftime("%Y-%m-%d")
            group_name = f"Group {group_num} {current_date}"

            # Get the number of groups created *today* by the *phone* for the status message
            groups_created_so_far_today = get_groups_created_today(phone)

            # Update status message
            status_text = f"""
**🚀 جاري إنشاء المجموعات...**

- **الحساب:** `{phone}`
- **حالة الحساب:** `نشط` ✅
- **التقدم:** `{i + 1}/{count}`
- **المجموعات اليوم:** `{groups_created_so_far_today}`
- **جاري إنشاء:** `{group_name}`
"""
            await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_message.message_id, text=status_text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 إيقاف الإنشاء", callback_data='stop_creation')]]))

            result, error = await telethon_handler.create_group(client, group_name, messages_to_send)

            if error:
                if isinstance(error, FloodWaitError):
                    ban_duration = error.seconds
                    ban_expires_at = datetime.now() + timedelta(seconds=ban_duration)
                    update_account_ban_status(phone, ban_expires_at)
                    await update.message.reply_text(f"تم حظر الحساب {phone} مؤقتًا لمدة {ban_duration} ثانية.")
                    break
                else:
                    await update.message.reply_text(f"فشل إنشاء المجموعة {group_name}. الخطأ: {str(error)}")
                    await asyncio.sleep(5)
                    continue

            increment_groups_created(phone)
            add_group(update.effective_user.id, result['id'], result['name'], result['link'], phone)
            # Log success separately
            await update.message.reply_text(f"✅ تم إنشاء المجموعة [{group_name}]({result['link']}) بنجاح.", parse_mode='Markdown')

            await asyncio.sleep(GROUP_CREATION_INTERVAL)

    except Exception as e:
        logger.error(f"Error during group creation: {e}")
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_message.message_id, text=f"حدث خطأ فادح: {e}", reply_markup=get_main_menu_keyboard())
    finally:
        if client.is_connected():
            await client.disconnect()

    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_message.message_id, text="🎉 اكتملت عملية إنشاء جميع المجموعات!", reply_markup=get_main_menu_keyboard())
    return ConversationHandler.END

async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="تم إلغاء عملية الإنشاء.", reply_markup=get_main_menu_keyboard())
    return ConversationHandler.END

async def stop_creation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sets a flag to stop the group creation loop."""
    query = update.callback_query
    await query.answer("سيتم إيقاف الإنشاء بعد المجموعة الحالية...")
    context.user_data['stop_creation'] = True


# --- Main Application Setup ---
def main() -> None:
    if 'YOUR_BOT_TOKEN' in BOT_TOKEN or 'YOUR_API_ID' in API_ID:
        logger.error("Please fill in your bot_token, api_id, and api_hash in config.ini")
        return

    initialize_database()
    application = Application.builder().token(BOT_TOKEN).build()

    create_groups_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_creation_handler, pattern='^' + START_CREATION + '$')],
        states={
            SELECT_ACCOUNT_FOR_CREATION: [CallbackQueryHandler(ask_group_count_handler, pattern=f'^{CHOOSE_ACCOUNT_FOR_CREATION}:.*$')],
            ASK_GROUP_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_groups_handler),
                CallbackQueryHandler(stop_creation_handler, pattern='^stop_creation$')
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_creation, pattern='^cancel_creation$')],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(add_account_conv)
    application.add_handler(create_groups_conv)
    application.add_handler(CallbackQueryHandler(my_accounts_handler, pattern='^' + MY_ACCOUNTS + '$'))
    application.add_handler(CallbackQueryHandler(delete_account_handler, pattern=f'^{DELETE_ACCOUNT}:.*$'))
    application.add_handler(CallbackQueryHandler(toggle_account_status_handler, pattern='^toggle_status:.*$'))
    application.add_handler(CallbackQueryHandler(show_groups_handler, pattern='^show_groups$'))
    application.add_handler(CallbackQueryHandler(disclaimer_handler, pattern='^disclaimer$'))
    application.add_handler(CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main$'))

    application.run_polling()

if __name__ == '__main__':
    main()
