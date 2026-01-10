"""
Test Command for Shift Notification System
Place this in: main/management/commands/test_shift_notifier.py

Usage:
    python manage.py test_shift_notifier --test          # Send test message
    python manage.py test_shift_notifier --start         # Send shift start
    python manage.py test_shift_notifier --end           # Send shift end
    python manage.py test_shift_notifier --stats         # Show today's stats
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from main.services.shift_notification_service import get_shift_notification_service
from main.services.telegram_service import get_telegram_service


class Command(BaseCommand):
    help = 'Test the shift notification system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test',
            action='store_true',
            help='Send a test message to verify Telegram connection'
        )
        parser.add_argument(
            '--start',
            action='store_true',
            help='Send shift start notification now'
        )
        parser.add_argument(
            '--end',
            action='store_true',
            help='Send shift end notification with today\'s stats'
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            help='Show today\'s statistics without sending'
        )
        parser.add_argument(
            '--check',
            action='store_true',
            help='Check Telegram connection'
        )

    def handle(self, *args, **options):
        if options['check']:
            self.check_connection()
        elif options['test']:
            self.send_test_message()
        elif options['start']:
            self.send_shift_start()
        elif options['end']:
            self.send_shift_end()
        elif options['stats']:
            self.show_stats()
        else:
            self.stdout.write(self.style.WARNING(
                'Please specify an option: --test, --start, --end, --stats, or --check'
            ))
            self.stdout.write('\nExamples:')
            self.stdout.write('  python manage.py test_shift_notifier --check')
            self.stdout.write('  python manage.py test_shift_notifier --test')
            self.stdout.write('  python manage.py test_shift_notifier --start')
            self.stdout.write('  python manage.py test_shift_notifier --end')
            self.stdout.write('  python manage.py test_shift_notifier --stats')

    def check_connection(self):
        """Check if Telegram API is reachable."""
        self.stdout.write('Checking Telegram connection...')
        
        telegram = get_telegram_service()
        
        self.stdout.write(f'Bot Token: {telegram.config.bot_token[:20]}...')
        self.stdout.write(f'Chat ID: {telegram.config.chat_id}')
        
        if telegram.is_online():
            self.stdout.write(self.style.SUCCESS('✅ Telegram API is reachable!'))
        else:
            self.stdout.write(self.style.ERROR('❌ Cannot reach Telegram API'))

    def send_test_message(self):
        """Send a test message to Telegram."""
        self.stdout.write('Sending test message...')
        
        telegram = get_telegram_service()
        
        now = timezone.now()
        test_message = f"""
🧪 <b>TEST XABAR</b>

Bu test xabar Shift Notification tizimidan.

✅ Agar siz buni ko'rsangiz, integratsiya ishlayapti!

⏰ Vaqt: {now.strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        success, error = telegram.send_message(test_message.strip())
        
        if success:
            self.stdout.write(self.style.SUCCESS('✅ Test message sent successfully!'))
            self.stdout.write('Check your Telegram!')
        else:
            self.stdout.write(self.style.ERROR(f'❌ Failed to send: {error}'))

    def send_shift_start(self):
        """Send shift start notification."""
        self.stdout.write('Sending shift start notification...')
        
        service = get_shift_notification_service()
        success = service.send_shift_start()
        
        if success:
            self.stdout.write(self.style.SUCCESS('✅ Shift start notification sent!'))
        else:
            self.stdout.write(self.style.WARNING('⚠️ Message queued (offline mode)'))

    def send_shift_end(self):
        """Send shift end notification with statistics."""
        self.stdout.write('Sending shift end notification...')
        
        service = get_shift_notification_service()
        success = service.send_shift_end()
        
        if success:
            self.stdout.write(self.style.SUCCESS('✅ Shift end notification sent!'))
        else:
            self.stdout.write(self.style.WARNING('⚠️ Message queued (offline mode)'))

    def show_stats(self):
        """Show today's statistics without sending."""
        self.stdout.write('Fetching today\'s statistics...\n')
        
        service = get_shift_notification_service()
        start_time, end_time = service.get_shift_times()
        stats = service.get_shift_statistics(start_time, end_time)
        
        self.stdout.write('=' * 40)
        self.stdout.write(f'📅 Date: {timezone.now().strftime("%Y-%m-%d")}')
        self.stdout.write(f'⏰ Shift: {start_time.strftime("%H:%M")} - {end_time.strftime("%H:%M")}')
        self.stdout.write('=' * 40)
        self.stdout.write(f'📦 Total Orders: {stats.total_orders}')
        self.stdout.write(f'✅ Paid: {stats.paid_orders}')
        self.stdout.write(f'❌ Unpaid: {stats.unpaid_orders}')
        self.stdout.write(f'🚫 Cancelled: {stats.cancelled_orders}')
        self.stdout.write(f'💰 Total Revenue: {stats.total_revenue:,.0f} UZS')
        self.stdout.write('=' * 40)
        
        if stats.cashier_stats:
            self.stdout.write('\n👤 Cashiers:')
            for cs in stats.cashier_stats:
                name = f"{cs['cashier__first_name']} {cs['cashier__last_name']}"
                revenue = cs['revenue'] or 0
                self.stdout.write(f'   • {name}: {cs["order_count"]} orders / {revenue:,.0f} UZS')
        else:
            self.stdout.write('\nNo cashier data available.')