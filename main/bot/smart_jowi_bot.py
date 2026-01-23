"""
Smart Jowi Telegram Bot with Dynamic Admin Management
Uses aiogram for async Telegram bot operations
"""

import json
import logging
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Set
from datetime import datetime
from functools import wraps

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, CallbackQuery, 
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode

logger = logging.getLogger(__name__)


# =============================================================================
# BOT CONFIG STORAGE
# =============================================================================

class BotConfigStorage:
    """
    Stores bot configuration including:
    - Admin IDs (who can access settings)
    - Subscriber IDs (who receives notifications)
    """
    
    CONFIG_FILE = Path("bot_config.json")
    
    _cache: Optional[Dict] = None
    
    @classmethod
    def _get_default_config(cls) -> Dict:
        return {
            "admin_ids": [],  # Users who can manage settings
            "subscriber_ids": [],  # Users who receive notifications
            "settings": {
                "notify_new_orders": True,
                "notify_order_status": True,
                "notify_shift_changes": True,
            },
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
    
    @classmethod
    def _read(cls) -> Dict:
        if cls._cache is not None:
            return cls._cache
        
        try:
            if cls.CONFIG_FILE.exists():
                with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    cls._cache = json.load(f)
                    return cls._cache
        except Exception as e:
            logger.error(f"Error reading bot config: {e}")
        
        cls._cache = cls._get_default_config()
        return cls._cache
    
    @classmethod
    def _write(cls, data: Dict):
        try:
            data['updated_at'] = datetime.now().isoformat()
            with open(cls.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            cls._cache = data
        except Exception as e:
            logger.error(f"Error writing bot config: {e}")
    
    @classmethod
    def get_admin_ids(cls) -> List[int]:
        return cls._read().get('admin_ids', [])
    
    @classmethod
    def get_subscriber_ids(cls) -> List[int]:
        return cls._read().get('subscriber_ids', [])
    
    @classmethod
    def get_all_chat_ids(cls) -> List[int]:
        """Get all unique chat IDs (admins + subscribers)"""
        data = cls._read()
        all_ids = set(data.get('admin_ids', []))
        all_ids.update(data.get('subscriber_ids', []))
        return list(all_ids)
    
    @classmethod
    def is_admin(cls, user_id: int) -> bool:
        return user_id in cls.get_admin_ids()
    
    @classmethod
    def is_subscriber(cls, user_id: int) -> bool:
        return user_id in cls.get_subscriber_ids()
    
    @classmethod
    def add_admin(cls, user_id: int) -> bool:
        data = cls._read()
        if user_id not in data['admin_ids']:
            data['admin_ids'].append(user_id)
            cls._write(data)
            return True
        return False
    
    @classmethod
    def remove_admin(cls, user_id: int) -> bool:
        data = cls._read()
        if user_id in data['admin_ids']:
            data['admin_ids'].remove(user_id)
            cls._write(data)
            return True
        return False
    
    @classmethod
    def add_subscriber(cls, user_id: int) -> bool:
        data = cls._read()
        if user_id not in data['subscriber_ids']:
            data['subscriber_ids'].append(user_id)
            cls._write(data)
            return True
        return False
    
    @classmethod
    def remove_subscriber(cls, user_id: int) -> bool:
        data = cls._read()
        if user_id in data['subscriber_ids']:
            data['subscriber_ids'].remove(user_id)
            cls._write(data)
            return True
        return False
    
    @classmethod
    def get_settings(cls) -> Dict:
        return cls._read().get('settings', {})
    
    @classmethod
    def update_setting(cls, key: str, value: bool):
        data = cls._read()
        if 'settings' not in data:
            data['settings'] = {}
        data['settings'][key] = value
        cls._write(data)
    
    @classmethod
    def initialize_first_admin(cls, user_id: int):
        """Initialize first admin if no admins exist"""
        data = cls._read()
        if not data.get('admin_ids'):
            data['admin_ids'] = [user_id]
            data['subscriber_ids'] = [user_id]  # First admin is also subscriber
            cls._write(data)
            return True
        return False


# =============================================================================
# PENDING MESSAGE QUEUE (for offline support)
# =============================================================================

class PendingMessageQueue:
    """Queue for messages that failed to send (offline support)"""
    
    QUEUE_FILE = Path("pending_bot_messages.json")
    
    @classmethod
    def _read(cls) -> List[Dict]:
        try:
            if cls.QUEUE_FILE.exists():
                with open(cls.QUEUE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f) or []
        except:
            pass
        return []
    
    @classmethod
    def _write(cls, data: List[Dict]):
        with open(cls.QUEUE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def add(cls, chat_ids: List[int], message: str, sticker_id: str = None):
        queue = cls._read()
        queue.append({
            "chat_ids": chat_ids,
            "message": message,
            "sticker_id": sticker_id,
            "created_at": datetime.now().isoformat()
        })
        cls._write(queue)
    
    @classmethod
    def get_all(cls) -> List[Dict]:
        return cls._read()
    
    @classmethod
    def clear(cls):
        cls._write([])
    
    @classmethod
    def remove_first(cls, count: int):
        queue = cls._read()
        cls._write(queue[count:])
    
    @classmethod
    def count(cls) -> int:
        return len(cls._read())


# =============================================================================
# FSM STATES
# =============================================================================

class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_remove_id = State()
    confirm_remove = State()


# =============================================================================
# KEYBOARDS
# =============================================================================

def get_main_keyboard(is_admin: bool) -> ReplyKeyboardMarkup:
    """Get main keyboard based on user role"""
    buttons = [
        [KeyboardButton(text="📊 Status"), KeyboardButton(text="ℹ️ Info")]
    ]
    
    if is_admin:
        buttons.append([KeyboardButton(text="⚙️ Settings")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Settings menu keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Manage Subscribers", callback_data="manage_subscribers")],
        [InlineKeyboardButton(text="👑 Manage Admins", callback_data="manage_admins")],
        [InlineKeyboardButton(text="🔔 Notification Settings", callback_data="notification_settings")],
        [InlineKeyboardButton(text="📋 View All Users", callback_data="view_users")],
        [InlineKeyboardButton(text="❌ Close", callback_data="close_settings")],
    ])


def get_subscriber_management_keyboard() -> InlineKeyboardMarkup:
    """Subscriber management keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Subscriber", callback_data="add_subscriber")],
        [InlineKeyboardButton(text="➖ Remove Subscriber", callback_data="remove_subscriber")],
        [InlineKeyboardButton(text="📋 List Subscribers", callback_data="list_subscribers")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_settings")],
    ])


def get_admin_management_keyboard() -> InlineKeyboardMarkup:
    """Admin management keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Admin", callback_data="add_admin")],
        [InlineKeyboardButton(text="➖ Remove Admin", callback_data="remove_admin")],
        [InlineKeyboardButton(text="📋 List Admins", callback_data="list_admins")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_settings")],
    ])


def get_notification_settings_keyboard() -> InlineKeyboardMarkup:
    """Notification settings keyboard"""
    settings = BotConfigStorage.get_settings()
    
    def status_emoji(key: str) -> str:
        return "✅" if settings.get(key, True) else "❌"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{status_emoji('notify_new_orders')} New Orders",
            callback_data="toggle_notify_new_orders"
        )],
        [InlineKeyboardButton(
            text=f"{status_emoji('notify_order_status')} Order Status Changes",
            callback_data="toggle_notify_order_status"
        )],
        [InlineKeyboardButton(
            text=f"{status_emoji('notify_shift_changes')} Shift Changes",
            callback_data="toggle_notify_shift_changes"
        )],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_settings")],
    ])


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_action")],
    ])


