import json
import logging
import requests
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional, Tuple, List
from dataclasses import dataclass
from smart_jowi.settings import BOT_TOKEN, CHAT_IDS, STICKERS, UZB_TZ, SESSION_FILE, PENDING_FILE 

from django.db.models import Sum

logger = logging.getLogger(__name__)


def get_uzb_time() -> datetime:
    return datetime.now(UZB_TZ)


def format_uzb_datetime(dt: datetime = None) -> tuple[str, str]:
    if dt is None:
        dt = get_uzb_time()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=UZB_TZ)
    else:
        dt = dt.astimezone(UZB_TZ)
    return dt.strftime('%Y-%m-%d'), dt.strftime('%H:%M:%S')


class TelegramService:
    
    @staticmethod
    def send_message(text: str) -> tuple[bool, Optional[str]]:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        
        all_success = True
        last_error = None
        
        for chat_id in CHAT_IDS:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            
            try:
                response = requests.post(url, json=payload, timeout=10)
                if response.status_code == 200:
                    logger.info(f"Message sent to {chat_id}")
                else:
                    all_success = False
                    last_error = f"API error for {chat_id}: {response.status_code}"
                    logger.warning(last_error)
            except requests.exceptions.ConnectionError:
                all_success = False
                last_error = "No internet connection"
            except requests.exceptions.Timeout:
                all_success = False
                last_error = "Request timeout"
            except Exception as e:
                all_success = False
                last_error = str(e)
        
        return all_success, last_error
    
    @staticmethod
    def send_sticker(sticker_id: str) -> tuple[bool, Optional[str]]:
        if not sticker_id:
            return True, None
            
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendSticker"
        
        all_success = True
        last_error = None
        
        for chat_id in CHAT_IDS:
            payload = {
                "chat_id": chat_id,
                "sticker": sticker_id
            }
            
            try:
                response = requests.post(url, json=payload, timeout=10)
                if response.status_code == 200:
                    logger.info(f"Sticker sent to {chat_id}")
                else:
                    all_success = False
                    last_error = f"Sticker API error for {chat_id}: {response.status_code}"
                    logger.warning(last_error)
            except Exception as e:
                all_success = False
                last_error = str(e)
        
        return all_success, last_error
    
    @staticmethod
    def is_online() -> bool:
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getMe",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False


