import subprocess
import sysimport
import logging
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# Install required packages
def install_packages():
    required_packages = [
        "python-telegram-bot==20.0",
        "typing-extensions",
        "exceptiongroup"
    ]

    for package in required_packages:
        , "-m", "pip", "install", package])

# Run thesubprocess.check_call([sys.executable installation of packages
install_packages()

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Define the bot token and owner ID
TOKEN = int(os.getenv('TOKEN','7449574557:AAGcg6zL-hEVr7byvkVvCAIJPfBYtY-A8BQ'))  # Ensure your TOKEN is set in environment variables or Replit secrets
OWNER_ID = int(os.getenv('OWNER_ID', '1696305024'))  # Replace with your actual owner ID

# Store user data
waiting_users = []
active_chats = {}
last_partner = {}  # Store the last partner for each user
rematch_requests = {}  # Store rematch requests
user_ids = set()  # Set to store unique user IDs

# Save user IDs and usernames to files
async def save_user_data(context: ContextTypes.DEFAULT_TYPE) -> None:
    with open('user_ids.txt', 'w') as file:
        for user_id in user_ids:
            file.write(f"{user_id}\n")

    with open('usernames.txt', 'w') as file:
        for user_id in user_ids:
            try:
                chat = await context.bot.get_chat(user_id)
                if chat.username:
                    file.write(f"{user_id}: {chat.username}\n")
            except Exception as e:
                logging.error(f"Error retrieving username for {user_id}: {e}")

# Log message conversation
def log_conversation(user1_id: int, user2_id: int, message: str) -> None:
    filename = 'conversations.txt'
    with open(filename, 'a') as file:
        file.write(f"User {user1_id} and User {user2_id}: {message}\n")

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.chat_id

    # Add user ID to the set and save
    user_ids.add(user_id)
    await save_user_data(context)

    if user_id in active_chats:
        await update.message.reply_text('You are already in a chat. Use /skip to find a new partner or /stop to leave the chat.')
        return

    if user_id in waiting_users:
        await update.message.reply_text('You are already waiting for a chat partner.')
        return

    if waiting_users:
        # Match with a waiting user
        partner_id = waiting_users.pop(0)
        active_chats[user_id] = partner_id
        active_chats[partner_id] = user_id
        await update.message.reply_text(
            'You have been connected to a new chat! Use the following commands:\n'
            '/stop - Stop your current chat\n'
            '/skip - Skip to a new chat\n'
            '/rematch - Request a rematch with your last partner\n'
            '/share_usernames - Share your profile link\n'
            '\nFor help, contact @Vi5h4u'
        )
        await context.bot.send_message(
            chat_id=partner_id,
            text='You have been connected to a new chat! Use the following commands:\n'
                 '/stop - Stop your current chat\n'
                 '/skip - Skip to a new chat\n'
                 '/rematch - Request a rematch with your last partner\n'
                 '/share_usernames - Share your profile link\n'
                 '\nFor help, contact @Vi5h4u'
        )
    else:
        # No users waiting, add to waiting list
        waiting_users.append(user_id)
        await update.message.reply_text(
            'You are now waiting for a chat partner. Use the following commands:\n'
            '/stop - Stop your current chat\n'
            '/skip - Skip to a new chat\n'
            '/rematch - Request a rematch with your last partner\n'
            '/share_usernames - Share your profile link\n'
            '\nFor help, contact @Vi5h4u'
        )

# Stop command
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.chat_id

    if user_id in active_chats:
        # Notify partner and disconnect
        partner_id = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)
        await context.bot.send_message(chat_id=partner_id, text='Your chat partner has left the chat.')
        await update.message.reply_text('You have left the chat.')
    elif user_id in waiting_users:
        waiting_users.remove(user_id)
        await update.message.reply_text('You are no longer waiting for a chat partner.')
    else:
        await update.message.reply_text('You are not connected to any chat.')

# Skip command
async def skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.chat_id

    if user_id in active_chats:
        # Notify partner and disconnect
        partner_id = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)
        last_partner[user_id] = partner_id
        last_partner[partner_id] = user_id
        await context.bot.send_message(chat_id=partner_id, text='Your chat partner has skipped to a new chat.')
        await update.message.reply_text('You have skipped to a new chat.')

        # Try to connect to a new chat
        if not waiting_users:
            # If there are no users waiting, re-add the current user to the waiting list
            waiting_users.append(user_id)
            await update.message.reply_text('No new chat partner is available at the moment. Please wait for someone to start a chat.')
        else:
            # Proceed with the matching process
            await start(update, context)
    elif user_id in waiting_users:
        await update.message.reply_text('You are already waiting for a new chat.')
    else:
        await update.message.reply_text('You are not in a chat. Use /start to connect.')

# Rematch command
async def rematch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.chat_id

    if user_id not in last_partner:
        await update.message.reply_text('You have not skipped any chats recently. Use /start to connect with a new partner.')
        return

    partner_id = last_partner[user_id]

    if partner_id not in rematch_requests:
        # Record rematch request
        rematch_requests[user_id] = True
        await update.message.reply_text('Rematch request sent. Waiting for your partner to confirm.')
        await context.bot.send_message(chat_id=partner_id, text='Your last partner has requested a rematch. Use /rematch to reconnect.')
    elif rematch_requests.get(partner_id):
        # Both users want a rematch
        rematch_requests.pop(partner_id, None)
        last_partner.pop(user_id, None)
        last_partner.pop(partner_id, None)
        active_chats[user_id] = partner_id
        active_chats[partner_id] = user_id
        await update.message.reply_text('You have been rematched with your last partner!')
        await context.bot.send_message(chat_id=partner_id, text='You have been rematched with your last partner!')
    else:
        await update.message.reply_text('Rematch request already sent. Waiting for your partner to confirm.')

# Share Usernames command
async def share_usernames(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.chat_id
    if user_id in active_chats:
        chat = await context.bot.get_chat(user_id)
        user_link = f"https://t.me/{chat.username}" if chat.username else "Username not found"
        exchange_message = f"Your profile link: {user_link}"
        await update.message.reply_text(exchange_message, parse_mode='Markdown')
    else:
        await update.message.reply_text('You are not in a chat. Use /start to connect.')

# Command to get the list of all usernames
async def get_usernames(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.chat_id == OWNER_ID:
        if os.path.exists('usernames.txt'):
            with open('usernames.txt', 'r') as file:
                content = file.read()
                await update.message.reply_text(f"Usernames:\n{content}")
        else:
            await update.message.reply_text('No usernames found.')
    else:
        await update.message.reply_text('You are not authorized to access this command.')

# Handle all text messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.chat_id
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        message = update.message.text
        # Log conversation
        log_conversation(user_id, partner_id, message)
        # Forward message to the partner
        await context.bot.send_message(chat_id=partner_id, text=message)
    else:
        await update.message.reply_text('You are not in a chat. Use /start to connect.')

# Function to run the bot
def main() -> None:
    application = ApplicationBuilder().token(TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('stop', stop))
    application.add_handler(CommandHandler('skip', skip))
    application.add_handler(CommandHandler('rematch', rematch))
    application.add_handler(CommandHandler('share_usernames', share_usernames))
    application.add_handler(CommandHandler('get_usernames', get_usernames))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the bot
    application.run_polling()

if __name__ == '__main__':
    main()
    

