"""
Django management command to run the Smart Jowi Telegram bot
"""

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
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--process-pending',
            action='store_true',
            help='Process pending messages and exit'
        )
    
    def handle(self, *args, **options):
        from main.bot.smart_jowi_bot import SmartJowiBot
        
        # Get bot token from settings
        bot_token = getattr(settings, 'BOT_TOKEN', None)
        
        if not bot_token:
            self.stderr.write(self.style.ERROR(
                'BOT_TOKEN not found in settings!\n'
                'Add BOT_TOKEN to your settings.py'
            ))
            return
        
        self.bot = SmartJowiBot(bot_token)
        
        if options['process_pending']:
            asyncio.run(self._process_pending())
        else:
            self._run_bot()
    
    def _run_bot(self):
        """Run the bot with signal handling"""
        
        self.stdout.write(self.style.SUCCESS('Starting Smart Jowi Bot...'))
        self.stdout.write('Press Ctrl+C to stop.\n')
        
        # Setup signal handlers
        def signal_handler(sig, frame):
            self.stdout.write('\nStopping bot...')
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Run the bot
        try:
            asyncio.run(self.bot.start())
        except KeyboardInterrupt:
            pass
        finally:
            self.stdout.write(self.style.SUCCESS('Bot stopped.'))
    
    async def _process_pending(self):
        """Process pending messages"""
        from main.bot.smart_jowi_bot import PendingMessageQueue
        
        pending_count = PendingMessageQueue.count()
        
        if pending_count == 0:
            self.stdout.write('No pending messages.')
            return
        
        self.stdout.write(f'Processing {pending_count} pending messages...')
        
        sent, failed = await self.bot.process_pending_messages()
        
        self.stdout.write(self.style.SUCCESS(f'Sent: {sent}, Failed: {failed}'))
