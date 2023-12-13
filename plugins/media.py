import asyncio
import re
from typing import List
from swibots import BotApp, BotContext, CommandEvent, InlineMarkup, InlineKeyboardButton, filters, Message, Group, Channel, CallbackQueryEvent
from database.ia_filterdb import save_file, Media, get_search_results
from utils import get_size, temp, file_int_from_name, file_str_from_int
from config import ADMINS, CUSTOM_FILE_CAPTION
from swibots import Media as SwiMedia
import logging
from client import app

lock = asyncio.Lock()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@app.on_command(["search", "file", "files"])
async def show_movie_info(ctx: BotContext[CommandEvent]):
        message = ctx.event.message
        params = ctx.event.params
        if params is None or len(params) == 0:
            await message.reply_text(f"Please enter a movie name!\nType /{ctx.event.command} <movie name>")
            return
        mymessage = await message.reply_text(f"Searching for {params}...")

        await show_media_results(mymessage, params, "0", app)

@app.on_callback_query(filters.regexp('^search_prev'))
async def search_prev_callback(ctx: BotContext[CallbackQueryEvent]):
        _, search_params, offset = ctx.event.callback_data.split('#')
        mymessage = await ctx.event.message.edit_text(f"Searching for {search_params}...")
        await show_media_results(mymessage, search_params, offset, app)

@app.on_callback_query(filters.regexp('^search_next'))
async def search_next_callback(ctx: BotContext[CallbackQueryEvent]):
        _, search_params, offset = ctx.event.callback_data.split('#')
        mymessage = await ctx.event.message.edit_text(f"Searching for {search_params}...")
        await show_media_results(mymessage, search_params, offset, app)

@app.on_command("index")
async def index_channel(ctx: BotContext[CommandEvent]):
        message: Message = ctx.event.message

        if ADMINS is None or message.user_id not in ADMINS:
            await message.reply_text("You are not allowed to use this command!")
            return

        args = ctx.event.params

        params_regex = re.compile(r"^([a-zA-Z0-9\-]+) ?([0-9]+)? ?([0-9]+)?$")
        channel_or_group_id = None
        channel_or_group = None
        is_group = False

        if message.channel_id is not None:
            channel_or_group_id = message.channel_id
        elif message.group_id is not None:
            channel_or_group_id = message.group_id
            is_group = True
        else:
            if not params_regex.match(args):
                await message.reply_text(f"Please enter a channel id!\nType /{ctx.event.command} <channel id>")
                return
            channel_or_group_id = params_regex.match(args).group(1)

        # get the channel
        try:
            channel_or_group = await app.get_channel(channel_or_group_id)
            if channel_or_group is None:
                await message.reply_text(f"Channel {channel_or_group_id} not found!")
                return
        except Exception as e:
            try:
                channel_or_group = await app.get_group(channel_or_group_id)
                is_group = True
                if channel_or_group is None:
                    await message.reply_text(f"Group {channel_or_group_id} not found!")
                    return
            except Exception as e:
                await message.reply_text(f"Channel or group {channel_or_group_id} not found!")
                return

        mymessage = await message.reply_text(f"Getting messages for {'Group' if is_group else 'Channel'} {channel_or_group_id}...")
        await index_files_to_db(channel_or_group=channel_or_group, is_group=is_group, msg=mymessage, app=app)

@app.on_command(["deleteall"])
async def delete_all(ctx: BotContext[CommandEvent]):
        message = ctx.event.message

        if ADMINS is None or message.user_id not in ADMINS:
            await message.reply_text("You are not allowed to use this command!")
            return

        await message.reply_text(
            'This will delete all indexed files.\nDo you want to continue??',
            inline_markup=InlineMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="YES", callback_data="delete_all_data"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="CANCEL", callback_data="close_data"
                        )
                    ],
                ]
            ),
        )

@app.on_callback_query(filters.regexp(r'^delete_all_data'))
async def delete_all_index_confirm(ctx: BotContext[CallbackQueryEvent]):
        message = ctx.event.message
        await Media.collection.drop()
        await message.edit_text('Succesfully Deleted All The Indexed Files.')

@app.on_callback_query(filters.regexp(r"blk_(.*)"))
async def listenCallback(ctx: BotContext[CallbackQueryEvent]):
    m = ctx.event.message
    data = int(ctx.event.callback_data.split("_")[-1])
    file = await Media.find({"file_id": data}).to_list(1)
    file = file[0]
    try:
        media = await app.get_media(data)
    except Exception as er:
        await m.send(f"{file.description} not found!")
        return
    media.id = 0
    await ctx.event.answer("File will be sent to your PM!", show_alert=True)
    f_caption = file.caption
    title = file.file_name
    size = get_size(file.file_size)

    if CUSTOM_FILE_CAPTION:
            try:
                f_caption = CUSTOM_FILE_CAPTION.format(
                    file_name='' if title is None else title, file_size='' if size is None else size, file_caption='' if f_caption is None else f_caption)
            except Exception as e:
                logger.exception(e)
                f_caption = f_caption
    if f_caption is None:
            f_caption = f"{file.file_name}"

    await app.send_message(
        f_caption.strip(),
        user_id=ctx.event.action_by_id,
        media_info=media
    )
    await m.edit_inline_markup(InlineMarkup([[
        InlineKeyboardButton("Go to PM", ctx.user.link)
    ]]))

