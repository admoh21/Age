import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

logger = logging.getLogger(__name__)

async def connect_and_send_code(api_id, api_hash, phone_number):
    """
    Connects to Telegram, sends a login code, and returns the client and phone_code_hash.
    """
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()

    try:
        sent_code = await client.send_code_request(phone_number)
        return client, sent_code.phone_code_hash
    except Exception as e:
        logger.error(f"Failed to send code for {phone_number}: {e}")
        await client.disconnect()
        return None, None

async def sign_in_with_code(client, phone_number, phone_code, phone_code_hash):
    """
    Tries to sign in using the provided code.
    Returns the user if successful, raises SessionPasswordNeededError if 2FA is needed.
    """
    try:
        user = await client.sign_in(phone_number, code=phone_code, phone_code_hash=phone_code_hash)
        return user
    except SessionPasswordNeededError:
        # Re-raise the exception to be handled by the conversation flow
        raise
    except Exception as e:
        logger.error(f"Failed to sign in with code for {phone_number}: {e}")
        return None

import asyncio
from telethon.errors import FloodWaitError, UsernameInvalidError
from telethon.tl.functions.channels import CheckUsernameRequest, CreateChannelRequest, UpdateUsernameRequest


async def sign_in_with_password(client, password):
    """
    Signs in using the 2FA password.
    """
    try:
        user = await client.sign_in(password=password)
        return user
    except Exception as e:
        logger.error(f"Failed to sign in with password: {e}")
        return None

async def check_username_availability(client, username):
    """
    Safely checks if a username is available using channels.CheckUsernameRequest.
    Returns ('available', None), ('occupied', None), ('invalid', None), or ('flood', wait_seconds).
    """
    try:
        # This is the correct, safe method to check a username.
        # It checks the username for a channel, which is what we want.
        # A result of True means the username is available.
        result = await client(CheckUsernameRequest(username=username))
        if result:
            return 'available', None
        else:
            # This 'else' case is ambiguous; it could be taken or invalid.
            # We rely on specific error handling for clarity.
            return 'occupied', None

    except UsernameInvalidError:
        logger.warning(f"Username '{username}' is invalid according to Telegram and will be skipped.")
        return 'invalid', None

    except FloodWaitError as e:
        logger.warning(f"Flood wait error when checking {username}: waiting {e.seconds} seconds.")
        return 'flood', e.seconds

    except Exception as e:
        # A generic error usually implies the username is taken or there's a connection issue.
        # We'll log it and treat it as 'occupied' to be safe.
        logger.error(f"An error of type {type(e).__name__} occurred for '{username}': {e}")
        return 'occupied', None

async def create_channel_and_set_username(client, username):
    """
    Creates a new public channel and sets its username.
    Returns True if successful, False otherwise.
    """
    try:
        # 1. Create a new channel
        channel_title = f"Reserved-{username}"
        created_channel = await client(CreateChannelRequest(
            title=channel_title,
            about="Reserved via bot.",
            megagroup=False
        ))
        channel_entity = created_channel.chats[0]

        # 2. Set the username for the new channel
        await client(UpdateUsernameRequest(
            channel=channel_entity.id,
            username=username
        ))
        logger.info(f"Successfully created channel and set username: @{username}")
        return True
    except Exception as e:
        logger.error(f"Failed to create channel or set username for @{username}: {e}")
        return False
