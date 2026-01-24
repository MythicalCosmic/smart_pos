import json
import logging
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode

logger = logging.getLogger(__name__)

ADMIN_ID = 6589960007

MSG_NOT_AUTHORIZED = "⛔ You are not part of this system."
MSG_WELCOME_ADMIN = "👋 Welcome, <b>{name}</b>!\n\nYou are the super admin.\nUse ⚙️ <b>Settings</b> to manage users."
MSG_STATUS_TITLE = "<b>📊 System Status</b>\n\n"
MSG_STATUS_USERS = "<b>Users:</b> {count}\n"
MSG_STATUS_PENDING = "<b>Pending Messages:</b> {pending}"
MSG_INFO_TITLE = "<b>ℹ️ Information</b>\n\n"
MSG_INFO_BODY = "<b>Your ID:</b> <code>{user_id}</code>\n<b>Name:</b> {name}\n<b>Role:</b> {role}\n\n<b>Smart Jowi POS Bot v1.0</b>"
MSG_SETTINGS_TITLE = "<b>⚙️ Settings</b>\n\nSelect an option:"
MSG_USERS_TITLE = "<b>👥 Manage Users</b>\n\nUsers receive order and shift notifications."
MSG_ADD_USER_PROMPT = "<b>➕ Add User</b>\n\nSend the user's Telegram ID:\n\n<i>Example: 123456789</i>"
MSG_REMOVE_USER_PROMPT = "<b>➖ Remove User</b>\n\nCurrent users:\n{list}\n\nSend the ID to remove:"
MSG_USER_ADDED = "✅ User added!\n\nID: <code>{user_id}</code>"
MSG_USER_ADDED_NOTIFIED = "✅ User added and notified!\n\nID: <code>{user_id}</code>"
MSG_USER_ADDED_NOT_NOTIFIED = "✅ User added but could not notify them.\n\nID: <code>{user_id}</code>"
MSG_USER_EXISTS = "ℹ️ This user is already added.\n\nID: <code>{user_id}</code>"
MSG_USER_REMOVED = "✅ User removed!\n\nID: <code>{user_id}</code>"
MSG_USER_NOT_FOUND = "❌ This ID is not in the list.\n\nID: <code>{user_id}</code>"
MSG_NO_USERS = "No users yet."
MSG_USERS_LIST = "<b>📋 Users ({count})</b>\n\n{list}"
MSG_INVALID_ID = "❌ Invalid format!\n\nSend only numbers.\nExample: <code>123456789</code>"
MSG_CANCELLED = "Cancelled"
MSG_SETTINGS_CLOSED = "Settings closed"
MSG_VIEW_USERS_TITLE = "<b>📋 All Users</b>\n\n"
MSG_ADMIN_SECTION = "<b>👑 Super Admin:</b>\n<code>{admin_id}</code>\n\n"
MSG_USERS_SECTION = "<b>📨 Users:</b>\n{list}"
MSG_NEW_USER_NOTIFICATION = "🎉 You have been added to Smart Jowi Bot!\nYou will now receive order notifications."
MSG_UNKNOWN_COMMAND = "❓ Unknown command."

CONFIG_FILE = Path("data/bot_config.json")


def _get_default_config() -> Dict:
    return {
        "user_ids": [],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }


def _read_config() -> Dict:
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error reading bot config: {e}")
    return _get_default_config()


def _write_config(data: Dict):
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        data['updated_at'] = datetime.now().isoformat()
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Config saved: {data}")
    except Exception as e:
        logger.error(f"Error writing bot config: {e}")


def get_user_ids() -> List[int]:
    return _read_config().get('user_ids', [])


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def add_user(user_id: int) -> bool:
    data = _read_config()
    if 'user_ids' not in data:
        data['user_ids'] = []
    if user_id not in data['user_ids']:
        data['user_ids'].append(user_id)
        _write_config(data)
        return True
    return False


def remove_user(user_id: int) -> bool:
    data = _read_config()
    if 'user_ids' not in data:
        data['user_ids'] = []
    if user_id in data['user_ids']:
        data['user_ids'].remove(user_id)
        _write_config(data)
        return True
    return False


def get_all_chat_ids() -> List[int]:
    users = get_user_ids()
    all_ids = [ADMIN_ID]
    for uid in users:
        if uid not in all_ids:
            all_ids.append(uid)
    return all_ids


class AdminStates(StatesGroup):
    waiting_for_add_id = State()
    waiting_for_remove_id = State()


def get_admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Status"), KeyboardButton(text="ℹ️ Info")],
            [KeyboardButton(text="⚙️ Settings")]
        ],
        resize_keyboard=True
    )


