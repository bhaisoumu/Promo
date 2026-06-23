from telethon import TelegramClient, events
from telethon.tl.types import User, Chat, Channel
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.folders import ImportFolderInviteRequest   # <-- NEW IMPORT
from telethon.errors import FloodWaitError, InviteHashInvalidError, InviteHashExpiredError
import asyncio
import time
import traceback
import re
from datetime import timedelta
from config import config
from database import database

# --- INIT ---
client = TelegramClient("session", config.API_ID, config.API_HASH)
DELAY = config.DEFAULT_DELAY
MODE = config.DEFAULT_MODE
PARALLEL_BATCH_SIZE = None
auto_broadcast_task = None

# --- LOGGING ---
async def send_log(text: str):
    """Send error/log message to the configured log group (if set)."""
    if config.LOG_GROUP_ID and config.LOG_GROUP_ID != 0:
        try:
            await client.send_message(config.LOG_GROUP_ID, f"📋 **Log:**\n`{text}`")
        except Exception as e:
            print(f"Failed to send log: {e}")

def log_exception(loop, context):
    """Global exception handler to send errors to log group."""
    exception = context.get('exception')
    if exception:
        error_text = f"Exception: {exception}\n{traceback.format_exc()}"
        asyncio.create_task(send_log(error_text))
        print(error_text)
    else:
        print(context['message'])

# Set up global exception handler
loop = asyncio.get_event_loop()
loop.set_exception_handler(log_exception)

# --- HELPERS ---
def credit(text: str) -> str:
    return f"{text}\n\n—— Made and developed by @DhruvOrigin"

def is_authorized(user_id: int) -> bool:
    return user_id == config.OWNER_ID or user_id in config.SUDO_USERS

def is_group(chat) -> bool:
    if isinstance(chat, User):
        return False
    if hasattr(chat, 'megagroup') and chat.megagroup:
        return True
    if hasattr(chat, 'group') and chat.group:
        return True
    return hasattr(chat, 'is_group') and chat.is_group

# ============================================================
#               AUTO DM BLOCK
# ============================================================
@client.on(events.NewMessage(incoming=True))
async def auto_block_dm(event):
    if not config.AUTO_DM_BLOCK or not event.is_private:
        return
    if is_authorized(event.sender_id):
        return
    try:
        await client.block_user(event.sender_id)
        print(f"🚫 Auto-blocked user: {event.sender_id}")
        try:
            await event.reply(credit("🚫 You have been blocked for sending a DM."))
        except:
            pass
    except Exception as e:
        error = f"Block error: {e}"
        print(error)
        await send_log(error)

@client.on(events.NewMessage(pattern=r"\.dmblock$"))
async def toggle_dm_block(event):
    if not is_authorized(event.sender_id):
        return
    new_status = not config.AUTO_DM_BLOCK
    await database.save_dm_block(new_status)
    config.AUTO_DM_BLOCK = new_status
    status = "✅ Enabled" if new_status else "❌ Disabled"
    await event.reply(credit(f"Auto DM Block: {status}"))

@client.on(events.NewMessage(pattern=r"\.dmblock status$"))
async def dm_block_status(event):
    if not is_authorized(event.sender_id):
        return
    status = "🟢 Active" if config.AUTO_DM_BLOCK else "🔴 Inactive"
    await event.reply(credit(f"**Auto DM Block Status:** {status}"))

