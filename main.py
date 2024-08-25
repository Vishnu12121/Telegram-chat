import os
import logging
import sqlite3
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# Flask app setup
app = Flask(__name__)

# Telegram bot setup
TOKEN = os.getenv('TOKEN')
bot = Bot(TOKEN)
app_bot = ApplicationBuilder().token(TOKEN).build()

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Initialize database
def init_db():
    conn = sqlite3.connect('chatbot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            last_message TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ActiveChats (
            user1_id INTEGER,
            user2_id INTEGER,
            chat_state TEXT,
            PRIMARY KEY (user1_id, user2_id)
        )
    ''')
    conn.commit()
    conn.close()

# Flask route for webhook
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    json_str = request.get_data(as_text=True)
    update = Update.de_json(json_str, bot)
    app_bot.process_update(update)
    return 'OK'

# Define global variables and functions
waiting_users = []
active_chats = {}
last_partner = {}  # Store the last partner for each user
rematch_requests = {}  # Store rematch requests
user_ids = set()  # Set to store unique user IDs

def get_db_connection():
    conn = sqlite3.connect('chatbot.db')
    conn.row_factory = sqlite3.Row
    return conn

async def save_user_data(context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM Users')  # Clear existing data
    
    for user_id in user_ids:
        try:
            chat = await context.bot.get_chat(user_id)
            username = chat.username or "Unknown"
            cursor.execute('''
                INSERT OR REPLACE INTO Users (id, username, last_message)
                VALUES (?, ?, ?)
            ''', (user_id, username, ''))
        except Exception as e:
            logging.error(f"Error retrieving username for {user_id}: {e}")
    
    conn.commit()
    conn.close()

def log_conversation(user1_id: int, user2_id: int, message: str) -> None:
    filename = 'conversations.txt'
    with open(filename, 'a') as file:
        file.write(f"User {user1_id} and User {user2_id}: {message}\n")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.chat_id

    # Add user ID to the set and save
    global user_ids
    user_ids.add(user_id)
    await save_user_data(context)

    conn = get_db_connection()
    cursor = conn.cursor()

    if user_id in active_chats:
        await update.message.reply_text('You are already in a chat. Use /skip to find a new partner or /stop to leave the chat.')
        conn.close()
        return

    if user_id in waiting_users:
        await update.message.reply_text('You are already waiting for a chat partner.')
        conn.close()
        return

    if waiting_users:
        partner_id = waiting_users.pop(0)
        active_chats[user_id] = partner_id
        active_chats[partner_id] = user_id
        cursor.execute('''
            INSERT OR REPLACE INTO ActiveChats (user1_id, user2_id, chat_state)
            VALUES (?, ?, ?)
        ''', (user_id, partner_id, 'active'))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            'You have been connected to a new chat! Use the following commands:\n'
            '/stop - Stop your current chat\n'
            '/skip - Skip to a new chat\n'
            '/rematch - Request a rematch with your last partner\n'
            '/share_usernames - Share your profile link\n'
        )
        await context.bot.send_message(
            chat_id=partner_id,
            text='You have been connected to a new chat! Use the following commands:\n'
                 '/stop - Stop your current chat\n'
                 '/skip - Skip to a new chat\n'
                 '/rematch - Request a rematch with your last partner\n'
                 '/share_usernames - Share your profile link\n'
        )
    else:
        waiting_users.append(user_id)
        await update.message.reply_text(
            'You are now waiting for a chat partner. Use the following commands:\n'
            '/stop - Stop your current chat\n'
            '/skip - Skip to a new chat\n'
            '/rematch - Request a rematch with your last partner\n'
            '/share_usernames - Share your profile link\n'
        )
    conn.close()

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.chat_id

    conn = get_db_connection()
    cursor = conn.cursor()

    if user_id in active_chats:
        partner_id = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)
        cursor.execute('DELETE FROM ActiveChats WHERE (user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?)',
                       (user_id, partner_id, partner_id, user_id))
        conn.commit()

        await context.bot.send_message(chat_id=partner_id, text='Your chat partner has left the chat. You can use /rematch to reconnect or /start to find a new partner.')
        
        if partner_id in rematch_requests and rematch_requests[partner_id]:
            last_partner[user_id] = partner_id
            last_partner[partner_id] = user_id
            rematch_requests.pop(partner_id, None)
            active_chats[user_id] = partner_id
            active_chats[partner_id] = user_id
            cursor.execute('''
                INSERT OR REPLACE INTO ActiveChats (user1_id, user2_id, chat_state)
                VALUES (?, ?, ?)
            ''', (user_id, partner_id, 'active'))
            conn.commit()
            await update.message.reply_text('You have been rematched with your last partner!')
            await context.bot.send_message(chat_id=partner_id, text='You have been rematched with your last partner!')
        else:
            await update.message.reply_text('You have left the chat. Use /start to find a new partner.')

        conn.close()
    elif user_id in waiting_users:
        waiting_users.remove(user_id)
        conn.close()
        await update.message.reply_text('You are no longer waiting for a chat partner.')
    else:
        conn.close()
        await update.message.reply_text('You are not connected to any chat.')

async def skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.chat_id

    conn = get_db_connection()
    cursor = conn.cursor()

    if user_id in active_chats:
        partner_id = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)
        last_partner[user_id] = partner_id
        last_partner[partner_id] = user_id
        cursor.execute('DELETE FROM ActiveChats WHERE (user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?)',
                       (user_id, partner_id, partner_id, user_id))
        conn.commit()

        await context.bot.send_message(chat_id=partner_id, text='Your chat partner has skipped to a new chat. You can use /rematch to reconnect or /start to find a new partner.')
        
        if partner_id in rematch_requests and rematch_requests[partner_id]:
            rematch_requests.pop(partner_id, None)
            active_chats[user_id] = partner_id
            active_chats[partner_id] = user_id
            cursor.execute('''
                INSERT OR REPLACE INTO ActiveChats (user1_id, user2_id, chat_state)
                VALUES (?, ?, ?)
            ''', (user_id, partner_id, 'active'))
            conn.commit()
            await update.message.reply_text('You have been rematched with your last partner!')
            await context.bot.send_message(chat_id=partner_id, text='You have been rematched with your last partner!')
        else:
            if not waiting_users:
                waiting_users.append(user_id)
                await update.message.reply_text('No new chat partner is available at the moment. Please wait for someone to start a chat.')
            else:
                await start(update, context)
        conn.close()
    elif user_id in waiting_users:
        conn.close()
        await update.message.reply_text('You are already waiting for a new chat.')
    else:
        conn.close()
        await update.message.reply_text('You are not in a chat. Use /start to connect.')

async def rematch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.chat_id

    if user_id not in last_partner:
        await update.message.reply_text('You have not skipped any chats recently. Use /start to connect with a new partner.')
        return

    partner_id = last_partner[user_id]

    if partner_id not in rematch_requests:
        rematch_requests[user_id] = True
        await update.message.reply_text('Rematch request sent. Waiting for your partner to confirm.')
        await context.bot.send_message(chat_id=partner_id, text='Your partner has requested a rematch. Use /rematch to reconnect or /start to find a new partner.')
    else:
        await update.message.reply_text('A rematch request is already pending.')

async def share_usernames(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.chat_id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM Users WHERE id = ?', (user_id,))
    user_data = cursor.fetchone()
    conn.close()

    if user_data:
        username = user_data['username']
        await update.message.reply_text(f'Your username is @{username}')
    else:
        await update.message.reply_text('Unable to retrieve your username. Please try again later.')

# Add handlers to the application
app_bot.add_handler(CommandHandler('start', start))
app_bot.add_handler(CommandHandler('stop', stop))
app_bot.add_handler(CommandHandler('skip', skip))
app_bot.add_handler(CommandHandler('rematch', rematch))
app_bot.add_handler(CommandHandler('share_usernames', share_usernames))

# Set webhook
def set_webhook():
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_URL')}/{TOKEN}"
    bot.set_webhook(url=webhook_url)

# Run Flask app
if __name__ == '__main__':
    init_db()
    set_webhook()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
