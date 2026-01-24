import json
import logging
import requests
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional, Tuple, List
from dataclasses import dataclass

from django.conf import settings
from django.db.models import Sum, Count, Avg, Q, F, ExpressionWrapper, DurationField
from django.db.models.functions import ExtractHour
from django.db import models

logger = logging.getLogger(__name__)

BOT_TOKEN = getattr(settings, 'BOT_TOKEN', '')
UZB_OFFSET = timedelta(hours=5)
UZB_TZ = timezone(UZB_OFFSET)
SESSION_FILE = getattr(settings, 'SESSION_FILE', 'data/session.json')
PENDING_FILE = getattr(settings, 'PENDING_FILE', 'data/pending_notifications.json')
STICKERS = getattr(settings, 'STICKERS', {})


def get_uzb_time() -> datetime:
    return datetime.now(UZB_TZ)


def format_uzb_datetime(dt: datetime = None) -> tuple:
    if dt is None:
        dt = get_uzb_time()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=UZB_TZ)
    else:
        dt = dt.astimezone(UZB_TZ)
    return dt.strftime('%Y-%m-%d'), dt.strftime('%H:%M:%S')


def format_money(amount) -> str:
    if isinstance(amount, Decimal):
        amount = float(amount)
    return f"{amount:,.0f}"


def format_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} daqiqa"
    hours = minutes // 60
    mins = minutes % 60
    if mins == 0:
        return f"{hours} soat"
    return f"{hours} soat {mins} daqiqa"


def get_chat_ids() -> List[int]:
    try:
        from main.bot.smart_jowi_bot import get_chat_ids as bot_get_chat_ids
        return bot_get_chat_ids()
    except ImportError:
        return getattr(settings, 'CHAT_IDS', [])


