"""
Test Command for Shift Notification System
Place this in: main/management/commands/test_shift.py

Usage:
    python manage.py test_shift --check         # Check Telegram connection
    python manage.py test_shift --test          # Send test message
    python manage.py test_shift --login <id>    # Simulate cashier login
    python manage.py test_shift --logout <id>   # Simulate cashier logout
    python manage.py test_shift --status        # Show current shift status
    python manage.py test_shift --pending       # Process pending notifications
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Test the shift notification system'

    def add_arguments(self, parser):
        parser.add_argument('--check', action='store_true', help='Check Telegram connection')
        parser.add_argument('--test', action='store_true', help='Send test message')
        parser.add_argument('--login', type=int, metavar='USER_ID', help='Simulate cashier login')
        parser.add_argument('--logout', type=int, metavar='USER_ID', help='Simulate cashier logout')
        parser.add_argument('--status', action='store_true', help='Show current shift status')
        parser.add_argument('--pending', action='store_true', help='Process pending notifications')

    def handle(self, *args, **options):
        if options['check']:
            self.check_connection()
        elif options['test']:
            self.send_test()
        elif options['login']:
            self.simulate_login(options['login'])
        elif options['logout'] is not None:
            self.simulate_logout(options['logout'])
        elif options['status']:
            self.show_status()
        elif options['pending']:
            self.process_pending()
        else:
            self.print_usage()

    def print_usage(self):
        self.stdout.write(self.style.WARNING('Please specify an option:\n'))
        self.stdout.write('  --check          Check Telegram connection')
        self.stdout.write('  --test           Send test message')
        self.stdout.write('  --login <id>     Simulate cashier login')
        self.stdout.write('  --logout <id>    Simulate cashier logout')
        self.stdout.write('  --status         Show current shift status')
        self.stdout.write('  --pending        Process pending notifications')

    def check_connection(self):
        from main.services.shift_notification_service import TelegramService, get_uzb_time, BOT_TOKEN, CHAT_IDS
        
        self.stdout.write('Checking Telegram connection...\n')
        self.stdout.write(f'Bot Token: {BOT_TOKEN[:20]}...')
        self.stdout.write(f'Chat ID: {CHAT_IDS}')
        self.stdout.write(f'Current time (UZB): {get_uzb_time().strftime("%Y-%m-%d %H:%M:%S")}')
        
        if TelegramService.is_online():
            self.stdout.write(self.style.SUCCESS('\n✅ Telegram API is reachable!'))
        else:
            self.stdout.write(self.style.ERROR('\n❌ Cannot reach Telegram API'))

    def send_test(self):
        """Send a test message."""
        from main.services.shift_notification_service import TelegramService, get_uzb_time
        
        self.stdout.write('Sending test message...\n')
        
        now = get_uzb_time()
        message = f"""
🧪 <b>TEST XABAR</b>

Bu test xabar Smart POS tizimidan.

✅ Agar siz buni ko'rsangiz, integratsiya ishlayapti!

⏰ Vaqt (UZB): {now.strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        success, error = TelegramService.send_message(message.strip())
        
        if success:
            self.stdout.write(self.style.SUCCESS('✅ Test message sent! Check Telegram.'))
        else:
            self.stdout.write(self.style.ERROR(f'❌ Failed: {error}'))

    def simulate_login(self, user_id: int):
        """Simulate cashier login."""
        from main.models import User
        from main.services.shift_notification_service import get_shift_notification_service
        
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ User with ID {user_id} not found'))
            return
        
        user_name = f"{user.first_name} {user.last_name}".strip() or user.email
        self.stdout.write(f'Simulating login for: {user_name} (ID: {user_id})')
        self.stdout.write(f'User role: {user.role}')
        
        service = get_shift_notification_service()
        result = service.on_cashier_login(user_id, user_name)
        
        self.stdout.write(f'\nResult: {result["message"]}')
        
        if result.get('previous_cashier'):
            self.stdout.write(f'Previous cashier ended: {result["previous_cashier"]}')
        
        self.stdout.write(self.style.SUCCESS('\n✅ Done! Check Telegram.'))

    def simulate_logout(self, user_id: int):
        """Simulate cashier logout."""
        from main.services.shift_notification_service import get_shift_notification_service
        
        self.stdout.write(f'Simulating logout for user ID: {user_id}')
        
        service = get_shift_notification_service()
        result = service.on_cashier_logout(user_id)
        
        self.stdout.write(f'\nResult: {result["message"]}')
        
        if result.get('notification_sent'):
            self.stdout.write(self.style.SUCCESS('\n✅ Done! Check Telegram.'))
        else:
            self.stdout.write(self.style.WARNING('\n⚠️ No notification was sent.'))

    def show_status(self):
        """Show current shift status."""
        from main.services.shift_notification_service import get_shift_notification_service, PendingQueue
        
        self.stdout.write('Current Shift Status\n')
        self.stdout.write('=' * 40)
        
        service = get_shift_notification_service()
        session_info = service.get_current_session_info()
        
        if session_info:
            self.stdout.write(self.style.SUCCESS('\n🟢 SHIFT ACTIVE'))
            self.stdout.write(f'  Cashier: {session_info["user_name"]}')
            self.stdout.write(f'  User ID: {session_info["user_id"]}')
            self.stdout.write(f'  Login time: {session_info["login_time"]}')
            self.stdout.write(f'  Duration: {session_info["duration"]}')
        else:
            self.stdout.write(self.style.WARNING('\n🔴 NO ACTIVE SHIFT'))
        
        pending_count = PendingQueue.count()
        self.stdout.write(f'\n📬 Pending notifications: {pending_count}')

    def process_pending(self):
        """Process pending notifications."""
        from main.services.shift_notification_service import get_shift_notification_service
        
        self.stdout.write('Processing pending notifications...\n')
        
        service = get_shift_notification_service()
        sent, failed = service.process_pending()
        
        self.stdout.write(f'Sent: {sent}')
        self.stdout.write(f'Failed/Remaining: {failed}')
        
        if sent > 0:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Sent {sent} pending notifications'))