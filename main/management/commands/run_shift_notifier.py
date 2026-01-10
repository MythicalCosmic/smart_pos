import signal
import sys
import logging
from datetime import datetime
from time import sleep

from django.core.management.base import BaseCommand
from django.utils import timezone

from main.services.shift_notification_service import get_shift_notification_service
from main.services.telegram_service import get_telegram_service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run the shift notification scheduler'
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.service = None
        self.shift_start_sent_today = False
        self.shift_end_sent_today = False
        self.last_date = None
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--check-interval',
            type=int,
            default=30,
            help='Interval in seconds between checks (default: 30)'
        )
        parser.add_argument(
            '--pending-interval',
            type=int,
            default=60,
            help='Interval in seconds between pending notification checks (default: 60)'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting shift notification service...'))
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.service = get_shift_notification_service()
        check_interval = options['check_interval']
        pending_interval = options['pending_interval']
        
        self.stdout.write(f'Check interval: {check_interval}s')
        self.stdout.write(f'Pending notification interval: {pending_interval}s')
        self.stdout.write(f'Shift hours: {self.service.config.start_hour}:00 - {self.service.config.end_hour}:00')
        
        last_pending_check = timezone.now()
        
        while self.running:
            try:
                now = timezone.now()
                current_date = now.date()
                
                if self.last_date != current_date:
                    self._reset_daily_flags(current_date)
                
                if self._should_send_shift_start(now):
                    self._send_shift_start()
                
                if self._should_send_shift_end(now):
                    self._send_shift_end()

                if (now - last_pending_check).total_seconds() >= pending_interval:
                    self._process_pending()
                    last_pending_check = now
                
                sleep(check_interval)
                
            except Exception as e:
                logger.error(f'Error in main loop: {e}')
                self.stdout.write(self.style.ERROR(f'Error: {e}'))
                sleep(check_interval)
        
        self.stdout.write(self.style.SUCCESS('Shift notification service stopped.'))
    
    def _signal_handler(self, signum, frame):
        self.stdout.write('\nReceived shutdown signal, stopping...')
        self.running = False
    
    def _reset_daily_flags(self, current_date):
        self.last_date = current_date
        self.shift_start_sent_today = False
        self.shift_end_sent_today = False
        self.stdout.write(f'New day: {current_date}, flags reset')
    
    def _should_send_shift_start(self, now: datetime) -> bool:
        if self.shift_start_sent_today:
            return False
        
        target_hour = self.service.config.start_hour
        target_minute = self.service.config.start_minute
        
        if now.hour == target_hour and target_minute <= now.minute < target_minute + 2:
            return True
        
        return False
    
    def _should_send_shift_end(self, now: datetime) -> bool:
        if self.shift_end_sent_today:
            return False
        
        target_hour = self.service.config.end_hour
        target_minute = self.service.config.end_minute
        
        if now.hour == target_hour and target_minute <= now.minute < target_minute + 2:
            return True
        
        return False
    
    def _send_shift_start(self):
        self.stdout.write('Sending shift start notification...')
        success = self.service.send_shift_start()
        
        if success:
            self.stdout.write(self.style.SUCCESS('Shift start notification sent!'))
        else:
            self.stdout.write(self.style.WARNING('Shift start queued (offline)'))
        
        self.shift_start_sent_today = True
    
    def _send_shift_end(self):
        self.stdout.write('Sending shift end notification...')
        success = self.service.send_shift_end()
        
        if success:
            self.stdout.write(self.style.SUCCESS('Shift end notification sent!'))
        else:
            self.stdout.write(self.style.WARNING('Shift end queued (offline)'))
        
        self.shift_end_sent_today = True
    
    def _process_pending(self):
        pending_count = self.service.queue.count()
        
        if pending_count > 0:
            self.stdout.write(f'Processing {pending_count} pending notifications...')
            sent, failed = self.service.process_pending_notifications()
            
            if sent > 0:
                self.stdout.write(self.style.SUCCESS(f'Sent {sent} pending notifications'))
            if failed > 0:
                self.stdout.write(self.style.WARNING(f'{failed} notifications still pending'))