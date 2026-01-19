"""
Cloud settings for central server.
SQLite database, receives sync from branches.

Usage:
    gunicorn smart_jowi.wsgi --env DJANGO_SETTINGS_MODULE=smart_jowi.settings.cloud
    
Environment variables:
    ALLOWED_BRANCH_TOKENS - Comma-separated list of valid branch tokens
"""

from .base import *

# =============================================================================
# DEPLOYMENT MODE
# =============================================================================
DEPLOYMENT_MODE = 'cloud'


# =============================================================================
# SECURITY - Production settings
# =============================================================================
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '*').split(',')

# HTTPS settings (disable for local network)
SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'False').lower() == 'true'
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False


# =============================================================================
# DATABASE - SQLite for cloud (simple setup)
# =============================================================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_cloud.sqlite3',
        'OPTIONS': {
            'timeout': 30,  # Longer timeout for concurrent access
        }
    }
}


# =============================================================================
# CACHE - Redis if available, fallback to local memory
# =============================================================================
REDIS_URL = os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/1')

try:
    import redis
    r = redis.Redis.from_url(REDIS_URL)
    r.ping()
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            },
            'KEY_PREFIX': 'smartjowi_cloud',
            'TIMEOUT': 300,
        }
    }
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
            },
        },
    }
except:
    # Fallback to local memory cache if Redis unavailable
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'smartjowi-cloud',
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
SYNC_ENABLED = False  # Cloud doesn't push, only receives

# Authorized branches that can sync to this cloud
ALLOWED_BRANCH_TOKENS = ['branch-secret-token-12345']

# Real-time updates via WebSocket
REALTIME_UPDATES_ENABLED = True


# =============================================================================
# STATIC FILES - Production
# =============================================================================
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'


# =============================================================================
# LOGGING - Production
# =============================================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
        'json': {
            'class': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'main.services.sync': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}


# =============================================================================
# REST FRAMEWORK - Tighter throttling for cloud
# =============================================================================
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        'sync': '60/minute',  # Special rate for sync endpoints
    }
}