# ============================================================
#               JOIN / LEAVE
# ============================================================
@client.on(events.NewMessage(pattern=r"\.join\s+(.+)"))
async def join_chat(event):
    if not is_authorized(event.sender_id):
        return
    link = event.pattern_match.group(1).strip()
    status_msg = await event.reply(credit(f"🔄 Attempting to join: `{link}`"))
    try:
        invite_hash = None
        username = None
        if "t.me/joinchat/" in link or "t.me/+" in link:
            invite_hash = link.split("/")[-1].split("?")[0]
        elif "t.me/" in link and "joinchat" not in link and "+" not in link:
            username = link.split("/")[-1].split("?")[0]
        else:
            if not link.startswith("http"):
                invite_hash = link.split("?")[0]
            else:
                await status_msg.edit(credit("❌ Unrecognized link format."))
                return

        if username:
            try:
                entity = await client.get_entity(f"@{username}")
                if isinstance(entity, (Channel, Chat)):
                    await client.join_channel(entity)
                    await status_msg.edit(credit(f"✅ Joined public group: `{link}`\nChat ID: `{entity.id}`"))
                    await asyncio.sleep(2)
                    await client.send_message(entity, "👋 Hello everyone! I've joined this group.")
                else:
                    await status_msg.edit(credit("❌ Not a group/channel."))
                return
            except Exception as e:
                await status_msg.edit(credit(f"❌ Error: `{str(e)}`"))
                await send_log(f"Join error (public): {e}\n{traceback.format_exc()}")
                return

        if invite_hash:
            try:
                result = await client(ImportChatInviteRequest(invite_hash))
                if result.chats:
                    chat = result.chats[0]
                    chat_id = chat.id
                    await status_msg.edit(credit(f"✅ Joined (or request sent) via invite: `{link}`\nChat ID: `{chat_id}`"))
                    await asyncio.sleep(2)
                    await client.send_message(chat_id, "👋 Hello everyone! I've joined this group.")
                else:
                    await status_msg.edit(credit("❌ No chat found in invite response."))
            except FloodWaitError as e:
                await status_msg.edit(credit(f"⏳ Flood wait: {e.seconds}s"))
            except InviteHashInvalidError:
                await status_msg.edit(credit(f"❌ Invalid invite link: `{link}`"))
            except InviteHashExpiredError:
                await status_msg.edit(credit(f"❌ Invite link expired: `{link}`"))
            except Exception as e:
                await status_msg.edit(credit(f"❌ Failed: `{str(e)}`"))
                await send_log(f"Join error (private): {e}\n{traceback.format_exc()}")
            return

        await status_msg.edit(credit("❌ Could not determine link type."))
    except Exception as e:
        await status_msg.edit(credit(f"❌ Unexpected error: `{str(e)}`"))
        await send_log(f"Join error (general): {e}\n{traceback.format_exc()}")

@client.on(events.NewMessage(pattern=r"\.leave\s+(-?\d+)"))
async def leave_chat(event):
    if not is_authorized(event.sender_id):
        return
    chat_id = int(event.pattern_match.group(1))
    try:
        entity = await client.get_entity(chat_id)
        await client.leave_chat(entity)
        await event.reply(credit(f"✅ Left chat: `{chat_id}`"))
    except Exception as e:
        await event.reply(credit(f"❌ Failed: `{str(e)}`"))
        await send_log(f"Leave error: {e}\n{traceback.format_exc()}")

# ============================================================
#               /FOLDER COMMAND (NEW)
# ============================================================
@client.on(events.NewMessage(pattern=r"\.folder$"))
async def add_folder(event):
    if not is_authorized(event.sender_id):
        return
    if not event.is_reply:
        await event.reply(credit("⚠️ Reply to a message containing a folder link with `.folder`."))
        return
    reply_msg = await event.get_reply_message()
    if not reply_msg:
        await event.reply(credit("❌ Could not find replied message."))
        return
    text = reply_msg.text
    if not text:
        await event.reply(credit("❌ Replied message has no text."))
        return
    # Extract folder link (t.me/addlist/...)
    pattern = r"(?:https?://)?(?:t\.me/)?addlist/([a-zA-Z0-9_-]+)"
    match = re.search(pattern, text)
    if not match:
        await event.reply(credit("❌ No folder invite link found in the replied message."))
        return
    hash_str = match.group(1)
    try:
        result = await client(ImportFolderInviteRequest(hash_str))
        await event.reply(credit(f"✅ Folder added successfully!"))
    except FloodWaitError as e:
        await event.reply(credit(f"⏳ Flood wait: {e.seconds}s"))
    except Exception as e:
        await event.reply(credit(f"❌ Failed to add folder: `{str(e)}`"))
        await send_log(f"Folder error: {e}\n{traceback.format_exc()}")

