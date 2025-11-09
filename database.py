import sqlite3
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_NAME = "telegram_bot.db"

def get_db_connection():
    """Creates a database connection."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """Initializes the database and creates tables if they don't exist."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Table for users and their admin status
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            is_admin BOOLEAN NOT NULL DEFAULT 0
        )
        """)
        logger.info("Table 'users' created or already exists.")

        # Table for user-added accounts (phone numbers and session strings)
        # One user can have multiple accounts.
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            phone_number TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            session_string TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        )
        """)
        logger.info("Table 'accounts' created or already exists.")

        # Table for reserved channels/usernames
        # Linked to the account that reserved it.
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS reserved_channels (
            channel_username TEXT PRIMARY KEY,
            reserved_by_phone TEXT NOT NULL,
            reservation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reserved_by_phone) REFERENCES accounts (phone_number) ON DELETE CASCADE
        )
        """)
        logger.info("Table 'reserved_channels' created or already exists.")

        conn.commit()
        logger.info("Database initialized successfully.")

    except sqlite3.Error as e:
        logger.error(f"Database error during initialization: {e}")
    finally:
        if conn:
            conn.close()

def add_user_if_not_exists(user_id):
    """Adds a new user to the database if they don't already exist."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error while adding user {user_id}: {e}")
    finally:
        if conn:
            conn.close()

def get_user_accounts(user_id):
    """Fetches all accounts associated with a user_id."""
    accounts = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT phone_number FROM accounts WHERE user_id = ?", (user_id,))
        accounts = [row['phone_number'] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Database error while fetching accounts for user {user_id}: {e}")
    finally:
        if conn:
            conn.close()
    return accounts

def delete_account(phone_number):
    """Deletes an account from the database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM accounts WHERE phone_number = ?", (phone_number,))
        conn.commit()
        logger.info(f"Successfully deleted account {phone_number}")
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error while deleting account {phone_number}: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_session_string(phone_number):
    """Retrieves the session string for a given phone number."""
    session_string = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT session_string FROM accounts WHERE phone_number = ?", (phone_number,))
        row = cursor.fetchone()
        if row:
            session_string = row['session_string']
    except sqlite3.Error as e:
        logger.error(f"Database error while fetching session for {phone_number}: {e}")
    finally:
        if conn:
            conn.close()
    return session_string

def save_reserved_channel(channel_username, phone_number):
    """Saves a newly reserved channel to the database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO reserved_channels (channel_username, reserved_by_phone) VALUES (?, ?)",
            (channel_username, phone_number)
        )
        conn.commit()
        logger.info(f"Saved reserved channel @{channel_username} for {phone_number}")
    except sqlite3.Error as e:
        logger.error(f"Database error while saving channel @{channel_username}: {e}")
    finally:
        if conn:
            conn.close()

def get_reserved_channels_by_phone(phone_number):
    """Fetches all reserved channels for a specific phone number."""
    channels = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT channel_username FROM reserved_channels WHERE reserved_by_phone = ?", (phone_number,))
        channels = [row['channel_username'] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Database error while fetching reserved channels for {phone_number}: {e}")
    finally:
        if conn:
            conn.close()
    return channels

def set_admin_status(user_id, is_admin):
    """Sets the admin status for a user."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Ensure user exists before updating
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        cursor.execute("UPDATE users SET is_admin = ? WHERE user_id = ?", (is_admin, user_id))
        conn.commit()
        logger.info(f"Set admin status for user {user_id} to {is_admin}")
    except sqlite3.Error as e:
        logger.error(f"Database error setting admin status for {user_id}: {e}")
    finally:
        if conn:
            conn.close()

def get_admins():
    """Gets a list of all admin user IDs."""
    admins = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE is_admin = 1")
        admins = [row['user_id'] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Database error fetching admins: {e}")
    finally:
        if conn:
            conn.close()
    return admins

def save_account(user_id, phone_number, session_string):
    """Saves or updates an account in the database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO accounts (phone_number, user_id, session_string) VALUES (?, ?, ?)",
            (phone_number, user_id, session_string)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error saving account for user {user_id}: {e}")
        return False
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    # This allows running the script directly to initialize the database
    print("Initializing database...")
    initialize_database()
    print("Database initialization complete.")