class SessionTracker:
    @staticmethod
    def _read() -> Optional[dict]:
        try:
            path = Path(SESSION_FILE)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data if data else None
        except:
            pass
        return None
    
    @staticmethod
    def _write(data: Optional[dict]):
        with open(SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_session(cls) -> Optional[dict]:
        return cls._read()
    
    @classmethod
    def set_session(cls, user_id: int, user_name: str) -> dict:
        session = {
            "user_id": user_id,
            "user_name": user_name,
            "login_time": get_uzb_time().isoformat()
        }
        cls._write(session)
        logger.info(f"Session started: {user_name} (ID: {user_id})")
        return session
    
    @classmethod
    def clear_session(cls) -> Optional[dict]:
        old = cls._read()
        cls._write(None)
        if old:
            logger.info(f"Session cleared: {old['user_name']}")
        return old

class PendingQueue:
    
    @staticmethod
    def _read() -> list:
        try:
            path = Path(PENDING_FILE)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f) or []
        except:
            pass
        return []
    
    @staticmethod
    def _write(data: list):
        with open(PENDING_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def add(cls, message: str, notification_type: str, sticker_id: str = None):
        queue = cls._read()
        queue.append({
            "message": message,
            "type": notification_type,
            "sticker_id": sticker_id,
            "created_at": get_uzb_time().isoformat()
        })
        cls._write(queue)
        logger.info(f"Queued notification: {notification_type}")
    
    @classmethod
    def get_all(cls) -> list:
        return cls._read()
    
    @classmethod
    def clear(cls):
        cls._write([])
    
    @classmethod
    def count(cls) -> int:
        return len(cls._read())

@dataclass
class ShiftStats:
    total_orders: int
    total_revenue: Decimal
    paid_orders: int
    unpaid_orders: int
    cancelled_orders: int
    duration_minutes: int

class ShiftNotificationService:

    SHIFT_START_TEMPLATE = """
🟢 <b>SMENA BOSHLANDI</b>

👤 Kassir: <b>{cashier_name}</b>
📅 Sana: {date}
⏰ Vaqt: {time}

Yaxshi ish kunini tilaymiz! 💪
"""

    SHIFT_END_TEMPLATE = """
🔴 <b>SMENA TUGADI</b>

👤 Kassir: <b>{cashier_name}</b>
📅 Sana: {date}
⏰ Vaqt: {time}
⏱ Davomiyligi: <b>{duration}</b>

Rahmat, dam oling! 🌙
"""

    STATISTICS_TEMPLATE = """
📊 <b>{cashier_name} - SMENA STATISTIKASI</b>

⏱ Davomiyligi: <b>{duration}</b>
━━━━━━━━━━━━━━━━━━━━━
📦 Jami buyurtmalar: <b>{total_orders}</b>
✅ To'langan: <b>{paid_orders}</b>
❌ To'lanmagan: <b>{unpaid_orders}</b>
🚫 Bekor qilingan: <b>{cancelled_orders}</b>
━━━━━━━━━━━━━━━━━━━━━
💰 <b>Jami tushum: {total_revenue:,.0f} UZS</b>
"""

    SHIFT_SWITCH_TEMPLATE = """
🔄 <b>SMENA ALMASHDI</b>

🔴 Chiqdi: <b>{old_cashier}</b>
🟢 Kirdi: <b>{new_cashier}</b>

📅 Sana: {date}
⏰ Vaqt: {time}
"""

    def get_shift_statistics(self, start_time: datetime, end_time: datetime = None) -> ShiftStats:
        from main.models import Order
        
        if end_time is None:
            end_time = get_uzb_time()
        
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=UZB_TZ)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=UZB_TZ)
        
        orders = Order.objects.filter(
            created_at__gte=start_time,
            created_at__lte=end_time
        )
        
        total_orders = orders.count()
        paid_orders = orders.filter(is_paid=True).count()
        unpaid_orders = orders.filter(is_paid=False).exclude(status='CANCELLED').count()
        cancelled_orders = orders.filter(status='CANCELLED').count()
        
        total_revenue = orders.filter(is_paid=True).aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')
        
        duration_minutes = int((end_time - start_time).total_seconds() / 60)
        
        return ShiftStats(
            total_orders=total_orders,
            total_revenue=total_revenue,
            paid_orders=paid_orders,
            unpaid_orders=unpaid_orders,
            cancelled_orders=cancelled_orders,
            duration_minutes=duration_minutes
        )
    
    def _format_duration(self, minutes: int) -> str:
        if minutes < 60:
            return f"{minutes} daqiqa"
        hours = minutes // 60
        mins = minutes % 60
        if mins == 0:
            return f"{hours} soat"
        return f"{hours} soat {mins} daqiqa"
    
    def _parse_login_time(self, iso_string: str) -> datetime:
        dt = datetime.fromisoformat(iso_string)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UZB_TZ)
        return dt
    
    def _get_stats_sticker(self, stats: ShiftStats) -> str:
        if stats.total_orders >= 10 or stats.total_revenue >= 500000:
            return STICKERS.get('good_stats')
        return STICKERS.get('neutral_stats')

    def on_cashier_login(self, user_id: int, user_name: str) -> dict:
        current_session = SessionTracker.get_session()
        result = {
            'success': True,
            'message': '',
            'previous_cashier': None
        }
        
        if current_session and current_session['user_id'] == user_id:
            result['message'] = 'Same cashier already logged in'
            return result
        
        if current_session:
            self._send_shift_switch(current_session, user_id, user_name)
            result['previous_cashier'] = current_session['user_name']
        else:
            self._send_shift_start(user_name)
        SessionTracker.set_session(user_id, user_name)
        result['message'] = f'Shift started for {user_name}'
        
        return result
    
    def on_cashier_logout(self, user_id: int) -> dict:
        current_session = SessionTracker.get_session()
        result = {
            'success': True,
            'message': '',
            'notification_sent': False
        }
        
        if not current_session:
            result['message'] = 'No active session to end'
            return result
        
        if current_session['user_id'] != user_id:
            result['message'] = 'Different cashier is currently active'
            return result

        self._send_shift_end(current_session)
        SessionTracker.clear_session()
        
        result['message'] = f'Shift ended for {current_session["user_name"]}'
        result['notification_sent'] = True
        
        return result
    
    def get_current_session_info(self) -> Optional[dict]:
        session = SessionTracker.get_session()
        if not session:
            return None
        
        start_time = self._parse_login_time(session['login_time'])
        now = get_uzb_time()
        duration_minutes = int((now - start_time).total_seconds() / 60)
        
        return {
            'user_id': session['user_id'],
            'user_name': session['user_name'],
            'login_time': session['login_time'],
            'duration': self._format_duration(duration_minutes),
            'duration_minutes': duration_minutes
        }
    
    def process_pending(self) -> Tuple[int, int]:
        if not TelegramService.is_online():
            return 0, 0
        
        pending = PendingQueue.get_all()
        if not pending:
            return 0, 0
        
        sent = 0
        for notif in pending:
            if notif.get('sticker_id'):
                TelegramService.send_sticker(notif['sticker_id'])
            
            success, _ = TelegramService.send_message(notif['message'])
            if success:
                sent += 1
            else:
                break
        
        if sent == len(pending):
            PendingQueue.clear()
        
        return sent, len(pending) - sent

    def _send_shift_start(self, user_name: str) -> bool:
        date_str, time_str = format_uzb_datetime()
        
        message = self.SHIFT_START_TEMPLATE.format(
            cashier_name=user_name,
            date=date_str,
            time=time_str
        ).strip()

        sticker_id = STICKERS.get('shift_start')
        if sticker_id:
            TelegramService.send_sticker(sticker_id)
        
        success, error = TelegramService.send_message(message)
        
        if not success:
            PendingQueue.add(message, "shift_start", sticker_id)
        
        return success
    
    def _send_shift_end(self, session: dict) -> bool:
        date_str, time_str = format_uzb_datetime()
        start_time = self._parse_login_time(session['login_time'])
        stats = self.get_shift_statistics(start_time)
        
        stats_message = self.STATISTICS_TEMPLATE.format(
            cashier_name=session['user_name'],
            duration=self._format_duration(stats.duration_minutes),
            total_orders=stats.total_orders,
            paid_orders=stats.paid_orders,
            unpaid_orders=stats.unpaid_orders,
            cancelled_orders=stats.cancelled_orders,
            total_revenue=stats.total_revenue
        ).strip()
        
        stats_sticker = self._get_stats_sticker(stats)
        if stats_sticker:
            TelegramService.send_sticker(stats_sticker)
        
        TelegramService.send_message(stats_message)
        
        end_message = self.SHIFT_END_TEMPLATE.format(
            cashier_name=session['user_name'],
            date=date_str,
            time=time_str,
            duration=self._format_duration(stats.duration_minutes)
        ).strip()
        
        end_sticker = STICKERS.get('shift_end')
        if end_sticker:
            TelegramService.send_sticker(end_sticker)
        
        success, error = TelegramService.send_message(end_message)
        
        if not success:
            PendingQueue.add(end_message, "shift_end", end_sticker)
        
        return success
    
    def _send_shift_switch(self, old_session: dict, new_user_id: int, new_user_name: str) -> bool:
        date_str, time_str = format_uzb_datetime()
        start_time = self._parse_login_time(old_session['login_time'])
        stats = self.get_shift_statistics(start_time)
        stats_message = self.STATISTICS_TEMPLATE.format(
            cashier_name=old_session['user_name'],
            duration=self._format_duration(stats.duration_minutes),
            total_orders=stats.total_orders,
            paid_orders=stats.paid_orders,
            unpaid_orders=stats.unpaid_orders,
            cancelled_orders=stats.cancelled_orders,
            total_revenue=stats.total_revenue
        ).strip()
        
        stats_sticker = self._get_stats_sticker(stats)
        if stats_sticker:
            TelegramService.send_sticker(stats_sticker)
        
        TelegramService.send_message(stats_message)
        
        switch_message = self.SHIFT_SWITCH_TEMPLATE.format(
            old_cashier=old_session['user_name'],
            new_cashier=new_user_name,
            date=date_str,
            time=time_str
        ).strip()

        switch_sticker = STICKERS.get('shift_switch')
        if switch_sticker:
            TelegramService.send_sticker(switch_sticker)
        
        success, error = TelegramService.send_message(switch_message)
        
        if not success:
            PendingQueue.add(switch_message, "shift_switch", switch_sticker)
        
        return success

_service_instance: Optional[ShiftNotificationService] = None


def get_shift_notification_service() -> ShiftNotificationService:
    global _service_instance
    if _service_instance is None:
        _service_instance = ShiftNotificationService()
    return _service_instance