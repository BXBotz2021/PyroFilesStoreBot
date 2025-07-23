# (c) @AbirHasan2005
# Modernized by Gemini

import os
import asyncio
import traceback
from binascii import Error
from pyrogram import Client, filters
from pyrogram.errors import UserNotParticipant, FloodWait, QueryIdInvalid
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from pyrogram.enums import ChatType, ChatMemberStatus

from configs import Config
from handlers.database import db
from handlers.add_user_to_db import add_user_to_database
from handlers.send_file import send_media_and_reply
from handlers.helpers import b64_to_str, str_to_b64
from handlers.check_user_status import handle_user_status
from handlers.force_sub_handler import handle_force_sub, get_invite_link
from handlers.broadcast_handlers import main_broadcast_handler
from handlers.save_media import save_media_in_channel, save_batch_media_in_channel

# A dictionary to store user's media for batch processing
MediaList = {}

# Initialize the Bot
Bot = Client(
    name=Config.BOT_USERNAME,
    in_memory=True,
    bot_token=Config.BOT_TOKEN,
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
)


@Bot.on_message(filters.private)
async def _(bot: Client, cmd: Message):
    await handle_user_status(bot, cmd)


@Bot.on_message(filters.command("start") & filters.private)
async def start(bot: Client, cmd: Message):
    if cmd.from_user.id in Config.BANNED_USERS:
        await cmd.reply_text("Sorry, you are banned.")
        return

    if Config.UPDATES_CHANNEL is not None:
        back = await handle_force_sub(bot, cmd)
        if back == 400:
            return

    # Check if the command has a payload
    usr_cmd = cmd.text.split("_", 1)[-1]
    if usr_cmd == "/start":
        await add_user_to_database(bot, cmd)
        await cmd.reply_text(
            Config.HOME_TEXT.format(cmd.from_user.first_name, cmd.from_user.id),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Support Group", url="https://t.me/JoinOT"),
                        InlineKeyboardButton("Bots Channel", url="https://t.me/Discovery_Updates"),
                    ],
                    [
                        InlineKeyboardButton("About Bot", callback_data="aboutbot"),
                        InlineKeyboardButton("About Dev", callback_data="aboutdevs"),
                    ],
                ]
            ),
        )
    else:
        try:
            # Decode the file ID from base64
            try:
                file_id_b64 = usr_cmd
                file_id = int(b64_to_str(file_id_b64).split("_")[-1])
            except (Error, UnicodeDecodeError):
                file_id = int(usr_cmd.split("_")[-1])

            # Retrieve the message from the database channel
            get_message = await bot.get_messages(chat_id=Config.DB_CHANNEL, message_ids=file_id)
            message_ids = []
            if get_message.text:
                # It's a batch of files
                message_ids = get_message.text.split(" ")
                await cmd.reply_text(
                    text=f"**Total Files:** `{len(message_ids)}`",
                    quote=True,
                    disable_web_page_preview=True,
                )
            else:
                # It's a single file
                message_ids.append(int(get_message.id))

            # Send each file to the user
            for msg_id in message_ids:
                await send_media_and_reply(bot, user_id=cmd.from_user.id, file_id=int(msg_id))
        except Exception as err:
            await cmd.reply_text(f"Something went wrong!\n\n**Error:** `{err}`")


@Bot.on_message((filters.document | filters.video | filters.audio) & ~filters.chat(Config.DB_CHANNEL))
async def main(bot: Client, message: Message):
    if message.chat.type == ChatType.PRIVATE:
        await add_user_to_database(bot, message)

        if Config.UPDATES_CHANNEL is not None:
            back = await handle_force_sub(bot, message)
            if back == 400:
                return

        if message.from_user.id in Config.BANNED_USERS:
            await message.reply_text(
                "Sorry, you are banned!\n\nContact [Support Group](https://t.me/JoinOT)",
                disable_web_page_preview=True,
            )
            return

        if not Config.OTHER_USERS_CAN_SAVE_FILE:
            return

        await message.reply_text(
            text="**Choose an option from below:**",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Save in Batch", callback_data="addToBatchTrue")],
                    [InlineKeyboardButton("Get Sharable Link", callback_data="addToBatchFalse")],
                ]
            ),
            quote=True,
            disable_web_page_preview=True,
        )
    elif message.chat.type == ChatType.CHANNEL:
        if (message.chat.id == int(Config.LOG_CHANNEL)) or (
            Config.UPDATES_CHANNEL and message.chat.id == int(Config.UPDATES_CHANNEL)
        ) or message.forward_from_chat or message.forward_from:
            return
        elif int(message.chat.id) in Config.BANNED_CHAT_IDS:
            await bot.leave_chat(message.chat.id)
            return

        try:
            forwarded_msg = await message.forward(Config.DB_CHANNEL)
            file_er_id = str(forwarded_msg.id)
            share_link = f"https://t.me/{Config.BOT_USERNAME}?start=AbirHasan2005_{str_to_b64(file_er_id)}"
            ch_edit = await bot.edit_message_reply_markup(
                message.chat.id,
                message.id,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Get Sharable Link", url=share_link)]]
                ),
            )
            # Log the action
            log_text = f"#CHANNEL_BUTTON:\n\nChannel: {message.chat.title}\n"
            if message.chat.username:
                log_text += f"Link: [Click Here](https://t.me/{message.chat.username}/{ch_edit.id})"
            else:
                private_ch = str(message.chat.id)[4:]
                log_text += f"Link: [Click Here](https://t.me/c/{private_ch}/{ch_edit.id})"
            await forwarded_msg.reply_text(log_text)

        except FloodWait as sl:
            await asyncio.sleep(sl.value)
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"#FloodWait:\nGot FloodWait of `{sl.value}s` from `{message.chat.id}`!",
            )
        except Exception as err:
            await bot.leave_chat(message.chat.id)
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"#ERROR_TRACEBACK:\nGot Error from `{message.chat.id}`!\n\n**Traceback:** `{err}`",
            )