def get_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Manage Users", callback_data="manage_users")],
        [InlineKeyboardButton(text="📋 View All Users", callback_data="view_users")],
        [InlineKeyboardButton(text="❌ Close", callback_data="close_settings")],
    ])


def get_user_management_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add User", callback_data="add_user")],
        [InlineKeyboardButton(text="➖ Remove User", callback_data="remove_user")],
        [InlineKeyboardButton(text="📋 List Users", callback_data="list_users")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_settings")],
    ])


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_action")],
    ])


def get_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_settings")],
    ])


class SmartJowiBot:
    def __init__(self, token: str):
        self.token = token
        self.bot = Bot(token=token)
        self.storage = MemoryStorage()
        self.dp = Dispatcher(storage=self.storage)
        self.router = Router()
        self._setup_handlers()
        self.dp.include_router(self.router)

    def _setup_handlers(self):
        self.router.message.register(self.cmd_start, Command("start"))
        self.router.message.register(self.btn_settings, F.text == "⚙️ Settings")
        self.router.message.register(self.btn_status, F.text == "📊 Status")
        self.router.message.register(self.btn_info, F.text == "ℹ️ Info")
        self.router.callback_query.register(self.cb_manage_users, F.data == "manage_users")
        self.router.callback_query.register(self.cb_view_users, F.data == "view_users")
        self.router.callback_query.register(self.cb_close_settings, F.data == "close_settings")
        self.router.callback_query.register(self.cb_back_to_settings, F.data == "back_to_settings")
        self.router.callback_query.register(self.cb_add_user, F.data == "add_user")
        self.router.callback_query.register(self.cb_remove_user, F.data == "remove_user")
        self.router.callback_query.register(self.cb_list_users, F.data == "list_users")
        self.router.callback_query.register(self.cb_cancel_action, F.data == "cancel_action")
        self.router.message.register(self.handle_add_id, StateFilter(AdminStates.waiting_for_add_id))
        self.router.message.register(self.handle_remove_id, StateFilter(AdminStates.waiting_for_remove_id))
        self.router.message.register(self.handle_unknown)

    async def cmd_start(self, message: Message):
        user_id = message.from_user.id
        user_name = message.from_user.full_name
        if is_admin(user_id):
            text = MSG_WELCOME_ADMIN.format(name=user_name)
            await message.answer(text, reply_markup=get_admin_keyboard(), parse_mode=ParseMode.HTML)
            return

    async def btn_status(self, message: Message):
        if not is_admin(message.from_user.id):
            return
        users = get_user_ids()
        text = MSG_STATUS_TITLE
        text += MSG_STATUS_USERS.format(count=len(users))
        text += MSG_STATUS_PENDING.format(pending=0)
        await message.answer(text, parse_mode=ParseMode.HTML)

    async def btn_info(self, message: Message):
        if not is_admin(message.from_user.id):
            return
        text = MSG_INFO_TITLE + MSG_INFO_BODY.format(
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            role="👑 Super Admin"
        )
        await message.answer(text, parse_mode=ParseMode.HTML)

    async def btn_settings(self, message: Message):
        if not is_admin(message.from_user.id):
            return
        await message.answer(MSG_SETTINGS_TITLE, reply_markup=get_settings_keyboard(), parse_mode=ParseMode.HTML)

    async def cb_manage_users(self, callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer()
            return
        await callback.message.edit_text(MSG_USERS_TITLE, reply_markup=get_user_management_keyboard(), parse_mode=ParseMode.HTML)
        await callback.answer()

    async def cb_view_users(self, callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer()
            return
        users = get_user_ids()
        text = MSG_VIEW_USERS_TITLE
        text += MSG_ADMIN_SECTION.format(admin_id=ADMIN_ID)
        if users:
            user_list = "\n".join([f"{i}. <code>{uid}</code>" for i, uid in enumerate(users, 1)])
        else:
            user_list = MSG_NO_USERS
        text += MSG_USERS_SECTION.format(list=user_list)
        await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode=ParseMode.HTML)
        await callback.answer()

    async def cb_close_settings(self, callback: CallbackQuery):
        await callback.message.delete()
        await callback.answer(MSG_SETTINGS_CLOSED)

    async def cb_back_to_settings(self, callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer()
            return
        await callback.message.edit_text(MSG_SETTINGS_TITLE, reply_markup=get_settings_keyboard(), parse_mode=ParseMode.HTML)
        await callback.answer()

    async def cb_add_user(self, callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminStates.waiting_for_add_id)
        await callback.message.edit_text(MSG_ADD_USER_PROMPT, reply_markup=get_cancel_keyboard(), parse_mode=ParseMode.HTML)
        await callback.answer()

    async def cb_remove_user(self, callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            await callback.answer()
            return
        users = get_user_ids()
        if not users:
            await callback.answer(MSG_NO_USERS, show_alert=True)
            return
        await state.set_state(AdminStates.waiting_for_remove_id)
        user_list = "\n".join([f"{i}. <code>{uid}</code>" for i, uid in enumerate(users, 1)])
        text = MSG_REMOVE_USER_PROMPT.format(list=user_list)
        await callback.message.edit_text(text, reply_markup=get_cancel_keyboard(), parse_mode=ParseMode.HTML)
        await callback.answer()

    async def cb_list_users(self, callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer()
            return
        users = get_user_ids()
        if not users:
            text = MSG_USERS_LIST.format(count=0, list=MSG_NO_USERS)
        else:
            user_list = "\n".join([f"{i}. <code>{uid}</code>" for i, uid in enumerate(users, 1)])
            text = MSG_USERS_LIST.format(count=len(users), list=user_list)
        await callback.message.edit_text(text, reply_markup=get_user_management_keyboard(), parse_mode=ParseMode.HTML)
        await callback.answer()

    async def cb_cancel_action(self, callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.message.edit_text(MSG_SETTINGS_TITLE, reply_markup=get_settings_keyboard(), parse_mode=ParseMode.HTML)
        await callback.answer(MSG_CANCELLED)

    async def handle_add_id(self, message: Message, state: FSMContext):
        if not is_admin(message.from_user.id):
            await state.clear()
            return
        try:
            user_id = int(message.text.strip())
        except ValueError:
            await message.answer(MSG_INVALID_ID, parse_mode=ParseMode.HTML)
            return
        await state.clear()
        success = add_user(user_id)
        if success:
            notified = False
            try:
                await self.bot.send_message(user_id, MSG_NEW_USER_NOTIFICATION, parse_mode=ParseMode.HTML)
                notified = True
            except:
                pass
            if notified:
                await message.answer(MSG_USER_ADDED_NOTIFIED.format(user_id=user_id), reply_markup=get_admin_keyboard(), parse_mode=ParseMode.HTML)
            else:
                await message.answer(MSG_USER_ADDED_NOT_NOTIFIED.format(user_id=user_id), reply_markup=get_admin_keyboard(), parse_mode=ParseMode.HTML)
        else:
            await message.answer(MSG_USER_EXISTS.format(user_id=user_id), reply_markup=get_admin_keyboard(), parse_mode=ParseMode.HTML)

    async def handle_remove_id(self, message: Message, state: FSMContext):
        if not is_admin(message.from_user.id):
            await state.clear()
            return
        try:
            user_id = int(message.text.strip())
        except ValueError:
            await message.answer(MSG_INVALID_ID, parse_mode=ParseMode.HTML)
            return
        await state.clear()
        success = remove_user(user_id)
        if success:
            await message.answer(MSG_USER_REMOVED.format(user_id=user_id), reply_markup=get_admin_keyboard(), parse_mode=ParseMode.HTML)
        else:
            await message.answer(MSG_USER_NOT_FOUND.format(user_id=user_id), reply_markup=get_admin_keyboard(), parse_mode=ParseMode.HTML)

    async def handle_unknown(self, message: Message):
        if not message.text:
            return
        if not message.from_user:
            return
        if message.from_user.is_bot:
            return
        user_id = message.from_user.id
        if is_admin(user_id):
            await message.answer(MSG_UNKNOWN_COMMAND, reply_markup=get_admin_keyboard(), parse_mode=ParseMode.HTML)
            return

    async def send_to_all(self, text: str, sticker_id: str = None) -> Dict:
        chat_ids = get_all_chat_ids()
        if not chat_ids:
            return {"success": False, "sent": 0, "failed": 0}
        sent = 0
        failed = 0
        for chat_id in chat_ids:
            try:
                if sticker_id:
                    await self.bot.send_sticker(chat_id, sticker_id)
                await self.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
                sent += 1
            except Exception as e:
                logger.warning(f"Failed to send to {chat_id}: {e}")
                failed += 1
        return {"success": sent > 0, "sent": sent, "failed": failed}

    async def start(self):
        logger.info("Starting Smart Jowi Bot...")
        try:
            await self.dp.start_polling(self.bot)
        except Exception as e:
            logger.error(f"Bot error: {e}")

    async def stop(self):
        await self.bot.session.close()


def get_chat_ids() -> List[int]:
    return get_all_chat_ids()


def is_notification_enabled(notification_type: str) -> bool:
    return True