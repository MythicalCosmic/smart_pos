import signal
import logging
from time import sleep

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process pending order notifications'
    
    def __init__(self):
        super().__init__()
        self.running = True
    
    def add_arguments(self, parser):
        parser.add_argument('--daemon', action='store_true', help='Run as daemon (continuous)')
        parser.add_argument('--interval', type=int, default=180, help='Check interval in seconds (default: 180)')
    
    def handle(self, *args, **options):
        from main.services.order_notification_service import (
            get_order_notification_service,
            PendingOrderQueue,
            TelegramAPI,
            get_uzb_time
        )
        
        if options['daemon']:
            self._run_daemon(options['interval'])
        else:
            self._run_once()
    
    def _run_once(self):
        from main.services.order_notification_service import (
            get_order_notification_service,
            PendingOrderQueue,
            TelegramAPI
        )
        
        pending_count = PendingOrderQueue.count()
        
        if pending_count == 0:
            self.stdout.write('No pending notifications.')
            return
        
        self.stdout.write(f'Found {pending_count} pending notifications.')
        
        if not TelegramAPI.is_online():
            self.stdout.write(self.style.WARNING('Telegram offline.'))
            return
        
        service = get_order_notification_service()
        sent, failed = service.process_pending()
        
        self.stdout.write(self.style.SUCCESS(f'Sent: {sent}, Failed: {failed}'))
    
    def _run_daemon(self, interval):
        from main.services.order_notification_service import (
            get_order_notification_service,
            PendingOrderQueue,
            TelegramAPI,
            get_uzb_time
        )
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.stdout.write(self.style.SUCCESS('Order notification processor started (daemon mode)'))
        self.stdout.write(f'Interval: {interval}s')
        self.stdout.write(f'Time: {get_uzb_time().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write('Press Ctrl+C to stop.\n')
        
        while self.running:
            try:
                pending_count = PendingOrderQueue.count()
                
                if pending_count > 0:
                    self.stdout.write(f'[{get_uzb_time().strftime("%H:%M:%S")}] {pending_count} pending')
                    
                    if TelegramAPI.is_online():
                        service = get_order_notification_service()
                        sent, failed = service.process_pending()
                        
                        if sent > 0:
                            self.stdout.write(self.style.SUCCESS(f'  Sent {sent}'))
                        if failed > 0:
                            self.stdout.write(self.style.WARNING(f'  Failed {failed}'))
                    else:
                        self.stdout.write(self.style.WARNING('  Telegram offline'))
                
                sleep(interval)
            except Exception as e:
                logger.error(f'Processor error: {e}')
                self.stdout.write(self.style.ERROR(f'Error: {e}'))
                sleep(interval)
        
        self.stdout.write(self.style.SUCCESS('\nProcessor stopped.'))
    
    def _signal_handler(self, signum, frame):
        self.stdout.write('\nStopping...')
        self.running = False