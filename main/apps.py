from django.apps import AppConfig


class MainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'main'

    def ready(self):
        import os
        if os.environ.get('RUN_MAIN'):
            from main.services.sync_service import start_sync_worker_on_ready
            start_sync_worker_on_ready()