# ============================================================
#               /BIO COMMAND
# ============================================================
@client.on(events.NewMessage(pattern=r"^/bio$"))
async def set_bio(event):
    if not is_authorized(event.sender_id):
        return
    if not event.is_reply:
        await event.reply(credit("⚠️ Reply to a message with `/bio` to set it as your bio."))
        return
    reply_msg = await event.get_reply_message()
    if not reply_msg:
        await event.reply(credit("❌ Could not find replied message."))
        return
    new_bio = reply_msg.text
    if not new_bio:
        await event.reply(credit("❌ Replied message has no text."))
        return
    try:
        if len(new_bio) > 70:
            new_bio = new_bio[:70]
            await event.reply(credit(f"⚠️ Bio trimmed to 70 characters."))
        await client.edit_profile(about=new_bio)
        await event.reply(credit(f"✅ Bio updated to:\n\n`{new_bio}`"))
    except Exception as e:
        await event.reply(credit(f"❌ Failed to update bio: `{str(e)}`"))
        await send_log(f"Bio error: {e}\n{traceback.format_exc()}")

# ============================================================
#               SPAM CHECK / SEND
# ============================================================
@client.on(events.NewMessage(pattern=r"\.spamcheck$"))
async def spam_check(event):
    if not is_authorized(event.sender_id):
        return
    try:
        spam_bot = await client.get_entity("@SpamBot")
        await client.send_message(spam_bot, "/start")
        reply = await client.wait_for(events.NewMessage(from_users=spam_bot.id), timeout=10)
        response = reply.message.text
        if "limited" in response.lower():
            status = "🚫 Your account is **limited** (spam restriction)."
        elif "not limited" in response.lower():
            status = "✅ Your account is **not limited**."
        else:
            status = f"⚠️ Could not determine. Response: {response[:100]}"
        await event.reply(credit(status))
    except asyncio.TimeoutError:
        await event.reply(credit("❌ No response from @SpamBot. Try again."))
    except Exception as e:
        await event.reply(credit(f"❌ Error: `{str(e)}`"))
        await send_log(f"SpamCheck error: {e}\n{traceback.format_exc()}")

@client.on(events.NewMessage(pattern=r"\.spamsend\s+(\d+)"))
async def spam_send(event):
    if not is_authorized(event.sender_id):
        return
    count = int(event.pattern_match.group(1))
    if count > 50:
        await event.reply(credit("❌ Maximum 50 to avoid flood."))
        return
    try:
        spam_bot = await client.get_entity("@SpamBot")
        await event.reply(credit(f"🔄 Sending /start {count} times..."))
        for i in range(count):
            await client.send_message(spam_bot, "/start")
            await asyncio.sleep(0.3)
        await event.reply(credit(f"✅ Sent `/start` {count} times to @SpamBot.\nCheck PM for responses."))
    except Exception as e:
        await event.reply(credit(f"❌ Error: `{str(e)}`"))
        await send_log(f"SpamSend error: {e}\n{traceback.format_exc()}")

