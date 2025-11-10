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

async def create_group(client, group_name):
    """Creates a group, sends 5 messages, and converts it to a supergroup."""
    try:
        # 1. Create the group
        created_chat = await client(CreateChatRequest(
            users=["me"],  # You can add other users here if you want
            title=group_name
        ))
        chat_id = created_chat.chats[0].id

        # 2. Send 5 messages
        for i in range(5):
            await client(SendMessageRequest(
                peer=chat_id,
                message=f"رسالة تلقائية {i+1}"
            ))
            await asyncio.sleep(1) # Small delay between messages

        # 3. Convert to supergroup
        await client(ConvertToGigagroupRequest(channel_id=chat_id))

        return "SUCCESS", None
    except Exception as e:
        return None, str(e)
