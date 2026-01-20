import json
import logging
import requests
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict
from threading import Thread, Lock
import time
from smart_jowi.settings import BOT_TOKEN, CHAT_IDS, UZB_TZ, STICKERS, ORDER_MESSAGES_FILE, PENDING_ORDERS_FILE, RETRY_INTERVAL_SECONDS

logger = logging.getLogger(__name__)

def get_uzb_time() -> datetime:
    return datetime.now(UZB_TZ)


def format_uzb_time(dt: datetime = None) -> str:
    if dt is None:
        dt = get_uzb_time()
    return dt.strftime('%H:%M:%S')


def format_uzb_date(dt: datetime = None) -> str:
    if dt is None:
        dt = get_uzb_time()
    return dt.strftime('%Y-%m-%d')


def format_money(amount) -> str:
    if isinstance(amount, Decimal):
        amount = float(amount)
    return f"{amount:,.0f}"


class TelegramAPI:
    
    BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
    
    @classmethod
    def _request(cls, method: str, data: dict) -> Optional[dict]:
        try:
            response = requests.post(
                f"{cls.BASE_URL}/{method}",
                json=data,
                timeout=10
            )
            if response.status_code == 200:
                return response.json().get('result')
            logger.warning(f"Telegram API error: {response.status_code} - {response.text}")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"Telegram request failed: {e}")
            return None
    
    @classmethod
    def is_online(cls) -> bool:
        try:
            response = requests.get(f"{cls.BASE_URL}/getMe", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    @classmethod
    def send_message(cls, chat_id: int, text: str, parse_mode: str = "HTML") -> Optional[int]:
        result = cls._request("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        })
        return result.get('message_id') if result else None
    
    @classmethod
    def send_sticker(cls, chat_id: int, sticker_id: str) -> Optional[int]:
        if not sticker_id:
            return None
        result = cls._request("sendSticker", {
            "chat_id": chat_id,
            "sticker": sticker_id
        })
        return result.get('message_id') if result else None
    
    @classmethod
    def edit_message(cls, chat_id: int, message_id: int, text: str, parse_mode: str = "HTML") -> bool:
        result = cls._request("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode
        })
        return result is not None
    
    @classmethod
    def pin_message(cls, chat_id: int, message_id: int, disable_notification: bool = False) -> bool:
        result = cls._request("pinChatMessage", {
            "chat_id": chat_id,
            "message_id": message_id,
            "disable_notification": disable_notification
        })
        return result is not None
    
    @classmethod
    def unpin_message(cls, chat_id: int, message_id: int) -> bool:
        result = cls._request("unpinChatMessage", {
            "chat_id": chat_id,
            "message_id": message_id
        })
        return result is not None
    
    @classmethod
    def delete_message(cls, chat_id: int, message_id: int) -> bool:
        result = cls._request("deleteMessage", {
            "chat_id": chat_id,
            "message_id": message_id
        })
        return result is not None


class OrderMessageStorage:
    _lock = Lock()
    
    @classmethod
    def _read(cls) -> Dict:
        try:
            path = Path(ORDER_MESSAGES_FILE)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except:
            pass
        return {}
    
    @classmethod
    def _write(cls, data: Dict):
        with open(ORDER_MESSAGES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def save_message_ids(cls, order_id: int, chat_message_map: Dict[int, int]):
        with cls._lock:
            data = cls._read()
            data[str(order_id)] = chat_message_map
            cls._write(data)
    
    @classmethod
    def get_message_ids(cls, order_id: int) -> Optional[Dict[int, int]]:
        with cls._lock:
            data = cls._read()
            result = data.get(str(order_id))
            if result:
                return {int(k): v for k, v in result.items()}
            return None
    
    @classmethod
    def remove_order(cls, order_id: int):
        with cls._lock:
            data = cls._read()
            data.pop(str(order_id), None)
            cls._write(data)


@dataclass
class PendingOrderNotification:
    action: str 
    order_id: int
    order_data: dict  
    created_at: str
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'PendingOrderNotification':
        return cls(**data)


class PendingOrderQueue:
    
    _lock = Lock()
    
    @classmethod
    def _read(cls) -> List[dict]:
        try:
            path = Path(PENDING_ORDERS_FILE)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f) or []
        except:
            pass
        return []
    
    @classmethod
    def _write(cls, data: List[dict]):
        with open(PENDING_ORDERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def add(cls, notification: PendingOrderNotification):
        with cls._lock:
            queue = cls._read()
            queue.append(notification.to_dict())
            cls._write(queue)
            logger.info(f"Queued order notification: {notification.action} for order {notification.order_id}")
    
    @classmethod
    def get_all(cls) -> List[PendingOrderNotification]:
        with cls._lock:
            queue = cls._read()
            return [PendingOrderNotification.from_dict(item) for item in queue]
    
    @classmethod
    def clear(cls):
        with cls._lock:
            cls._write([])
    
    @classmethod
    def remove_first(cls, count: int):
        with cls._lock:
            queue = cls._read()
            cls._write(queue[count:])
    
    @classmethod
    def count(cls) -> int:
        with cls._lock:
            return len(cls._read())
    
    @classmethod
    def is_empty(cls) -> bool:
        return cls.count() == 0


class OrderNotificationService:
    
    STATUS_FORMATS = {
        'NEW': '🆕 YANGI',
        'OPEN': '🆕 YANGI',
        'PREPARING': '🔄 TAYYORLANMOQDA',
        'READY': '✅ TAYYOR',
        'DELIVERING': '🚗 YETKAZILMOQDA',
        'COMPLETED': '✔️ YAKUNLANDI',
        'CANCELLED': '🚫 BEKOR QILINDI'
    }
    
    ORDER_TEMPLATE = """
<b>{status_text} #{display_id}</b>

Kassir: <b>{cashier_name}</b>
Turi: <b>{order_type}</b>
{phone_line}
───────────────────
{items_list}
───────────────────
<b>Jami: {total_amount} so'm</b>
To'lov: {payment_status}
{prep_time_line}
{hashtags}
"""

    ORDER_CANCELLED_TEMPLATE = """
<b>🚫 BEKOR QILINDI #{display_id}</b>

Kassir: <b>{cashier_name}</b>
───────────────────
{items_list}
───────────────────
<s>{total_amount} so'm</s>

{hashtags}
"""

    ORDER_TYPE_HASHTAGS = {
        'HALL': '#zal',
        'DELIVERY': '#yetkazish',
        'PICKUP': '#olib_ketish'
    }
    
    STATUS_HASHTAGS = {
        'NEW': '#yangi',
        'OPEN': '#yangi',
        'PREPARING': '#tayyorlanmoqda',
        'READY': '#tayyor',
        'DELIVERING': '#yetkazilmoqda',
        'COMPLETED': '#yakunlandi',
        'CANCELLED': '#bekor'
    }

    def __init__(self):
        self._retry_thread = None
        self._stop_retry = False
    
    def _get_status_text(self, status: str) -> str:
        return self.STATUS_FORMATS.get(status, status)
    
    def _get_payment_status(self, is_paid: bool) -> str:
        return "✅ To'langan" if is_paid else "❌ To'lanmagan"
    
    def _get_hashtags(self, order_data: dict, status: str) -> str:
        tags = []
        
        if status in self.STATUS_HASHTAGS:
            tags.append(self.STATUS_HASHTAGS[status])
        
        order_type = order_data.get('order_type', '')
        if order_type in self.ORDER_TYPE_HASHTAGS:
            tags.append(self.ORDER_TYPE_HASHTAGS[order_type])
        
        if order_data.get('is_paid'):
            tags.append('#tolangan')
        else:
            tags.append('#tolanmagan')
        
        return ' '.join(tags)
    
    def on_new_order(self, order) -> dict:
        order_data = self._serialize_order(order)
        
        if not TelegramAPI.is_online():
            self._queue_notification('new', order.id, order_data)
            self._ensure_retry_thread()
            return {'success': False, 'message': 'Queued (offline)'}
        
        return self._send_new_order(order_data)
    
    def on_order_status_change(self, order_id: int, new_status: str) -> dict:
        from main.models import Order
        
        try:
            order = Order.objects.select_related('cashier').prefetch_related('items__product').get(id=order_id)
            order_data = self._serialize_order(order)
        except Order.DoesNotExist:
            return {'success': False, 'message': 'Order not found'}
        
        if not TelegramAPI.is_online():
            self._queue_notification('status_change', order_id, order_data)
            self._ensure_retry_thread()
            return {'success': False, 'message': 'Queued (offline)'}
        
        if new_status == 'READY':
            return self._send_order_ready(order_data)
        elif new_status == 'CANCELLED':
            return self._send_order_cancelled(order_data)
        else:
            return self._update_order_message(order_data)
    
    def on_order_ready(self, order_id: int) -> dict:
        return self.on_order_status_change(order_id, 'READY')
    
    def on_order_cancelled(self, order_id: int) -> dict:
        return self.on_order_status_change(order_id, 'CANCELLED')
    
    def process_pending(self) -> tuple[int, int]:
        if not TelegramAPI.is_online():
            return 0, 0
        
        pending = PendingOrderQueue.get_all()
        if not pending:
            return 0, 0
        
        sent = 0
        for notif in pending:
            try:
                if notif.action == 'new':
                    result = self._send_new_order(notif.order_data)
                elif notif.action == 'status_change':
                    if notif.order_data.get('status') == 'READY':
                        result = self._send_order_ready(notif.order_data)
                    elif notif.order_data.get('status') == 'CANCELLED':
                        result = self._send_order_cancelled(notif.order_data)
                    else:
                        result = self._update_order_message(notif.order_data)
                else:
                    result = {'success': True}
                
                if result.get('success'):
                    sent += 1
                else:
                    break
            except Exception as e:
                logger.error(f"Failed to process pending notification: {e}")
                break
        
        if sent > 0:
            PendingOrderQueue.remove_first(sent)
        
        return sent, len(pending) - sent
    
    def _serialize_order(self, order) -> dict:
        items = []
        for item in order.items.all():
            items.append({
                'product_name': item.product.name,
                'quantity': item.quantity,
                'price': str(item.price),
                'subtotal': str(item.price * item.quantity)
            })
        
        cashier_name = "—"
        if order.cashier:
            cashier_name = f"{order.cashier.first_name} {order.cashier.last_name}".strip()
        
        prep_time = None
        if order.ready_at and order.created_at:
            seconds = (order.ready_at - order.created_at).total_seconds()
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            prep_time = f"{minutes}:{secs:02d}"
        
        return {
            'id': order.id,
            'display_id': order.display_id,
            'order_type': order.order_type,
            'phone_number': order.phone_number,
            'status': order.status,
            'is_paid': order.is_paid,
            'total_amount': str(order.total_amount),
            'cashier_name': cashier_name,
            'items': items,
            'prep_time': prep_time,
            'created_at': order.created_at.isoformat() if order.created_at else None,
        }
    
    def _format_items_list(self, items: list) -> str:
        lines = []
        for item in items:
            lines.append(f"{item['product_name']} x{item['quantity']} — {format_money(Decimal(item['subtotal']))} so'm")
        return "\n".join(lines)
    
    def _format_order_type(self, order_type: str) -> str:
        types = {
            'HALL': 'Zalda',
            'DELIVERY': 'Yetkazib berish',
            'PICKUP': 'Olib ketish'
        }
        return types.get(order_type, order_type)
    
    def _build_order_message(self, order_data: dict, status: str) -> str:
        phone_line = ""
        if order_data.get('phone_number'):
            phone_line = f"Tel: <b>{order_data['phone_number']}</b>"
        
        prep_time_line = ""
        if order_data.get('prep_time'):
            prep_time_line = f"Vaqt: <b>{order_data['prep_time']}</b>"
        
        hashtags = self._get_hashtags(order_data, status)
        
        return self.ORDER_TEMPLATE.format(
            status_text=self._get_status_text(status),
            display_id=order_data['display_id'],
            cashier_name=order_data['cashier_name'],
            order_type=self._format_order_type(order_data['order_type']),
            phone_line=phone_line,
            items_list=self._format_items_list(order_data['items']),
            total_amount=format_money(Decimal(order_data['total_amount'])),
            payment_status=self._get_payment_status(order_data['is_paid']),
            prep_time_line=prep_time_line,
            hashtags=hashtags
        ).strip()
    
    def _build_cancelled_message(self, order_data: dict) -> str:
        hashtags = self._get_hashtags(order_data, 'CANCELLED')
        
        return self.ORDER_CANCELLED_TEMPLATE.format(
            display_id=order_data['display_id'],
            cashier_name=order_data['cashier_name'],
            items_list=self._format_items_list(order_data['items']),
            total_amount=format_money(Decimal(order_data['total_amount'])),
            hashtags=hashtags
        ).strip()
    
    def _send_new_order(self, order_data: dict) -> dict:
        message = self._build_order_message(order_data, 'NEW')
        sticker_id = STICKERS.get('new_order')
        
        chat_message_map = {}
        success_count = 0
        
        for chat_id in CHAT_IDS:
            if sticker_id:
                TelegramAPI.send_sticker(chat_id, sticker_id)
            
            message_id = TelegramAPI.send_message(chat_id, message)
            
            if message_id:
                chat_message_map[chat_id] = message_id
                TelegramAPI.pin_message(chat_id, message_id, disable_notification=True)
                success_count += 1
        
        if chat_message_map:
            OrderMessageStorage.save_message_ids(order_data['id'], chat_message_map)
        
        return {
            'success': success_count > 0,
            'message': f'Sent to {success_count}/{len(CHAT_IDS)} chats',
            'message_ids': chat_message_map
        }
    
    def _update_order_message(self, order_data: dict) -> dict:
        message_ids = OrderMessageStorage.get_message_ids(order_data['id'])
        
        if not message_ids:
            return self._send_new_order(order_data)
        
        status = order_data.get('status', 'PREPARING')
        message = self._build_order_message(order_data, status)
        
        success_count = 0
        for chat_id, message_id in message_ids.items():
            if TelegramAPI.edit_message(chat_id, message_id, message):
                success_count += 1
        
        return {
            'success': success_count > 0,
            'message': f'Updated {success_count}/{len(message_ids)} messages'
        }
    
    def _send_order_ready(self, order_data: dict) -> dict:
        message_ids = OrderMessageStorage.get_message_ids(order_data['id'])
        
        if message_ids:
            for chat_id, message_id in message_ids.items():
                TelegramAPI.unpin_message(chat_id, message_id)
                TelegramAPI.edit_message(chat_id, message_id, f"✅ #{order_data['display_id']} tayyor!")

        message = self._build_order_message(order_data, 'READY')
        sticker_id = STICKERS.get('order_ready')
        
        success_count = 0
        for chat_id in CHAT_IDS:
            if sticker_id:
                TelegramAPI.send_sticker(chat_id, sticker_id)
            
            if TelegramAPI.send_message(chat_id, message):
                success_count += 1

        OrderMessageStorage.remove_order(order_data['id'])
        
        return {
            'success': success_count > 0,
            'message': f'Ready notification sent to {success_count}/{len(CHAT_IDS)} chats'
        }
    
    def _send_order_cancelled(self, order_data: dict) -> dict:
        message_ids = OrderMessageStorage.get_message_ids(order_data['id'])
        
        if message_ids:
            for chat_id, message_id in message_ids.items():
                TelegramAPI.unpin_message(chat_id, message_id)

        message = self._build_cancelled_message(order_data)
        sticker_id = STICKERS.get('order_cancelled')
        
        success_count = 0
        for chat_id in CHAT_IDS:
            if sticker_id:
                TelegramAPI.send_sticker(chat_id, sticker_id)
            
            if TelegramAPI.send_message(chat_id, message):
                success_count += 1
        
        if message_ids:
            for chat_id, message_id in message_ids.items():
                TelegramAPI.edit_message(chat_id, message_id, f"🚫 #{order_data['display_id']} bekor qilindi")

        OrderMessageStorage.remove_order(order_data['id'])
        
        return {
            'success': success_count > 0,
            'message': f'Cancelled notification sent to {success_count}/{len(CHAT_IDS)} chats'
        }
    
    def _queue_notification(self, action: str, order_id: int, order_data: dict):
        notification = PendingOrderNotification(
            action=action,
            order_id=order_id,
            order_data=order_data,
            created_at=get_uzb_time().isoformat()
        )
        PendingOrderQueue.add(notification)
    
    def _ensure_retry_thread(self):
        if self._retry_thread is None or not self._retry_thread.is_alive():
            self._stop_retry = False
            self._retry_thread = Thread(target=self._retry_loop, daemon=True)
            self._retry_thread.start()
    
    def _retry_loop(self):
        logger.info("Order notification retry thread started")
        
        while not self._stop_retry:
            time.sleep(RETRY_INTERVAL_SECONDS)
            
            if PendingOrderQueue.is_empty():
                continue
            
            if TelegramAPI.is_online():
                logger.info("Connection restored, processing pending order notifications...")
                sent, failed = self.process_pending()
                logger.info(f"Processed: {sent} sent, {failed} failed")
                
                if PendingOrderQueue.is_empty():
                    logger.info("All pending notifications sent, stopping retry thread")
                    break
        
        logger.info("Order notification retry thread stopped")
    
    def stop_retry_thread(self):
        self._stop_retry = True


_service_instance: Optional[OrderNotificationService] = None


def get_order_notification_service() -> OrderNotificationService:
    global _service_instance
    if _service_instance is None:
        _service_instance = OrderNotificationService()
    return _service_instance