# ============================================================
#               BROADCAST (only groups)
# ============================================================
async def broadcast_message(reply_msg):
    groups = []
    async for dialog in client.iter_dialogs():
        if dialog.is_group or (hasattr(dialog.entity, 'megagroup') and dialog.entity.megagroup):
            groups.append(dialog.entity)
    if not groups:
        return None
    sent_count = 0
    failed = []
    skipped = []
    
    async def send_to(chat):
        if not is_group(chat):
            skipped.append((chat.title or chat.id, "Not a group"))
            return False
        try:
            await client.send_message(chat, reply_msg)
            return True
        except Exception as e:
            failed.append((chat.title or chat.id, str(e)))
            return False
    
    if MODE == "parallel":
        if PARALLEL_BATCH_SIZE is None:
            results = await asyncio.gather(*[send_to(g) for g in groups])
            sent_count = sum(results)
        else:
            for i in range(0, len(groups), PARALLEL_BATCH_SIZE):
                batch = groups[i:i + PARALLEL_BATCH_SIZE]
                results = await asyncio.gather(*[send_to(g) for g in batch])
                sent_count += sum(results)
                if i + PARALLEL_BATCH_SIZE < len(groups):
                    await asyncio.sleep(DELAY)
    else:
        for i, group in enumerate(groups):
            if await send_to(group):
                sent_count += 1
            if i < len(groups) - 1:
                await asyncio.sleep(DELAY)
    
    report = f"✅ **{sent_count}/{len(groups)}** groups received the message."
    if skipped:
        skip_list = "\n".join([f"• {name}: `{reason}`" for name, reason in skipped[:3]])
        report += f"\n⚠️ **{len(skipped)}** skipped (not groups):\n{skip_list}"
    if failed:
        fail_list = "\n".join([f"• {name}: `{err}`" for name, err in failed[:5]])
        report += f"\n❌ **{len(failed)}** failed:\n{fail_list}"
    return report

@client.on(events.NewMessage(pattern=r"\.b$"))
async def broadcast(event):
    if not is_authorized(event.sender_id):
        return
    if not event.is_reply:
        await event.reply(credit("⚠️ Reply to a message with `.b`."))
        return
    reply_msg = await event.get_reply_message()
    if not reply_msg:
        await event.reply(credit("❌ Could not find message."))
        return
    status_msg = await event.reply("📤 Broadcasting to groups only...")
    try:
        report = await broadcast_message(reply_msg)
        if report:
            await status_msg.edit(credit(report))
        else:
            await status_msg.edit(credit("⚠️ No groups found."))
    except Exception as e:
        await status_msg.edit(credit(f"❌ Broadcast error: `{str(e)}`"))
        await send_log(f"Broadcast error: {e}\n{traceback.format_exc()}")

# ============================================================
#               AUTO BROADCAST LOOP & COMMANDS
# ============================================================
async def auto_broadcast_loop():
    while config.AUTO_BROADCAST_ACTIVE:
        try:
            settings = await database.get_auto_broadcast()
            if not settings or not settings.get("active", False):
                break
            msg = await client.get_messages(settings["chat_id"], ids=settings["message_id"])
            if msg:
                report = await broadcast_message(msg)
                print(f"Auto broadcast sent: {report}")
            await asyncio.sleep(config.AUTO_BROADCAST_INTERVAL)
        except asyncio.CancelledError:
            break
        except Exception as e:
            error = f"Auto broadcast error: {e}\n{traceback.format_exc()}"
            print(error)
            await send_log(error)
            await asyncio.sleep(60)

@client.on(events.NewMessage(pattern=r"\.ab$"))
async def auto_broadcast(event):
    if not is_authorized(event.sender_id):
        return
    if not event.is_reply:
        await event.reply(credit("⚠️ Reply to a message with `.ab`."))
        return
    reply_msg = await event.get_reply_message()
    if not reply_msg:
        await event.reply(credit("❌ Could not find message."))
        return
    settings = await database.get_auto_broadcast()
    interval = settings.get("interval", 3600) if settings else 3600
    await database.save_auto_broadcast(interval, reply_msg.id, event.chat_id, True)
    global auto_broadcast_task
    if auto_broadcast_task and not auto_broadcast_task.done():
        auto_broadcast_task.cancel()
    auto_broadcast_task = asyncio.create_task(auto_broadcast_loop())
    await event.reply(credit(f"✅ Auto broadcast set (interval {interval}s)."))