@Bot.on_message(filters.private & filters.command("broadcast") & filters.user(Config.BOT_OWNER) & filters.reply)
async def broadcast_handler_open(_, m: Message):
    await main_broadcast_handler(m, db)


@Bot.on_message(filters.private & filters.command("status") & filters.user(Config.BOT_OWNER))
async def sts(_, m: Message):
    total_users = await db.total_users_count()
    await m.reply_text(text=f"**Total Users in DB:** `{total_users}`", quote=True)


@Bot.on_message(filters.private & filters.command("ban_user") & filters.user(Config.BOT_OWNER))
async def ban(c: Client, m: Message):
    if len(m.command) == 1:
        await m.reply_text(
            "Use this command to ban a user from the bot.\n\n"
            "Usage:\n`/ban_user user_id ban_duration ban_reason`\n\n"
            "Example: `/ban_user 1234567 28 Misused me.`\n"
            "This bans user `1234567` for `28` days for the reason `Misused me`.",
            quote=True,
        )
        return

    try:
        user_id = int(m.command[1])
        ban_duration = int(m.command[2])
        ban_reason = " ".join(m.command[3:])
        ban_log_text = f"Banning user {user_id} for {ban_duration} days for the reason: {ban_reason}."
        try:
            await c.send_message(
                user_id,
                f"You are banned from using this bot for **{ban_duration}** day(s) for the reason: __{ban_reason}__\n\n"
                f"**Message from the admin**",
            )
            ban_log_text += "\n\nUser notified successfully!"
        except Exception as e:
            traceback.print_exc()
            ban_log_text += f"\n\nUser notification failed! \n`{e}`"

        await db.ban_user(user_id, ban_duration, ban_reason)
        await m.reply_text(ban_log_text, quote=True)
    except Exception as e:
        traceback.print_exc()
        await m.reply_text(
            f"An error occurred! Traceback given below:\n\n`{traceback.format_exc()}`",
            quote=True,
        )


@Bot.on_message(filters.private & filters.command("unban_user") & filters.user(Config.BOT_OWNER))
async def unban(c: Client, m: Message):
    if len(m.command) == 1:
        await m.reply_text(
            "Use this command to unban a user.\n\n"
            "Usage:\n`/unban_user user_id`\n\n"
            "Example: `/unban_user 1234567`",
            quote=True,
        )
        return

    try:
        user_id = int(m.command[1])
        unban_log_text = f"Unbanning user {user_id}"
        try:
            await c.send_message(user_id, "Your ban was lifted!")
            unban_log_text += "\n\nUser notified successfully!"
        except Exception as e:
            traceback.print_exc()
            unban_log_text += f"\n\nUser notification failed! \n`{e}`"
        await db.remove_ban(user_id)
        await m.reply_text(unban_log_text, quote=True)
    except Exception as e:
        traceback.print_exc()
        await m.reply_text(
            f"An error occurred! Traceback given below:\n\n`{traceback.format_exc()}`",
            quote=True,
        )


@Bot.on_message(filters.private & filters.command("banned_users") & filters.user(Config.BOT_OWNER))
async def _banned_users(_, m: Message):
    all_banned_users = await db.get_all_banned_users()
    banned_usr_count = 0
    text = ""
    async for banned_user in all_banned_users:
        user_id = banned_user["id"]
        ban_duration = banned_user["ban_status"]["ban_duration"]
        banned_on = banned_user["ban_status"]["banned_on"]
        ban_reason = banned_user["ban_status"]["ban_reason"]
        banned_usr_count += 1
        text += (
            f"> **User ID**: `{user_id}`, **Duration**: `{ban_duration}` days, "
            f"**Banned On**: `{banned_on}`, **Reason**: `{ban_reason}`\n\n"
        )
    reply_text = f"**Total Banned User(s):** `{banned_usr_count}`\n\n{text}"
    if len(reply_text) > 4096:
        with open("banned-users.txt", "w") as f:
            f.write(reply_text)
        await m.reply_document("banned-users.txt", True)
        os.remove("banned-users.txt")
        return
    await m.reply_text(reply_text, True)


