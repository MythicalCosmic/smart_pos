# smart_jowi/settings/__init__.py

import os

settings_module = os.getenv('DJANGO_SETTINGS_MODULE', 'smart_jowi.settings.local')

if 'cloud' in settings_module:
    from .cloud import *
else:
    from .local import *