@client.on(events.NewMessage(pattern=r"\.setime\s+(\d+)"))
async def set_interval(event):
    if not is_authorized(event.sender_id):
        return
    interval = int(event.pattern_match.group(1))
    if interval < 5:
        await event.reply(credit("❌ Minimum 5 seconds."))
        return
    settings = await database.get_auto_broadcast()
    if settings and settings.get("active"):
        await database.save_auto_broadcast(interval, settings["message_id"], settings["chat_id"], True)
        global auto_broadcast_task
        if auto_broadcast_task and not auto_broadcast_task.done():
            auto_broadcast_task.cancel()
        auto_broadcast_task = asyncio.create_task(auto_broadcast_loop())
        await event.reply(credit(f"✅ Interval updated to {interval}s."))
    else:
        await event.reply(credit("⚠️ No active auto broadcast. Use `.ab` first."))

@client.on(events.NewMessage(pattern=r"\.stopab$"))
async def stop_auto_broadcast(event):
    if not is_authorized(event.sender_id):
        return
    await database.disable_auto_broadcast()
    global auto_broadcast_task
    if auto_broadcast_task and not auto_broadcast_task.done():
        auto_broadcast_task.cancel()
        auto_broadcast_task = None
    await event.reply(credit("✅ Auto broadcast stopped."))

@client.on(events.NewMessage(pattern=r"\.abstatus$"))
async def ab_status(event):
    if not is_authorized(event.sender_id):
        return
    settings = await database.get_auto_broadcast()
    if not settings or not settings.get("active"):
        await event.reply(credit("ℹ️ Auto broadcast inactive."))
    else:
        await event.reply(credit(f"**Auto Broadcast:**\n• Active\n• Interval: {settings['interval']}s"))

# ============================================================
#               SETTINGS COMMANDS
# ============================================================
@client.on(events.NewMessage(pattern=r"\.delay\s+(\d+)"))
async def set_delay(event):
    if not is_authorized(event.sender_id):
        return
    global DELAY
    seconds = int(event.pattern_match.group(1))
    if seconds < 0:
        await event.reply(credit("❌ Positive number."))
        return
    DELAY = seconds
    await database.save_settings(delay=seconds)
    await event.reply(credit(f"✅ Delay set to {DELAY}s."))

@client.on(events.NewMessage(pattern=r"\.dp\s+(\d+)"))
async def set_dp(event):
    if not is_authorized(event.sender_id):
        return
    global DELAY
    micro = int(event.pattern_match.group(1))
    seconds = micro / 1_000_000
    if seconds < 0:
        await event.reply(credit("❌ Positive number."))
        return
    DELAY = seconds
    await database.save_settings(delay=seconds)
    await event.reply(credit(f"✅ Delay set to {micro}µs ({seconds}s)."))

@client.on(events.NewMessage(pattern=r"\.parallel(?:\s+(\d+))?$"))
async def set_parallel(event):
    if not is_authorized(event.sender_id):
        return
    global MODE, PARALLEL_BATCH_SIZE
    MODE = "parallel"
    num = event.pattern_match.group(1)
    PARALLEL_BATCH_SIZE = int(num) if num else None
    await database.save_settings(mode=MODE)
    await event.reply(credit(f"⚡ Parallel mode with batch size {PARALLEL_BATCH_SIZE or 'all'}."))

@client.on(events.NewMessage(pattern=r"\.batch$"))
async def set_batch(event):
    if not is_authorized(event.sender_id):
        return
    global MODE, PARALLEL_BATCH_SIZE
    MODE = "batch"
    PARALLEL_BATCH_SIZE = None
    await database.save_settings(mode=MODE)
    await event.reply(credit("🔄 Batch mode (one group at a time)."))

