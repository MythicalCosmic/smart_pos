from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured
import os


class MainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'main'

    def ready(self):
        if not os.environ.get('RUN_MAIN'):
            return

        from main.security.fingerprint import (
            generate_machine_fingerprint,
            load_fingerprint,
            save_fingerprint,
        )

        current_fp = generate_machine_fingerprint()
        saved_fp = load_fingerprint()

        if saved_fp is None:
            save_fingerprint(current_fp)
        elif saved_fp != current_fp:
            raise ImproperlyConfigured(
                "This application is locked to another machine."
            )

        from main.services.sync_service import start_sync_worker_on_ready
        start_sync_worker_on_ready()
