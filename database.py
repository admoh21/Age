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
            status TEXT DEFAULT 'active',
            ban_expires_at TIMESTAMP,
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

    # Table to store created groups
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            group_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            group_name TEXT,
            invite_link TEXT,
            created_by_phone TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (created_by_phone) REFERENCES accounts (phone_number)
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

def add_account(user_id, phone_number):
    """Adds a new account to the database with default status."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO accounts (user_id, phone_number, status) VALUES (?, ?, 'active')",
                   (user_id, phone_number))
    conn.commit()
    conn.close()

def update_account_status(phone_number, status):
    """Updates the status of an account."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE accounts SET status = ? WHERE phone_number = ?", (status, phone_number))
    conn.commit()
    conn.close()

def update_account_ban_status(phone_number, ban_expires_at):
    """Updates the ban status of an account."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE accounts SET status = 'banned', ban_expires_at = ? WHERE phone_number = ?", (ban_expires_at, phone_number))
    conn.commit()
    conn.close()

def get_user_accounts(user_id):
    """Gets all accounts for a given user, including their status."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT phone_number, status FROM accounts WHERE user_id = ?", (user_id,))
    accounts = cursor.fetchall()
    conn.close()
    return accounts

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

def add_group(user_id, group_id, group_name, invite_link, created_by_phone):
    """Adds a newly created group to the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO groups (user_id, group_id, group_name, invite_link, created_by_phone) VALUES (?, ?, ?, ?, ?)",
                   (user_id, group_id, group_name, invite_link, created_by_phone))
    conn.commit()
    conn.close()

def get_user_groups(user_id):
    """Gets all groups created by a given user."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT group_name, invite_link FROM groups WHERE user_id = ?", (user_id,))
    groups = cursor.fetchall()
    conn.close()
    return groups

def get_total_groups_by_phone(phone_number):
    """Gets the total number of groups created by a specific phone number."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM groups WHERE created_by_phone = ?", (phone_number,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_total_groups_by_user(user_id):
    """Gets the total number of groups created by a specific user across all their accounts."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM groups WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

if __name__ == '__main__':
    initialize_database()
    print("Database initialized successfully.")