# ============================================================
#               SUDO COMMANDS
# ============================================================
@client.on(events.NewMessage(pattern=r"\.sudo\s+(\d+)"))
async def add_sudo(event):
    if event.sender_id != config.OWNER_ID:
        return
    user_id = int(event.pattern_match.group(1))
    await database.add_sudo_user(user_id)
    await event.reply(credit(f"✅ Sudo user `{user_id}` added."))

@client.on(events.NewMessage(pattern=r"\.unsudo\s+(\d+)"))
async def remove_sudo(event):
    if event.sender_id != config.OWNER_ID:
        return
    user_id = int(event.pattern_match.group(1))
    await database.remove_sudo_user(user_id)
    await event.reply(credit(f"✅ Sudo user `{user_id}` removed."))

@client.on(events.NewMessage(pattern=r"\.sudo$"))
async def list_sudo(event):
    if not is_authorized(event.sender_id):
        return
    if not config.SUDO_USERS:
        await event.reply(credit("ℹ️ No sudo users."))
        return
    sudo_list = "\n".join([f"• `{uid}`" for uid in config.SUDO_USERS])
    await event.reply(credit(f"**Sudo Users:**\n{sudo_list}"))

# ============================================================
#               UTILITY COMMANDS
# ============================================================
@client.on(events.NewMessage(pattern=r"\.ping$"))
async def ping(event):
    if not is_authorized(event.sender_id):
        return
    start = time.time()
    msg = await event.reply("Pinging...")
    ms = round((time.time() - start) * 1000)
    await msg.edit(credit(f"⚡ Pong! {ms} ms"))

@client.on(events.NewMessage(pattern=r"\.id$"))
async def get_id(event):
    if not is_authorized(event.sender_id):
        return
    user_id = event.sender_id
    chat_id = event.chat_id
    reply = await event.get_reply_message()
    if reply:
        user_id = reply.sender_id
    await event.reply(credit(f"**User ID:** `{user_id}`\n**Chat ID:** `{chat_id}`"))

@client.on(events.NewMessage(pattern=r"\.groups$"))
async def list_groups(event):
    if not is_authorized(event.sender_id):
        return
    groups = []
    async for dialog in client.iter_dialogs():
        if dialog.is_group or (hasattr(dialog.entity, 'megagroup') and dialog.entity.megagroup):
            groups.append(dialog)
    if not groups:
        await event.reply(credit("ℹ️ No groups."))
        return
    lines = [f"• `{g.id}` - {g.name} ({getattr(g.entity, 'participants_count', 'N/A')} members)" for g in groups[:20]]
    msg = f"**Groups ({len(groups)}):**\n" + "\n".join(lines)
    if len(groups) > 20:
        msg += f"\n... and {len(groups)-20} more."
    await event.reply(credit(msg))

@client.on(events.NewMessage(pattern=r"\.stats$"))
async def stats(event):
    if not is_authorized(event.sender_id):
        return
    dialogs = await client.get_dialogs()
    groups = [d for d in dialogs if d.is_group or (hasattr(d.entity, 'megagroup') and d.entity.megagroup)]
    users = [d for d in dialogs if d.is_user]
    await event.reply(credit(
        f"**📊 Stats:**\n"
        f"• Total Dialogs: `{len(dialogs)}`\n"
        f"• Groups: `{len(groups)}`\n"
        f"• Users: `{len(users)}`\n"
        f"• Mode: `{MODE}`\n"
        f"• Delay: `{DELAY}s`"
    ))

@client.on(events.NewMessage(pattern=r"\.status$"))
async def bot_status(event):
    if not is_authorized(event.sender_id):
        return
    uptime_seconds = time.time() - client.start_time if hasattr(client, 'start_time') else 0
    uptime = str(timedelta(seconds=int(uptime_seconds)))
    groups = []
    async for dialog in client.iter_dialogs():
        if dialog.is_group or (hasattr(dialog.entity, 'megagroup') and dialog.entity.megagroup):
            groups.append(dialog)
    await event.reply(credit(
        f"**📊 Bot Status:**\n"
        f"• Mode: `{MODE}`\n"
        f"• Delay: `{DELAY}s`\n"
        f"• DM Block: `{'🟢 Active' if config.AUTO_DM_BLOCK else '🔴 Inactive'}`\n"
        f"• Auto Broadcast: `{'🟢 Active' if config.AUTO_BROADCAST_ACTIVE else '🔴 Inactive'}`\n"
        f"• Total Groups: `{len(groups)}`\n"
        f"• Sudo Users: `{len(config.SUDO_USERS)}`\n"
        f"• Uptime: `{uptime}`"
    ))