@Bot.on_message(filters.private & filters.command("clear_batch"))
async def clear_user_batch(_, m: Message):
    MediaList[str(m.from_user.id)] = []
    await m.reply_text("Your batch files have been cleared successfully!")


@Bot.on_callback_query()
async def button(bot: Client, cmd: CallbackQuery):
    cb_data = cmd.data
    if "aboutbot" in cb_data:
        await cmd.message.edit(
            Config.ABOUT_BOT_TEXT,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Source Code", url="https://github.com/AbirHasan2005/PyroFilesStoreBot"
                        )
                    ],
                    [
                        InlineKeyboardButton("Go Home", callback_data="gotohome"),
                        InlineKeyboardButton("About Dev", callback_data="aboutdevs"),
                    ],
                ]
            ),
        )
    elif "aboutdevs" in cb_data:
        await cmd.message.edit(
            Config.ABOUT_DEV_TEXT,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Source Code", url="https://github.com/AbirHasan2005/PyroFilesStoreBot"
                        )
                    ],
                    [
                        InlineKeyboardButton("About Bot", callback_data="aboutbot"),
                        InlineKeyboardButton("Go Home", callback_data="gotohome"),
                    ],
                ]
            ),
        )
    elif "gotohome" in cb_data:
        await cmd.message.edit(
            Config.HOME_TEXT.format(cmd.message.chat.first_name, cmd.message.chat.id),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Support Group", url="https://t.me/JoinOT"),
                        InlineKeyboardButton("Bots Channel", url="https://t.me/Discovery_Updates"),
                    ],
                    [
                        InlineKeyboardButton("About Bot", callback_data="aboutbot"),
                        InlineKeyboardButton("About Dev", callback_data="aboutdevs"),
                    ],
                ]
            ),
        )
    elif "refreshForceSub" in cb_data:
        if Config.UPDATES_CHANNEL:
            channel = Config.UPDATES_CHANNEL
            try:
                user = await bot.get_chat_member(channel, cmd.message.chat.id)
                if user.status == ChatMemberStatus.BANNED:
                    await cmd.message.edit(
                        text="Sorry, you are banned from the updates channel. Contact my [Support Group](https://t.me/JoinOT).",
                        disable_web_page_preview=True,
                    )
                    return
            except UserNotParticipant:
                invite_link = await get_invite_link(bot, channel)
                await cmd.message.edit(
                    text="**You still haven't joined ☹️. Please join my updates channel to use this bot!**",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton("🤖 Join Updates Channel", url=invite_link.invite_link)
                            ],
                            [InlineKeyboardButton("🔄 Refresh 🔄", callback_data="refreshForceSub")],
                        ]
                    ),
                )
                return
            except Exception as e:
                await cmd.message.edit(
                    text=f"Something went wrong. Contact my [Support Group](https://t.me/JoinOT).\n\n`{e}`",
                    disable_web_page_preview=True,
                )
                return
        await cmd.message.delete()
        await start(bot, cmd.message)

    elif cb_data.startswith("ban_user_"):
        user_id = cb_data.split("_", 2)[-1]
        if not int(cmd.from_user.id) == Config.BOT_OWNER:
            await cmd.answer("You are not allowed to do that!", show_alert=True)
            return
        try:
            await bot.ban_chat_member(chat_id=int(Config.UPDATES_CHANNEL), user_id=int(user_id))
            await cmd.answer("User banned from updates channel!", show_alert=True)
        except Exception as e:
            await cmd.answer(f"Can't ban them!\n\nError: {e}", show_alert=True)

    elif "addToBatchTrue" in cb_data:
        user_id_str = str(cmd.from_user.id)
        if MediaList.get(user_id_str, None) is None:
            MediaList[user_id_str] = []
        file_id = cmd.message.reply_to_message.id
        MediaList[user_id_str].append(file_id)
        await cmd.message.edit(
            "File saved in batch!\n\nPress the button below to get the batch link.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Get Batch Link", callback_data="getBatchLink")],
                    [InlineKeyboardButton("Close Message", callback_data="closeMessage")],
                ]
            ),
        )
    elif "addToBatchFalse" in cb_data:
        await save_media_in_channel(bot, editable=cmd.message, message=cmd.message.reply_to_message)

    elif "getBatchLink" in cb_data:
        message_ids = MediaList.get(str(cmd.from_user.id), None)
        if not message_ids:
            await cmd.answer("Batch list is empty!", show_alert=True)
            return
        await cmd.message.edit("Please wait, generating batch link...")
        await save_batch_media_in_channel(bot=bot, editable=cmd.message, message_ids=message_ids)
        MediaList[str(cmd.from_user.id)] = []

    elif "closeMessage" in cb_data:
        await cmd.message.delete(True)

    try:
        await cmd.answer()
    except QueryIdInvalid:
        pass


if __name__ == "__main__":
    print("Starting Bot...")
    Bot.run()
