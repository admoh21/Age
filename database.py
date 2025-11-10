# database.py

import sqlite3
from datetime import datetime

DB_NAME = "bot_database.db"

def initialize_database():
    """Initializes the database and creates tables if they don't exist."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Table for bot users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT
        )
    ''')

    # Table for telegram accounts added by users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            phone_number TEXT PRIMARY KEY,
            user_id INTEGER,
            api_id INTEGER,
            api_hash TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Table to track group creation stats
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS group_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT,
            groups_created INTEGER DEFAULT 0,
            date TEXT,
            UNIQUE(phone_number, date)
        )
    ''')

    conn.commit()
    conn.close()

def add_user(user_id, first_name):
    """Adds a new user to the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)", (user_id, first_name))
    conn.commit()
    conn.close()

def add_account(user_id, phone_number, api_id, api_hash):
    """Adds a new account to the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO accounts (user_id, phone_number, api_id, api_hash) VALUES (?, ?, ?, ?)",
                   (user_id, phone_number, api_id, api_hash))
    conn.commit()
    conn.close()

def get_user_accounts(user_id):
    """Gets all accounts for a given user."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT phone_number FROM accounts WHERE user_id = ?", (user_id,))
    accounts = cursor.fetchall()
    conn.close()
    return [acc[0] for acc in accounts]

def get_account_details(phone_number):
    """Gets the api_id and api_hash for a given account."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT api_id, api_hash FROM accounts WHERE phone_number = ?", (phone_number,))
    details = cursor.fetchone()
    conn.close()
    return details # (api_id, api_hash)


def delete_account(phone_number):
    """Deletes an account from the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM accounts WHERE phone_number = ?", (phone_number,))
    cursor.execute("DELETE FROM group_stats WHERE phone_number = ?", (phone_number,))
    conn.commit()
    conn.close()

def get_groups_created_today(phone_number):
    """Gets the number of groups created today for a given account."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT groups_created FROM group_stats WHERE phone_number = ? AND date = ?", (phone_number, today))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def increment_groups_created(phone_number):
    """Increments the number of groups created today for a given account."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO group_stats (phone_number, date) VALUES (?, ?)", (phone_number, today))
    cursor.execute("UPDATE group_stats SET groups_created = groups_created + 1 WHERE phone_number = ? AND date = ?", (phone_number, today))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    initialize_database()
    print("Database initialized successfully.")