class TelegramService:
    @staticmethod
    def send_message(text: str) -> tuple:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        chat_ids = get_chat_ids()
        all_success = True
        last_error = None
        for chat_id in chat_ids:
            payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
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
    def send_sticker(sticker_id: str) -> tuple:
        if not sticker_id:
            return True, None
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendSticker"
        chat_ids = get_chat_ids()
        all_success = True
        last_error = None
        for chat_id in chat_ids:
            payload = {"chat_id": chat_id, "sticker": sticker_id}
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
            response = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=5)
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
        path = Path(SESSION_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
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
        path = Path(PENDING_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
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
    completed_orders: int
    duration_minutes: int
    avg_order_value: Decimal
    avg_prep_time_seconds: float
    order_types: dict
    top_products: list
    peak_hour: dict


class ShiftNotificationService:
    SHIFT_START_TEMPLATE = """
<b>SMENA BOSHLANDI</b>

Kassir: <b>{cashier_name}</b>
Sana: {date}
Vaqt: {time}
"""

    STATISTICS_TEMPLATE = """
<b>{cashier_name} — SMENA HISOBOTI</b>

{date_from} {time_from} — {date_to} {time_to}
Davomiyligi: <b>{duration}</b>
───────────────────
<b>BUYURTMALAR</b>

Jami: <b>{total_orders}</b>
Bajarilgan: <b>{completed_orders}</b>
Bekor qilingan: <b>{cancelled_orders}</b>
O'rtacha tayyorlash: <b>{avg_prep_time}</b>
Eng band soat: <b>{peak_hour}</b> ({peak_count} ta)
───────────────────
<b>TO'LOVLAR</b>

To'langan: <b>{paid_orders}</b>
To'lanmagan: <b>{unpaid_orders}</b>
───────────────────
<b>BUYURTMA TURLARI</b>

Zalda: <b>{hall_orders}</b> ({hall_revenue} so'm)
Yetkazib berish: <b>{delivery_orders}</b> ({delivery_revenue} so'm)
Olib ketish: <b>{pickup_orders}</b> ({pickup_revenue} so'm)
───────────────────
<b>TOP MAHSULOTLAR</b>

{top_products_list}
───────────────────
<b>MOLIYAVIY NATIJA</b>

Jami tushum: <b>{total_revenue} so'm</b>
O'rtacha chek: <b>{avg_order_value} so'm</b>
"""

    SHIFT_SWITCH_TEMPLATE = """
<b>SMENA ALMASHDI</b>

Chiqdi: <b>{old_cashier}</b>
Kirdi: <b>{new_cashier}</b>

Sana: {date}
Vaqt: {time}
"""

    def get_shift_statistics(self, start_time: datetime, end_time: datetime = None, cashier_id: int = None) -> ShiftStats:
        from main.models import Order, OrderItem
        if end_time is None:
            end_time = get_uzb_time()
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=UZB_TZ)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=UZB_TZ)
        base_filter = Q(created_at__gte=start_time) & Q(created_at__lte=end_time)
        if cashier_id:
            base_filter &= Q(cashier_id=cashier_id)
        orders = Order.objects.filter(base_filter)
        total_orders = orders.count()
        paid_orders = orders.filter(is_paid=True).count()
        unpaid_orders = orders.filter(is_paid=False).exclude(status='CANCELLED').count()
        cancelled_orders = orders.filter(status='CANCELLED').count()
        completed_orders = orders.filter(status='COMPLETED').count()
        total_revenue = orders.filter(is_paid=True).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
        avg_order_value = orders.filter(is_paid=True).aggregate(avg=Avg('total_amount'))['avg'] or Decimal('0')
        orders_with_ready_time = orders.filter(ready_at__isnull=False, status__in=['READY', 'COMPLETED']).annotate(
            prep_time=ExpressionWrapper(F('ready_at') - F('created_at'), output_field=DurationField())
        )
        avg_prep_time_seconds = 0
        if orders_with_ready_time.exists():
            total_prep_time = sum((o.prep_time.total_seconds() for o in orders_with_ready_time if o.prep_time), 0)
            count = orders_with_ready_time.count()
            avg_prep_time_seconds = total_prep_time / count if count > 0 else 0
        order_type_data = orders.values('order_type').annotate(count=Count('id'), revenue=Sum('total_amount', filter=Q(is_paid=True)))
        order_types = {
            'HALL': {'count': 0, 'revenue': Decimal('0')},
            'DELIVERY': {'count': 0, 'revenue': Decimal('0')},
            'PICKUP': {'count': 0, 'revenue': Decimal('0')},
        }
        for item in order_type_data:
            if item['order_type'] in order_types:
                order_types[item['order_type']]['count'] = item['count']
                order_types[item['order_type']]['revenue'] = item['revenue'] or Decimal('0')
        hourly_orders = orders.annotate(hour=ExtractHour('created_at')).values('hour').annotate(count=Count('id')).order_by('hour')
        peak_hour = {'hour': 0, 'count': 0}
        for h in hourly_orders:
            if h['count'] > peak_hour['count']:
                peak_hour = {'hour': h['hour'], 'count': h['count']}
        item_filter = Q(order__created_at__gte=start_time) & Q(order__created_at__lte=end_time) & Q(order__is_paid=True)
        if cashier_id:
            item_filter &= Q(order__cashier_id=cashier_id)
        top_products = list(OrderItem.objects.filter(item_filter).values('product__name').annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum(F('price') * F('quantity'), output_field=models.DecimalField())
        ).order_by('-total_quantity')[:5])
        duration_minutes = int((end_time - start_time).total_seconds() / 60)
        return ShiftStats(
            total_orders=total_orders,
            total_revenue=total_revenue,
            paid_orders=paid_orders,
            unpaid_orders=unpaid_orders,
            cancelled_orders=cancelled_orders,
            completed_orders=completed_orders,
            duration_minutes=duration_minutes,
            avg_order_value=avg_order_value,
            avg_prep_time_seconds=avg_prep_time_seconds,
            order_types=order_types,
            top_products=top_products,
            peak_hour=peak_hour
        )

    def _format_prep_time(self, seconds: float) -> str:
        if seconds == 0:
            return "—"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"

    def _format_top_products(self, products: list) -> str:
        if not products:
            return "Ma'lumot yo'q"
        lines = []
        for i, p in enumerate(products, 1):
            name = p['product__name']
            qty = p['total_quantity']
            revenue = format_money(p['total_revenue'] or 0)
            lines.append(f"{i}. {name} — {qty} ta ({revenue} so'm)")
        return "\n".join(lines)

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
        result = {'success': True, 'message': '', 'previous_cashier': None}
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
        result = {'success': True, 'message': '', 'notification_sent': False}
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
            'duration': format_duration(duration_minutes),
            'duration_minutes': duration_minutes
        }

    def process_pending(self) -> Tuple[int, int]:
        if not TelegramService.is_online():
            return 0, 0
        pending = PendingQueue.get_all()
        if not pending:
            return 0, 0
        sent = 0
        failed = []
        for notif in pending:
            if notif.get('sticker_id'):
                TelegramService.send_sticker(notif['sticker_id'])
            success, _ = TelegramService.send_message(notif['message'])
            if success:
                sent += 1
            else:
                failed.append(notif)
        PendingQueue._write(failed)
        return sent, len(failed)

    def _send_shift_start(self, user_name: str) -> bool:
        date_str, time_str = format_uzb_datetime()
        message = self.SHIFT_START_TEMPLATE.format(cashier_name=user_name, date=date_str, time=time_str).strip()
        sticker_id = STICKERS.get('shift_start')
        if sticker_id:
            TelegramService.send_sticker(sticker_id)
        success, error = TelegramService.send_message(message)
        if not success:
            PendingQueue.add(message, "shift_start", sticker_id)
        return success

    def _send_shift_end(self, session: dict) -> bool:
        now = get_uzb_time()
        date_str, time_str = format_uzb_datetime(now)
        start_time = self._parse_login_time(session['login_time'])
        start_date, start_time_str = format_uzb_datetime(start_time)
        stats = self.get_shift_statistics(start_time, now, session['user_id'])
        stats_message = self.STATISTICS_TEMPLATE.format(
            cashier_name=session['user_name'],
            date_from=start_date,
            time_from=start_time_str,
            date_to=date_str,
            time_to=time_str,
            duration=format_duration(stats.duration_minutes),
            total_orders=stats.total_orders,
            completed_orders=stats.completed_orders,
            cancelled_orders=stats.cancelled_orders,
            avg_prep_time=self._format_prep_time(stats.avg_prep_time_seconds),
            peak_hour=f"{stats.peak_hour['hour']:02d}:00",
            peak_count=stats.peak_hour['count'],
            paid_orders=stats.paid_orders,
            unpaid_orders=stats.unpaid_orders,
            hall_orders=stats.order_types['HALL']['count'],
            hall_revenue=format_money(stats.order_types['HALL']['revenue']),
            delivery_orders=stats.order_types['DELIVERY']['count'],
            delivery_revenue=format_money(stats.order_types['DELIVERY']['revenue']),
            pickup_orders=stats.order_types['PICKUP']['count'],
            pickup_revenue=format_money(stats.order_types['PICKUP']['revenue']),
            top_products_list=self._format_top_products(stats.top_products),
            total_revenue=format_money(stats.total_revenue),
            avg_order_value=format_money(stats.avg_order_value)
        ).strip()
        stats_sticker = self._get_stats_sticker(stats)
        if stats_sticker:
            TelegramService.send_sticker(stats_sticker)
        success, error = TelegramService.send_message(stats_message)
        if not success:
            PendingQueue.add(stats_message, "shift_end", stats_sticker)
        return success

    def _send_shift_switch(self, old_session: dict, new_user_id: int, new_user_name: str) -> bool:
        now = get_uzb_time()
        date_str, time_str = format_uzb_datetime(now)
        start_time = self._parse_login_time(old_session['login_time'])
        start_date, start_time_str = format_uzb_datetime(start_time)
        stats = self.get_shift_statistics(start_time, now, old_session['user_id'])
        stats_message = self.STATISTICS_TEMPLATE.format(
            cashier_name=old_session['user_name'],
            date_from=start_date,
            time_from=start_time_str,
            date_to=date_str,
            time_to=time_str,
            duration=format_duration(stats.duration_minutes),
            total_orders=stats.total_orders,
            completed_orders=stats.completed_orders,
            cancelled_orders=stats.cancelled_orders,
            avg_prep_time=self._format_prep_time(stats.avg_prep_time_seconds),
            peak_hour=f"{stats.peak_hour['hour']:02d}:00",
            peak_count=stats.peak_hour['count'],
            paid_orders=stats.paid_orders,
            unpaid_orders=stats.unpaid_orders,
            hall_orders=stats.order_types['HALL']['count'],
            hall_revenue=format_money(stats.order_types['HALL']['revenue']),
            delivery_orders=stats.order_types['DELIVERY']['count'],
            delivery_revenue=format_money(stats.order_types['DELIVERY']['revenue']),
            pickup_orders=stats.order_types['PICKUP']['count'],
            pickup_revenue=format_money(stats.order_types['PICKUP']['revenue']),
            top_products_list=self._format_top_products(stats.top_products),
            total_revenue=format_money(stats.total_revenue),
            avg_order_value=format_money(stats.avg_order_value)
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
