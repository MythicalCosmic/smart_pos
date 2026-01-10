import logging
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Optional, Tuple
from dataclasses import dataclass

from django.db.models import Sum, Countw
from django.utils import timezone

from main.services.telegram_service import TelegramService, get_telegram_service
from main.services.pending_notifications import (
    PendingNotification,
    PendingNotificationQueue,
    get_notification_queue
)

logger = logging.getLogger(__name__)


@dataclass
class ShiftConfig:
    start_hour: int = 8
    start_minute: int = 0
    end_hour: int = 17
    end_minute: int = 0


@dataclass
class ShiftStats:
    total_orders: int
    total_revenue: Decimal
    paid_orders: int
    unpaid_orders: int
    cancelled_orders: int
    cashier_stats: list


class ShiftNotificationService:
    
    SHIFT_START_TEMPLATE = """
🟢 <b>SMENA BOSHLANDI</b>

📅 Sana: {date}
⏰ Vaqt: {time}

Yaxshi ish kuningiz bo'lsin! 💪
"""

    SHIFT_END_TEMPLATE = """
🔴 <b>SMENA TUGADI</b>

📅 Sana: {date}
⏰ Vaqt: {time}

📊 <b>Bugungi statistika:</b>
━━━━━━━━━━━━━━━━━━━━━
📦 Jami buyurtmalar: <b>{total_orders}</b>
✅ To'langan: <b>{paid_orders}</b>
❌ To'lanmagan: <b>{unpaid_orders}</b>
🚫 Bekor qilingan: <b>{cancelled_orders}</b>

💰 <b>Jami tushum: {total_revenue:,.0f} UZS</b>
━━━━━━━━━━━━━━━━━━━━━

{cashier_section}

Dam oling, ertaga ko'rishamiz! 🌙
"""

    CASHIER_STATS_TEMPLATE = """
👤 <b>Kassirlar bo'yicha:</b>
{cashier_lines}
"""

    def __init__(
        self,
        telegram_service: Optional[TelegramService] = None,
        notification_queue: Optional[PendingNotificationQueue] = None,
        shift_config: Optional[ShiftConfig] = None
    ):
        self.telegram = telegram_service or get_telegram_service()
        self.queue = notification_queue or get_notification_queue()
        self.config = shift_config or ShiftConfig()
    
    def get_shift_times(self, date: datetime = None) -> Tuple[datetime, datetime]:
        if date is None:
            date = timezone.now()
        
        start = timezone.make_aware(
            datetime.combine(
                date.date(),
                time(self.config.start_hour, self.config.start_minute)
            )
        ) if timezone.is_naive(date) else date.replace(
            hour=self.config.start_hour,
            minute=self.config.start_minute,
            second=0,
            microsecond=0
        )
        
        end = timezone.make_aware(
            datetime.combine(
                date.date(),
                time(self.config.end_hour, self.config.end_minute)
            )
        ) if timezone.is_naive(date) else date.replace(
            hour=self.config.end_hour,
            minute=self.config.end_minute,
            second=0,
            microsecond=0
        )
        
        return start, end
    
    def get_shift_statistics(self, start_time: datetime, end_time: datetime) -> ShiftStats:
        from main.models import Order
        
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
        
        # Cashier statistics
        cashier_stats = list(
            orders.filter(cashier__isnull=False)
            .values('cashier__first_name', 'cashier__last_name')
            .annotate(
                order_count=Count('id'),
                revenue=Sum('total_amount')
            )
            .order_by('-revenue')
        )
        
        return ShiftStats(
            total_orders=total_orders,
            total_revenue=total_revenue,
            paid_orders=paid_orders,
            unpaid_orders=unpaid_orders,
            cancelled_orders=cancelled_orders,
            cashier_stats=cashier_stats
        )
    
    def format_shift_start_message(self) -> str:
        now = timezone.now()
        return self.SHIFT_START_TEMPLATE.format(
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M")
        ).strip()
    
    def format_shift_end_message(self, stats: ShiftStats) -> str:
        now = timezone.now()
        
        cashier_section = ""
        if stats.cashier_stats:
            cashier_lines = []
            for cs in stats.cashier_stats:
                name = f"{cs['cashier__first_name']} {cs['cashier__last_name']}"
                revenue = cs['revenue'] or Decimal('0')
                cashier_lines.append(
                    f"  • {name}: {cs['order_count']} ta / {revenue:,.0f} UZS"
                )
            cashier_section = self.CASHIER_STATS_TEMPLATE.format(
                cashier_lines="\n".join(cashier_lines)
            )
        
        return self.SHIFT_END_TEMPLATE.format(
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M"),
            total_orders=stats.total_orders,
            paid_orders=stats.paid_orders,
            unpaid_orders=stats.unpaid_orders,
            cancelled_orders=stats.cancelled_orders,
            total_revenue=stats.total_revenue,
            cashier_section=cashier_section
        ).strip()
    
    def send_shift_start(self) -> bool:
        message = self.format_shift_start_message()
        success, error = self.telegram.send_message(message)
        
        if not success:
            self._queue_notification(message, "shift_start")
            logger.warning(f"Queued shift start notification: {error}")
        
        return success
    
    def send_shift_end(self) -> bool:
        start_time, end_time = self.get_shift_times()
        stats = self.get_shift_statistics(start_time, end_time)
        message = self.format_shift_end_message(stats)
        
        success, error = self.telegram.send_message(message)
        
        if not success:
            self._queue_notification(message, "shift_end", priority=3)
            logger.warning(f"Queued shift end notification: {error}")
        
        return success
    
    def _queue_notification(
        self,
        message: str,
        notification_type: str,
        priority: int = 2
    ) -> None:
        notification = PendingNotification(
            message=message,
            created_at=timezone.now().isoformat(),
            notification_type=notification_type,
            priority=priority
        )
        self.queue.add(notification)
    
    def process_pending_notifications(self) -> Tuple[int, int]:

        if not self.telegram.is_online():
            logger.info("Telegram not reachable, skipping pending notifications")
            return 0, 0
        
        pending = self.queue.get_all()
        sent = 0
        failed = 0

        pending_sorted = sorted(
            enumerate(pending),
            key=lambda x: (-x[1].priority, x[1].created_at)
        )
        
        indices_to_remove = []
        
        for original_index, notification in pending_sorted:
            success, _ = self.telegram.send_message(notification.message)
            if success:
                sent += 1
                indices_to_remove.append(original_index)
                logger.info(f"Sent pending notification: {notification.notification_type}")
            else:
                failed += 1
                break  
        
        for index in sorted(indices_to_remove, reverse=True):
            self.queue.remove(index)
        
        return sent, failed


def get_shift_notification_service() -> ShiftNotificationService:
    return ShiftNotificationService()