# ============================================================
#               HELP
# ============================================================
@client.on(events.NewMessage(pattern=r"\.help$"))
async def help_command(event):
    if not is_authorized(event.sender_id):
        return
    help_text = f"""
**📚 Available Commands:**

**Broadcast:**
`.b` - broadcast replied message to **groups only**
`.ab` - set auto broadcast (reply to a message)
`.setime <sec>` - set auto broadcast interval
`.stopab` - stop auto broadcast
`.abstatus` - check auto broadcast status

**Group Management:**
`.join <link>` - join group/channel via invite link (supports all formats)
`.leave <chat_id>` - leave a chat by ID
`.groups` - list all your groups

**Folder Management:**
`.folder` - reply to a message containing a folder link (t.me/addlist/...) to add that folder to your account

**DM Protection:**
`.dmblock` - toggle auto DM block
`.dmblock status` - check DM block status

**Bio:**
`/bio` - reply to a message with `/bio` to set that text as your bio

**Spam / Limitation:**
`.spamcheck` - check if account is limited (via @SpamBot)
`.spamsend <count>` - send /start to @SpamBot N times (max 50)

**Delay:**
`.delay <sec>` - set broadcast delay in seconds
`.dp <µs>` - set broadcast delay in microseconds

**Mode:**
`.parallel [batch_size]` - parallel mode
`.batch` - batch mode (one group at a time)

**Sudo (owner only):**
`.sudo <user_id>` - add sudo user
`.unsudo <user_id>` - remove sudo user
`.sudo` - list sudo users

**Utility:**
`.ping` - latency check
`.id` - get user/chat IDs
`.stats` - statistics
`.status` - detailed bot status
`.help` - this menu

**Current:**
• Mode: `{MODE}`
• Delay: `{DELAY}s`
• DM Block: `{'Active' if config.AUTO_DM_BLOCK else 'Inactive'}`
• Auto Broadcast: `{'Active' if config.AUTO_BROADCAST_ACTIVE else 'Inactive'}`

⚠️ Broadcasts only go to **groups**, never to channels or DMs.
"""
    await event.reply(credit(help_text))

# ============================================================
#               MAIN
# ============================================================
async def main():
    await database.connect()
    print("✅ Connected to MongoDB")
    global DELAY, MODE
    DELAY = config.DEFAULT_DELAY
    MODE = config.DEFAULT_MODE
    await client.start(phone=config.PHONE)
    client.start_time = time.time()
    print("✅ Userbot Started — @DhruvOrigin")
    print(f"📊 Mode: {MODE}, Delay: {DELAY}s")
    print(f"👥 Sudo: {len(config.SUDO_USERS)}")
    print(f"🛡️ DM Block: {'Active' if config.AUTO_DM_BLOCK else 'Inactive'}")
    print(f"📋 Log Group: {config.LOG_GROUP_ID if config.LOG_GROUP_ID else 'Disabled'}")

    settings = await database.get_auto_broadcast()
    if settings and settings.get("active"):
        config.AUTO_BROADCAST_INTERVAL = settings["interval"]
        config.AUTO_BROADCAST_ACTIVE = True
        global auto_broadcast_task
        auto_broadcast_task = asyncio.create_task(auto_broadcast_loop())
        print("✅ Auto broadcast started")

    print("\n💡 Type .help for commands")
    await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Stopped.")