# =============================================================================
# BOT CLASS
# =============================================================================

class SmartJowiBot:
    """Main bot class with all handlers"""
    
    def __init__(self, token: str):
        self.token = token
        self.bot = Bot(token=token)
        self.storage = MemoryStorage()
        self.dp = Dispatcher(storage=self.storage)
        self.router = Router()
        
        self._setup_handlers()
        self.dp.include_router(self.router)
    
    def _setup_handlers(self):
        """Register all handlers"""
        
        # Command handlers
        self.router.message.register(self.cmd_start, Command("start"))
        self.router.message.register(self.cmd_help, Command("help"))
        self.router.message.register(self.cmd_status, Command("status"))
        
        # Text button handlers
        self.router.message.register(self.btn_settings, F.text == "⚙️ Settings")
        self.router.message.register(self.btn_status, F.text == "📊 Status")
        self.router.message.register(self.btn_info, F.text == "ℹ️ Info")
        
        # Callback handlers
        self.router.callback_query.register(self.cb_manage_subscribers, F.data == "manage_subscribers")
        self.router.callback_query.register(self.cb_manage_admins, F.data == "manage_admins")
        self.router.callback_query.register(self.cb_notification_settings, F.data == "notification_settings")
        self.router.callback_query.register(self.cb_view_users, F.data == "view_users")
        self.router.callback_query.register(self.cb_close_settings, F.data == "close_settings")
        self.router.callback_query.register(self.cb_back_to_settings, F.data == "back_to_settings")
        
        # Subscriber management
        self.router.callback_query.register(self.cb_add_subscriber, F.data == "add_subscriber")
        self.router.callback_query.register(self.cb_remove_subscriber, F.data == "remove_subscriber")
        self.router.callback_query.register(self.cb_list_subscribers, F.data == "list_subscribers")
        
        # Admin management
        self.router.callback_query.register(self.cb_add_admin, F.data == "add_admin")
        self.router.callback_query.register(self.cb_remove_admin, F.data == "remove_admin")
        self.router.callback_query.register(self.cb_list_admins, F.data == "list_admins")
        
        # Toggle notifications
        self.router.callback_query.register(
            self.cb_toggle_notification, 
            F.data.startswith("toggle_")
        )
        
        # Cancel action
        self.router.callback_query.register(self.cb_cancel_action, F.data == "cancel_action")
        
        # State handlers
        self.router.message.register(
            self.handle_user_id_input,
            StateFilter(AdminStates.waiting_for_user_id)
        )
        self.router.message.register(
            self.handle_remove_id_input,
            StateFilter(AdminStates.waiting_for_remove_id)
        )
    
    # =========================================================================
    # COMMAND HANDLERS
    # =========================================================================
    
    async def cmd_start(self, message: Message):
        """Handle /start command"""
        user_id = message.from_user.id
        user_name = message.from_user.full_name
        
        # Initialize first admin if no admins exist
        is_first_admin = BotConfigStorage.initialize_first_admin(user_id)
        is_admin = BotConfigStorage.is_admin(user_id)
        
        if is_first_admin:
            text = (
                f"👋 Salom, <b>{user_name}</b>!\n\n"
                f"Siz birinchi admin sifatida ro'yxatdan o'tdingiz!\n\n"
                f"Bot orqali quyidagilarni qilishingiz mumkin:\n"
                f"• Buyurtmalar haqida xabar olish\n"
                f"• Smena hisobotlarini ko'rish\n"
                f"• Boshqa foydalanuvchilarni qo'shish\n\n"
                f"⚙️ <b>Settings</b> tugmasini bosing sozlamalarni ko'rish uchun."
            )
        elif is_admin:
            text = (
                f"👋 Salom, <b>{user_name}</b>!\n\n"
                f"Siz admin sifatida tizimga kirdingiz.\n"
                f"⚙️ <b>Settings</b> tugmasini bosing sozlamalarni boshqarish uchun."
            )
        else:
            # Regular user - add as subscriber request
            text = (
                f"👋 Salom, <b>{user_name}</b>!\n\n"
                f"Bu Smart Jowi POS tizimining botiga xush kelibsiz.\n\n"
                f"Sizning ID: <code>{user_id}</code>\n\n"
                f"Xabarlar olish uchun admindan so'rang sizni subscriber qilib qo'yishini."
            )
        
        await message.answer(text, reply_markup=get_main_keyboard(is_admin))
    
    async def cmd_help(self, message: Message):
        """Handle /help command"""
        is_admin = BotConfigStorage.is_admin(message.from_user.id)
        
        text = (
            "<b>📖 Yordam</b>\n\n"
            "<b>Asosiy buyruqlar:</b>\n"
            "/start - Botni ishga tushirish\n"
            "/status - Tizim holati\n"
            "/help - Yordam\n\n"
        )
        
        if is_admin:
            text += (
                "<b>Admin buyruqlari:</b>\n"
                "⚙️ Settings - Sozlamalarni boshqarish\n"
                "• Subscriber qo'shish/o'chirish\n"
                "• Admin qo'shish/o'chirish\n"
                "• Bildirishnoma sozlamalari\n"
            )
        
        await message.answer(text)
    
    async def cmd_status(self, message: Message):
        """Handle /status command"""
        await self.btn_status(message)
    
    # =========================================================================
    # TEXT BUTTON HANDLERS
    # =========================================================================
    
    async def btn_settings(self, message: Message):
        """Handle Settings button"""
        if not BotConfigStorage.is_admin(message.from_user.id):
            await message.answer("⛔ Siz admin emassiz!")
            return
        
        text = (
            "<b>⚙️ Sozlamalar</b>\n\n"
            "Quyidagi bo'limlardan birini tanlang:"
        )
        await message.answer(text, reply_markup=get_settings_keyboard())
    
    async def btn_status(self, message: Message):
        """Handle Status button"""
        admins = BotConfigStorage.get_admin_ids()
        subscribers = BotConfigStorage.get_subscriber_ids()
        settings = BotConfigStorage.get_settings()
        pending = PendingMessageQueue.count()
        
        def bool_emoji(val: bool) -> str:
            return "✅" if val else "❌"
        
        text = (
            "<b>📊 Tizim Holati</b>\n\n"
            f"<b>Foydalanuvchilar:</b>\n"
            f"• Adminlar: {len(admins)}\n"
            f"• Subscriberlar: {len(subscribers)}\n\n"
            f"<b>Bildirishnomalar:</b>\n"
            f"• Yangi buyurtmalar: {bool_emoji(settings.get('notify_new_orders', True))}\n"
            f"• Status o'zgarishi: {bool_emoji(settings.get('notify_order_status', True))}\n"
            f"• Smena o'zgarishi: {bool_emoji(settings.get('notify_shift_changes', True))}\n\n"
            f"<b>Kutilayotgan xabarlar:</b> {pending}"
        )
        await message.answer(text)
    
    async def btn_info(self, message: Message):
        """Handle Info button"""
        user_id = message.from_user.id
        is_admin = BotConfigStorage.is_admin(user_id)
        is_subscriber = BotConfigStorage.is_subscriber(user_id)
        
        role = "👑 Admin" if is_admin else ("📨 Subscriber" if is_subscriber else "👤 Guest")
        
        text = (
            "<b>ℹ️ Ma'lumot</b>\n\n"
            f"<b>Sizning ID:</b> <code>{user_id}</code>\n"
            f"<b>Ism:</b> {message.from_user.full_name}\n"
            f"<b>Username:</b> @{message.from_user.username or 'yo\'q'}\n"
            f"<b>Rol:</b> {role}\n\n"
            f"<b>Bot versiyasi:</b> 1.0.0\n"
            f"<b>Smart Jowi POS</b>"
        )
        await message.answer(text)
    
    # =========================================================================
    # CALLBACK HANDLERS
    # =========================================================================
    
    async def cb_manage_subscribers(self, callback: CallbackQuery):
        """Manage subscribers menu"""
        await callback.message.edit_text(
            "<b>👥 Subscriberlarni Boshqarish</b>\n\n"
            "Subscriberlar buyurtmalar va smena haqida xabar oladi.",
            reply_markup=get_subscriber_management_keyboard()
        )
        await callback.answer()
    
    async def cb_manage_admins(self, callback: CallbackQuery):
        """Manage admins menu"""
        await callback.message.edit_text(
            "<b>👑 Adminlarni Boshqarish</b>\n\n"
            "Adminlar botni to'liq boshqara oladi.",
            reply_markup=get_admin_management_keyboard()
        )
        await callback.answer()
    
    async def cb_notification_settings(self, callback: CallbackQuery):
        """Notification settings menu"""
        await callback.message.edit_text(
            "<b>🔔 Bildirishnoma Sozlamalari</b>\n\n"
            "Qaysi bildirishnomalarni olishni tanlang:",
            reply_markup=get_notification_settings_keyboard()
        )
        await callback.answer()
    
    async def cb_view_users(self, callback: CallbackQuery):
        """View all users"""
        admins = BotConfigStorage.get_admin_ids()
        subscribers = BotConfigStorage.get_subscriber_ids()
        
        text = "<b>📋 Barcha Foydalanuvchilar</b>\n\n"
        
        text += "<b>👑 Adminlar:</b>\n"
        if admins:
            for i, uid in enumerate(admins, 1):
                text += f"{i}. <code>{uid}</code>\n"
        else:
            text += "Yo'q\n"
        
        text += "\n<b>📨 Subscriberlar:</b>\n"
        if subscribers:
            for i, uid in enumerate(subscribers, 1):
                marker = " 👑" if uid in admins else ""
                text += f"{i}. <code>{uid}</code>{marker}\n"
        else:
            text += "Yo'q\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_settings")]
            ])
        )
        await callback.answer()
    
    async def cb_close_settings(self, callback: CallbackQuery):
        """Close settings menu"""
        await callback.message.delete()
        await callback.answer("Sozlamalar yopildi")
    
    async def cb_back_to_settings(self, callback: CallbackQuery):
        """Return to main settings menu"""
        await callback.message.edit_text(
            "<b>⚙️ Sozlamalar</b>\n\n"
            "Quyidagi bo'limlardan birini tanlang:",
            reply_markup=get_settings_keyboard()
        )
        await callback.answer()
    
    # =========================================================================
    # SUBSCRIBER MANAGEMENT
    # =========================================================================
    
    async def cb_add_subscriber(self, callback: CallbackQuery, state: FSMContext):
        """Start adding subscriber"""
        await state.set_state(AdminStates.waiting_for_user_id)
        await state.update_data(action="add_subscriber")
        
        await callback.message.edit_text(
            "<b>➕ Subscriber Qo'shish</b>\n\n"
            "Foydalanuvchi ID raqamini yuboring:\n\n"
            "<i>Masalan: 123456789</i>\n\n"
            "💡 Foydalanuvchi o'z ID sini /start buyrug'i orqali bilishi mumkin.",
            reply_markup=get_cancel_keyboard()
        )
        await callback.answer()
    
    async def cb_remove_subscriber(self, callback: CallbackQuery, state: FSMContext):
        """Start removing subscriber"""
        subscribers = BotConfigStorage.get_subscriber_ids()
        
        if not subscribers:
            await callback.answer("Hech qanday subscriber yo'q!", show_alert=True)
            return
        
        await state.set_state(AdminStates.waiting_for_remove_id)
        await state.update_data(action="remove_subscriber")
        
        text = "<b>➖ Subscriber O'chirish</b>\n\n"
        text += "Mavjud subscriberlar:\n"
        for i, uid in enumerate(subscribers, 1):
            text += f"{i}. <code>{uid}</code>\n"
        text += "\nO'chirmoqchi bo'lgan ID ni yuboring:"
        
        await callback.message.edit_text(text, reply_markup=get_cancel_keyboard())
        await callback.answer()
    
    async def cb_list_subscribers(self, callback: CallbackQuery):
        """List all subscribers"""
        subscribers = BotConfigStorage.get_subscriber_ids()
        
        if not subscribers:
            text = "<b>📋 Subscriberlar</b>\n\nHech kim yo'q."
        else:
            text = f"<b>📋 Subscriberlar ({len(subscribers)})</b>\n\n"
            for i, uid in enumerate(subscribers, 1):
                text += f"{i}. <code>{uid}</code>\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=get_subscriber_management_keyboard()
        )
        await callback.answer()
    
    # =========================================================================
    # ADMIN MANAGEMENT
    # =========================================================================
    
    async def cb_add_admin(self, callback: CallbackQuery, state: FSMContext):
        """Start adding admin"""
        await state.set_state(AdminStates.waiting_for_user_id)
        await state.update_data(action="add_admin")
        
        await callback.message.edit_text(
            "<b>➕ Admin Qo'shish</b>\n\n"
            "Foydalanuvchi ID raqamini yuboring:\n\n"
            "<i>Masalan: 123456789</i>",
            reply_markup=get_cancel_keyboard()
        )
        await callback.answer()
    
    async def cb_remove_admin(self, callback: CallbackQuery, state: FSMContext):
        """Start removing admin"""
        admins = BotConfigStorage.get_admin_ids()
        
        if len(admins) <= 1:
            await callback.answer("Oxirgi adminni o'chirish mumkin emas!", show_alert=True)
            return
        
        await state.set_state(AdminStates.waiting_for_remove_id)
        await state.update_data(action="remove_admin")
        
        text = "<b>➖ Admin O'chirish</b>\n\n"
        text += "Mavjud adminlar:\n"
        for i, uid in enumerate(admins, 1):
            text += f"{i}. <code>{uid}</code>\n"
        text += "\nO'chirmoqchi bo'lgan ID ni yuboring:"
        
        await callback.message.edit_text(text, reply_markup=get_cancel_keyboard())
        await callback.answer()
    
    async def cb_list_admins(self, callback: CallbackQuery):
        """List all admins"""
        admins = BotConfigStorage.get_admin_ids()
        
        text = f"<b>📋 Adminlar ({len(admins)})</b>\n\n"
        for i, uid in enumerate(admins, 1):
            text += f"{i}. <code>{uid}</code>\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=get_admin_management_keyboard()
        )
        await callback.answer()
    
    # =========================================================================
    # NOTIFICATION TOGGLE
    # =========================================================================
    
    async def cb_toggle_notification(self, callback: CallbackQuery):
        """Toggle notification setting"""
        setting_key = callback.data.replace("toggle_", "")
        settings = BotConfigStorage.get_settings()
        
        new_value = not settings.get(setting_key, True)
        BotConfigStorage.update_setting(setting_key, new_value)
        
        await callback.message.edit_reply_markup(
            reply_markup=get_notification_settings_keyboard()
        )
        
        status = "yoqildi ✅" if new_value else "o'chirildi ❌"
        await callback.answer(f"Sozlama {status}")
    
    # =========================================================================
    # CANCEL ACTION
    # =========================================================================
    
    async def cb_cancel_action(self, callback: CallbackQuery, state: FSMContext):
        """Cancel current action"""
        await state.clear()
        await callback.message.edit_text(
            "<b>⚙️ Sozlamalar</b>\n\n"
            "Quyidagi bo'limlardan birini tanlang:",
            reply_markup=get_settings_keyboard()
        )
        await callback.answer("Bekor qilindi")
    
    # =========================================================================
    # STATE HANDLERS
    # =========================================================================
    
    async def handle_user_id_input(self, message: Message, state: FSMContext):
        """Handle user ID input for adding"""
        data = await state.get_data()
        action = data.get("action")
        
        try:
            user_id = int(message.text.strip())
        except ValueError:
            await message.answer(
                "❌ Noto'g'ri format!\n\n"
                "Faqat raqam yuboring.\n"
                "Masalan: <code>123456789</code>",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        await state.clear()
        
        if action == "add_subscriber":
            success = BotConfigStorage.add_subscriber(user_id)
            if success:
                await message.answer(
                    f"✅ Subscriber qo'shildi!\n\nID: <code>{user_id}</code>",
                    reply_markup=get_main_keyboard(True)
                )
                # Try to notify the new subscriber
                try:
                    await self.bot.send_message(
                        user_id,
                        "🎉 Siz Smart Jowi botiga subscriber qilib qo'shildingiz!\n"
                        "Endi buyurtmalar haqida xabar olasiz."
                    )
                except:
                    pass
            else:
                await message.answer(
                    f"ℹ️ Bu foydalanuvchi allaqachon subscriber.\n\nID: <code>{user_id}</code>",
                    reply_markup=get_main_keyboard(True)
                )
        
        elif action == "add_admin":
            success = BotConfigStorage.add_admin(user_id)
            # Also add as subscriber
            BotConfigStorage.add_subscriber(user_id)
            
            if success:
                await message.answer(
                    f"✅ Admin qo'shildi!\n\nID: <code>{user_id}</code>",
                    reply_markup=get_main_keyboard(True)
                )
                # Notify new admin
                try:
                    await self.bot.send_message(
                        user_id,
                        "👑 Siz Smart Jowi botiga admin qilib qo'shildingiz!\n"
                        "/start buyrug'ini yuboring."
                    )
                except:
                    pass
            else:
                await message.answer(
                    f"ℹ️ Bu foydalanuvchi allaqachon admin.\n\nID: <code>{user_id}</code>",
                    reply_markup=get_main_keyboard(True)
                )
    
    async def handle_remove_id_input(self, message: Message, state: FSMContext):
        """Handle user ID input for removing"""
        data = await state.get_data()
        action = data.get("action")
        
        try:
            user_id = int(message.text.strip())
        except ValueError:
            await message.answer(
                "❌ Noto'g'ri format!\n\nFaqat raqam yuboring.",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        await state.clear()
        
        if action == "remove_subscriber":
            success = BotConfigStorage.remove_subscriber(user_id)
            if success:
                await message.answer(
                    f"✅ Subscriber o'chirildi!\n\nID: <code>{user_id}</code>",
                    reply_markup=get_main_keyboard(True)
                )
            else:
                await message.answer(
                    f"❌ Bu ID subscriber emas.\n\nID: <code>{user_id}</code>",
                    reply_markup=get_main_keyboard(True)
                )
        
        elif action == "remove_admin":
            if user_id == message.from_user.id:
                await message.answer(
                    "❌ O'zingizni o'chira olmaysiz!",
                    reply_markup=get_main_keyboard(True)
                )
                return
            
            success = BotConfigStorage.remove_admin(user_id)
            if success:
                await message.answer(
                    f"✅ Admin o'chirildi!\n\nID: <code>{user_id}</code>",
                    reply_markup=get_main_keyboard(True)
                )
            else:
                await message.answer(
                    f"❌ Bu ID admin emas.\n\nID: <code>{user_id}</code>",
                    reply_markup=get_main_keyboard(True)
                )
    
    # =========================================================================
    # MESSAGE SENDING (for external use)
    # =========================================================================
    
    async def send_to_subscribers(self, message: str, sticker_id: str = None) -> Dict:
        """Send message to all subscribers"""
        subscribers = BotConfigStorage.get_subscriber_ids()
        
        if not subscribers:
            return {"success": False, "message": "No subscribers"}
        
        sent = 0
        failed = 0
        
        for chat_id in subscribers:
            try:
                if sticker_id:
                    await self.bot.send_sticker(chat_id, sticker_id)
                await self.bot.send_message(chat_id, message)
                sent += 1
            except Exception as e:
                logger.warning(f"Failed to send to {chat_id}: {e}")
                failed += 1
        
        if failed == len(subscribers):
            # All failed - queue for later
            PendingMessageQueue.add(subscribers, message, sticker_id)
            return {"success": False, "message": "All failed, queued"}
        
        return {
            "success": True,
            "sent": sent,
            "failed": failed
        }
    
    async def process_pending_messages(self) -> tuple[int, int]:
        """Process pending messages queue"""
        pending = PendingMessageQueue.get_all()
        
        if not pending:
            return 0, 0
        
        sent = 0
        
        for item in pending:
            try:
                for chat_id in item['chat_ids']:
                    if item.get('sticker_id'):
                        await self.bot.send_sticker(chat_id, item['sticker_id'])
                    await self.bot.send_message(chat_id, item['message'])
                sent += 1
            except:
                break
        
        if sent > 0:
            PendingMessageQueue.remove_first(sent)
        
        return sent, len(pending) - sent
    
    # =========================================================================
    # RUN BOT
    # =========================================================================
    
    async def start(self):
        """Start the bot"""
        logger.info("Starting Smart Jowi Bot...")
        await self.dp.start_polling(self.bot)
    
    async def stop(self):
        """Stop the bot"""
        await self.bot.session.close()


# =============================================================================
# HELPER FOR EXTERNAL SERVICES
# =============================================================================

def get_chat_ids() -> List[int]:
    """Get all subscriber chat IDs (for backward compatibility)"""
    return BotConfigStorage.get_subscriber_ids()


def is_notification_enabled(notification_type: str) -> bool:
    """Check if notification type is enabled"""
    settings = BotConfigStorage.get_settings()
    key = f"notify_{notification_type}"
    return settings.get(key, True)
