"""
Local settings for POS branches.
SQLite database, sync enabled.

Usage:
    python manage.py runserver --settings=smart_jowi.settings.local
    
Environment variables:
    BRANCH_ID - Unique identifier for this branch (required)
    BRANCH_NAME - Human readable branch name
    CLOUD_SYNC_URL - URL of cloud server for syncing
    CLOUD_SYNC_TOKEN - Auth token for sync API
"""

from .base import *

# =============================================================================
# DEPLOYMENT MODE
# =============================================================================
DEPLOYMENT_MODE = 'local'


# =============================================================================
# DATABASE - SQLite for local reliability
# =============================================================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        # SQLite optimizations for POS
        'OPTIONS': {
            'timeout': 20,  # Wait up to 20 seconds for locks
        }
    }
}


# =============================================================================
# CACHE - Redis if available, fallback to local memory
# =============================================================================
REDIS_HOST = os.getenv('REDIS_HOST', '127.0.0.1')
REDIS_PORT = os.getenv('REDIS_PORT', '6379')

try:
    import redis
    r = redis.Redis(host=REDIS_HOST, port=int(REDIS_PORT))
    r.ping()
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': f'redis://{REDIS_HOST}:{REDIS_PORT}/1',
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            },
            'KEY_PREFIX': 'smartjowi_local',
            'TIMEOUT': 300,
        }
    }
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [(REDIS_HOST, int(REDIS_PORT))],
            },
        },
    }
except:
    # Fallback to local memory cache if Redis unavailable
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'smartjowi-local',
        }
    }
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }


# =============================================================================
# SYNC CONFIGURATION
# =============================================================================
SYNC_ENABLED = True

# Branch identification
BRANCH_ID = os.getenv('BRANCH_ID', 'branch_001')
BRANCH_NAME = os.getenv('BRANCH_NAME', 'Main Branch')

# Cloud server connection
CLOUD_SYNC_URL = os.getenv('CLOUD_SYNC_URL', 'https://your-cloud-server.com')
CLOUD_SYNC_TOKEN = os.getenv('CLOUD_SYNC_TOKEN', '')

# Sync intervals (in seconds)
SYNC_INTERVAL = int(os.getenv('SYNC_INTERVAL', '30'))  # How often to push changes
SYNC_RETRY_INTERVAL = int(os.getenv('SYNC_RETRY_INTERVAL', '60'))  # Retry on failure

# Sync behavior
SYNC_ON_SAVE = True  # Queue items for sync immediately on save
SYNC_BATCH_SIZE = 100  # Max items per sync request


# =============================================================================
# OFFLINE QUEUE
# =============================================================================
# Path to store pending sync items when offline
SYNC_QUEUE_FILE = BASE_DIR / 'sync_queue.json'


# =============================================================================
# LOCAL-SPECIFIC SETTINGS
# =============================================================================
# POS terminals don't need HTTPS in local network
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# More verbose logging for debugging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'local.log',
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'main.services.sync': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    },
}

# Create logs directory if it doesn't exist
(BASE_DIR / 'logs').mkdir(exist_ok=True)
