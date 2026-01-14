"""
Background Pending Notification Processor
Runs in background to send queued notifications when connection is restored.

Usage:
    python manage.py run_shift_notifier
    python manage.py run_shift_notifier --interval 60
"""

import signal
import logging
from time import sleep

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run background processor for pending shift notifications'
    
    def __init__(self):
        super().__init__()
        self.running = True
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=120,
            help='Interval in seconds between checks (default: 120)'
        )
    
    def handle(self, *args, **options):
        # Import here to avoid issues
        from main.services.shift_notification_service import get_uzb_time
        
        self.stdout.write(self.style.SUCCESS('Starting pending notification processor...'))
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        interval = options['interval']
        
        self.stdout.write(f'Check interval: {interval}s')
        self.stdout.write(f'Current time (UZB): {get_uzb_time().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write('')
        self.stdout.write('Shift notifications are triggered by cashier login/logout.')
        self.stdout.write('This processor only handles failed/pending messages.')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Processor running. Press Ctrl+C to stop.'))
        self.stdout.write('=' * 50)
        
        while self.running:
            try:
                self._process_pending()
                sleep(interval)
                
            except Exception as e:
                logger.error(f'Error in processor: {e}')
                self.stdout.write(self.style.ERROR(f'Error: {e}'))
                sleep(interval)
        
        self.stdout.write(self.style.SUCCESS('\nProcessor stopped.'))
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.stdout.write('\nReceived shutdown signal, stopping...')
        self.running = False
    
    def _process_pending(self):
        """Process any pending notifications."""
        from main.services.shift_notification_service import (
            get_shift_notification_service,
            PendingQueue,
            TelegramService,
            get_uzb_time
        )
        
        pending_count = PendingQueue.count()
        
        if pending_count == 0:
            return
        
        self.stdout.write(f'[{get_uzb_time().strftime("%H:%M:%S")}] Found {pending_count} pending notifications')
        
        # Check if online first (using static method)
        if not TelegramService.is_online():
            self.stdout.write(self.style.WARNING('  ↳ Telegram offline, will retry later'))
            return
        
        service = get_shift_notification_service()
        sent, failed = service.process_pending()
        
        if sent > 0:
            self.stdout.write(self.style.SUCCESS(f'  ↳ Sent {sent} notifications'))
        if failed > 0:
            self.stdout.write(self.style.WARNING(f'  ↳ {failed} still pending'))