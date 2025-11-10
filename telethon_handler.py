# telethon_handler.py

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.messages import CreateChatRequest, ExportChatInviteRequest, SendMessageRequest
from telethon.tl.functions.channels import ConvertToGigagroupRequest
import asyncio

async def start_client_login(api_id, api_hash, phone_number):
    """
    Starts the Telethon client and handles the interactive login process.
    Returns the client object if login is successful, otherwise returns an error message.
    """
    client = TelegramClient(f"{phone_number}.session", api_id, api_hash)

    try:
        await client.connect()

        if not await client.is_user_authorized():
            await client.send_code_request(phone_number)
            # We will handle code and password input in the bot conversation

        return client, None

    except Exception as e:
        return None, str(e)

async def submit_login_code(client, phone_number, code):
    """Submits the login code."""
    try:
        await client.sign_in(phone_number, code)
        return "SUCCESS", None
    except SessionPasswordNeededError:
        return "2FA_NEEDED", None
    except Exception as e:
        return None, str(e)

async def submit_2fa_password(client, password):
    """Submits the 2FA password."""
    try:
        await client.sign_in(password=password)
        return "SUCCESS", None
    except Exception as e:
        return None, str(e)

async def create_group(client, group_name, messages):
    """Creates a group, sends specified messages, and returns the group info."""
    try:
        # 1. Create the group
        result = await client(CreateChatRequest(users=['me'], title=group_name))

        # 2. Robustly find the chat ID from the response
        chat = None
        if hasattr(result, 'chats') and result.chats:
            chat = result.chats[0]
        else:
            # Fallback for different response structures, sometimes it's in 'updates'
            for update in getattr(result, 'updates', []):
                if hasattr(update, 'channel_id'):
                    chat_entity = await client.get_entity(update.channel_id)
                    chat = chat_entity
                    break

        if not chat:
            raise Exception("Could not find chat information in the response.")

        chat_id = chat.id

        # 3. Send messages
        for message in messages:
            await client.send_message(chat_id, message)
            await asyncio.sleep(1)

        # 4. Get invite link
        invite = await client(ExportChatInviteRequest(peer=chat_id))

        return {"status": "SUCCESS", "id": chat_id, "name": group_name, "link": invite.link}, None

    except Exception as e:
        # Return the actual exception object instead of its string representation
        return None, e