async def show_media_results(msg: Message, search: str, offset: str, app: BotApp):
    page_size = 10
    results = []
    if '|' in search:
        string, file_type = search.split('|', maxsplit=1)
        file_type = file_int_from_name(file_type.lower().strip())
        string = string.strip()
    else:
        string = search.strip()
        file_type = None

    offset = int(offset or 0)
    files, next_offset, total = await get_search_results(string,
                                                         file_type=file_type,
                                                         max_results=page_size,
                                                         offset=offset)

    for file in files:
        title = file.file_name
        size = get_size(file.file_size)
        f_caption = file.caption
        if CUSTOM_FILE_CAPTION:
            try:
                f_caption = CUSTOM_FILE_CAPTION.format(
                    file_name='' if title is None else title, file_size='' if size is None else size, file_caption='' if f_caption is None else f_caption)
            except Exception as e:
                logger.exception(e)
                f_caption = f_caption
        if f_caption is None:
            f_caption = f"{file.file_name}"

        results.append([
            InlineKeyboardButton(
                file.description,
                callback_data=f"blk_{file.file_id}"
                #text=f'📁 Name: {f_caption} Size: {get_size(file.file_size)}\nType: {file_str_from_int(file.file_type)}',
                #url=file.file_url
                )
        ])

    if results:
        pm_text = f"📁 Results - {total}"
        if string:
            pm_text += f" for {string}"
        try:
            if int(offset) > 0 or (next_offset and int(next_offset) < int(total)):
                pagination = []
                if offset != 0:
                    pagination.append(
                        InlineKeyboardButton(
                            text="Previous Page",
                            callback_data=f"search_prev#{search}#{offset - page_size}"
                        )
                    )
                else:
                    pagination.append(
                        InlineKeyboardButton(
                            text="No previous data"
                        )
                    )

                if int(next_offset) < int(total):
                    pagination.append(
                        InlineKeyboardButton(
                            text="Next Page",
                            callback_data=f"search_next#{search}#{next_offset}"
                        )
                    )
                else:
                    pagination.append(
                        InlineKeyboardButton(
                            text="No more data"
                        )
                    )

                if len(pagination) > 0:
                    results.append(pagination)

            await msg.edit_text(pm_text, inline_markup=InlineMarkup(results))
        except Exception as e:
            logger.exception(str(e))
    else:
        if string:
            await msg.edit_text(f"❌ No Results Found for {string}")
        else:
            await msg.edit_text(f"❌ No Results Found")


async def index_files_to_db(channel_or_group: Group | Channel, is_group: bool, msg: Message, app: BotApp):
    total_files = 0
    duplicate = 0
    errors = 0
    deleted = 0
    no_media = 0
    unsupported = 0
    idx = 0
    page_size = 100
    has_more = True
    # temp.CURRENT = 200
    async with lock:
        try:
            current = temp.CURRENT
            temp.CANCEL = False
            while has_more:
                if is_group:
                    history = await app.get_group_chat_history(channel_or_group.id, channel_or_group.community_id, msg.user_id, page_size, current)
                else:
                    history = await app.get_channel_chat_history(channel_or_group.id, channel_or_group.community_id, msg.user_id, page_size, current)

                has_more = history.messages is not None and len(
                    history.messages) > 0

                if has_more:
                    messages: List[Message] = history.messages
                    for message in messages:
                        if temp.CANCEL:
                            await msg.edit_text(f"Successfully Cancelled!!\n\nSaved <code>{total_files}</code> files to dataBase!\nDuplicate Files Skipped: <code>{duplicate}</code>\nDeleted Messages Skipped: <code>{deleted}</code>\nNon-Media messages skipped: <code>{no_media + unsupported}</code>(Unsupported Media - `{unsupported}` )\nErrors Occurred: <code>{errors}</code>")
                            break
                        current += 1
                        if current % 20 == 0:
                            can = [[InlineKeyboardButton(
                                'Cancel', callback_data='index_cancel')]]
                            reply = InlineMarkup(can)
                            await msg.edit_text(
                                text=f"Total messages fetched: <code>{current}</code>\nTotal messages saved: <code>{total_files}</code>\nDuplicate Files Skipped: <code>{duplicate}</code>\nDeleted Messages Skipped: <code>{deleted}</code>\nNon-Media messages skipped: <code>{no_media + unsupported}</code>(Unsupported Media - `{unsupported}` )\nErrors Occurred: <code>{errors}</code>",
                                inline_markup=reply)
                        if not message:
                            deleted += 1
                            continue
                        elif not message.media_link:
                            no_media += 1
                            continue
                        elif message.status not in [1, 2, 3, 7]:
                            unsupported += 1
                            continue
                        media = message.media_info
                        if not media:
                            unsupported += 1
                            continue
                        aynav, vnay = await save_file(media)
                        if aynav:
                            total_files += 1
                        elif vnay == 0:
                            duplicate += 1
                        elif vnay == 2:
                            errors += 1
        except Exception as e:
            logger.exception(e)
            await msg.edit_text(f'Error: {e}')
        else:
            await msg.edit_text(f'Succesfully saved <code>{total_files}</code> to dataBase!\nDuplicate Files Skipped: <code>{duplicate}</code>\nDeleted Messages Skipped: <code>{deleted}</code>\nNon-Media messages skipped: <code>{no_media + unsupported}</code>(Unsupported Media - `{unsupported}` )\nErrors Occurred: <code>{errors}</code>')
