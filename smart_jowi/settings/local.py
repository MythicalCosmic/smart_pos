from .base import *

DEPLOYMENT_MODE = 'local'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 20,  
        }
    }
}

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

SYNC_ENABLED = True

BRANCH_ID = os.getenv('BRANCH_ID', 'branch_001')
BRANCH_NAME = os.getenv('BRANCH_NAME', 'Main Branch')

# Cloud server connection
CLOUD_SYNC_URL = os.getenv('CLOUD_SYNC_URL', 'https://mythicalcosmic.uz')
CLOUD_SYNC_TOKEN = os.getenv('CLOUD_SYNC_TOKEN', '')

# Sync intervals (in seconds)
SYNC_INTERVAL = int(os.getenv('SYNC_INTERVAL', '30'))  
SYNC_RETRY_INTERVAL = int(os.getenv('SYNC_RETRY_INTERVAL', '60'))  

# Sync behavior
SYNC_ON_SAVE = True  #
SYNC_BATCH_SIZE = 100 

SYNC_QUEUE_FILE = BASE_DIR / 'data/sync_queue.json'


SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

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
            'maxBytes': 10 * 1024 * 1024,  
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
(BASE_DIR / 'logs').mkdir(exist_ok=True)


MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

from pathlib import Path
from datetime import timedelta
from datetime import timezone

BASE_DIR = Path(__file__).resolve().parent.parent


TIME_ZONE = 'Asia/Tashkent'
USE_TZ = True


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'



BOT_TOKEN = "8170384586:AAGX4nKThV-X9xjGTZqgU5t4BrqkrFzPPCc"

CHAT_IDS = [
    6589960007,
    1023732044,
    1345102941
]


STICKERS = {
    'shift_start': 'CAACAgIAAxkBAAEQOqZpZWS4euSKl2PLZpdLttwFKa1F2AACJWIAAj12uUvJkCLvzsfVXDgE',  
    'shift_end': 'CAACAgIAAxkBAAEQOqxpZWT2il8UsiHpQi07tIWe93jR0wAChmAAAqdiuUu0SVLALPDTHzgE',    
    'shift_switch': 'CAACAgIAAxkBAAEQOqppZWTpPjzqPEsc4fAxS3tI4wqrngACQWcAAqBFuUty6UbBXMMhVTgE',  
    'good_stats': 'CAACAgIAAxkBAAEQOqZpZWS4euSKl2PLZpdLttwFKa1F2AACJWIAAj12uUvJkCLvzsfVXDgE',   
    'neutral_stats': 'CAACAgIAAxkBAAEQOqhpZWTSsEDpaDtR7BGRoIrka3HGkQACtGUAAisBuUtbDAYh4513yTgE', 
}

UZB_OFFSET = timedelta(hours=5)
UZB_TZ = timezone(UZB_OFFSET)

SESSION_FILE = "data/active_session.json"
PENDING_FILE = "data/pending_notifications.json"

ORDER_MESSAGES_FILE = "data/order_messages.json"  
PENDING_ORDERS_FILE = "data/pending_order_notifications.json"

RETRY_INTERVAL_SECONDS = 180  