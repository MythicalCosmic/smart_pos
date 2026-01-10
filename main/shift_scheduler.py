import os
import sys
import logging
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from django.utils import timezone

from services.shift_notification_service import get_shift_notification_service

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def send_shift_start():
    logger.info("Executing shift start job")
    service = get_shift_notification_service()
    success = service.send_shift_start()
    
    if success:
        logger.info("✅ Shift start notification sent successfully")
    else:
        logger.warning("⚠️ Shift start notification queued (will retry)")


def send_shift_end():
    logger.info("Executing shift end job")
    service = get_shift_notification_service()
    success = service.send_shift_end()
    
    if success:
        logger.info("✅ Shift end notification sent successfully")
    else:
        logger.warning("⚠️ Shift end notification queued (will retry)")


def process_pending():
    service = get_shift_notification_service()
    pending_count = service.queue.count()
    
    if pending_count > 0:
        logger.info(f"Processing {pending_count} pending notifications")
        sent, failed = service.process_pending_notifications()
        logger.info(f"Sent: {sent}, Still pending: {failed}")


def main():
    logger.info("=" * 50)
    logger.info("Starting Shift Notification Scheduler")
    logger.info("=" * 50)
    logger.info(f"Current time: {timezone.now()}")
    logger.info("Schedule:")
    logger.info("  - Shift Start: 08:00 daily")
    logger.info("  - Shift End: 17:00 daily")
    logger.info("  - Pending check: Every 2 minutes")
    logger.info("=" * 50)
    
    scheduler = BlockingScheduler()
    scheduler.add_job(
        send_shift_start,
        CronTrigger(hour=8, minute=0),
        id='shift_start',
        name='Send shift start notification',
        replace_existing=True
    )
    
    scheduler.add_job(
        send_shift_end,
        CronTrigger(hour=17, minute=0),
        id='shift_end',
        name='Send shift end notification',
        replace_existing=True
    )
    
    scheduler.add_job(
        process_pending,
        IntervalTrigger(minutes=2),
        id='process_pending',
        name='Process pending notifications',
        replace_existing=True
    )
    
    try:
        logger.info("Scheduler started. Press Ctrl+C to exit.")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
        scheduler.shutdown()


if __name__ == '__main__':
    main()