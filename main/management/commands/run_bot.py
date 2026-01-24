import asyncio
import signal
import logging

from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run the Smart Jowi Telegram bot'

    def __init__(self):
        super().__init__()
        self.bot = None
        self.running = True

    def handle(self, *args, **options):
        from main.bot.smart_jowi_bot import SmartJowiBot

        bot_token = getattr(settings, 'BOT_TOKEN', None)

        if not bot_token:
            self.stderr.write(self.style.ERROR('BOT_TOKEN not found in settings!'))
            return

        self.bot = SmartJowiBot(bot_token)
        self._run_bot()

    def _run_bot(self):
        self.stdout.write(self.style.SUCCESS('Starting Smart Jowi Bot...'))
        self.stdout.write('Press Ctrl+C to stop.\n')

        def signal_handler(sig, frame):
            self.stdout.write('\nStopping bot...')
            self.running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            asyncio.run(self.bot.start())
        except KeyboardInterrupt:
            pass
        finally:
            self.stdout.write(self.style.SUCCESS('Bot stopped.'))
