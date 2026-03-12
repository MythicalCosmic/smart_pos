"""
Base settings for smart_jowi project.
Shared between local (POS) and cloud deployments.
"""

from pathlib import Path
import os

from django.urls import reverse_lazy

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-6f=xi1)9e)2l__yw&2-!o%t#gh(mzivf6hwq=t@q^pj_7=s(nu')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '*').split(',')

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', None)
# Application definition
INSTALLED_APPS = [
    "unfold", 
    "unfold.contrib.filters",  
    "unfold.contrib.forms",  
    "unfold.contrib.inlines",  
    "unfold.contrib.import_export",  
    "unfold.contrib.guardian",  
    "unfold.contrib.simple_history", 
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'main',
    'client',
    'stock',
    'corsheaders',
    'rest_framework',
    'drf_spectacular',
    'admins'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'main.middleware.JSONOnlyMiddleware',
]

ROOT_URLCONF = 'smart_jowi.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'templates',
            BASE_DIR / 'main' / 'templates',
            BASE_DIR / 'client' / 'templates',
            BASE_DIR / 'stock' / 'templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'smart_jowi.wsgi.application'


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_TZ = True


# Static files
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# CORS
CORS_ALLOW_ALL_ORIGINS = True


# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# JWT Settings
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', SECRET_KEY)
JWT_ALGORITHM = 'HS256'
JWT_EXPIRY_DAYS = 365


# Unfold Admin Configuration
UNFOLD = {
    "SITE_TITLE": "Smart Jowi Admin",
    "SITE_HEADER": "Smart Jowi",
    "SITE_URL": "/",
    "SITE_SYMBOL": "local_cafe",
    
    "DASHBOARD_CALLBACK": "main.utils.dashboard.dashboard_callback",
    
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": "Dashboard",
                "separator": False,
                "items": [
                    {
                        "title": "Dashboard",
                        "icon": "dashboard",
                        "link": reverse_lazy("admin:index"),
                    },
                ],
            },
            {
                "title": "Orders & Sales",
                "separator": True,
                "items": [
                    {
                        "title": "Orders",
                        "icon": "shopping_cart",
                        "link": reverse_lazy("admin:main_order_changelist"),
                    },
                    {
                        "title": "Cash Register",
                        "icon": "account_balance_wallet",
                        "link": reverse_lazy("admin:main_cashregister_changelist"),
                    },
                    {
                        "title": "Inkassa History",
                        "icon": "receipt_long",
                        "link": reverse_lazy("admin:main_inkassa_changelist"),
                    },
                ],
            },
            {
                "title": "Inventory",
                "separator": True,
                "items": [
                    {
                        "title": "Products",
                        "icon": "inventory_2",
                        "link": reverse_lazy("admin:main_product_changelist"),
                    },
                    {
                        "title": "Categories",
                        "icon": "category",
                        "link": reverse_lazy("admin:main_category_changelist"),
                    },
                ],
            },
            {
                "title": "Users & Access",
                "separator": True,
                "items": [
                    {
                        "title": "Users",
                        "icon": "people",
                        "link": reverse_lazy("admin:main_user_changelist"),
                    },
                    {
                        "title": "Sessions",
                        "icon": "key",
                        "link": reverse_lazy("admin:main_session_changelist"),
                    },
                ],
            },
            {
                "title": "Stock Management",
                "separator": True,
                "items": [
                    {
                        "title": "Stock Items",
                        "icon": "package_2",
                        "link": reverse_lazy("admin:stock_stockitem_changelist"),
                    },
                    {
                        "title": "Stock Levels",
                        "icon": "equalizer",
                        "link": reverse_lazy("admin:stock_stocklevel_changelist"),
                    },
                    {
                        "title": "Batches",
                        "icon": "layers",
                        "link": reverse_lazy("admin:stock_stockbatch_changelist"),
                    },
                    {
                        "title": "Transactions",
                        "icon": "swap_vert",
                        "link": reverse_lazy("admin:stock_stocktransaction_changelist"),
                    },
                    {
                        "title": "Locations",
                        "icon": "location_on",
                        "link": reverse_lazy("admin:stock_stocklocation_changelist"),
                    },
                    {
                        "title": "Categories",
                        "icon": "folder_open",
                        "link": reverse_lazy("admin:stock_stockcategory_changelist"),
                    },
                    {
                        "title": "Units",
                        "icon": "straighten",
                        "link": reverse_lazy("admin:stock_stockunit_changelist"),
                    },
                ],
            },
            {
                "title": "Supply Chain",
                "separator": True,
                "items": [
                    {
                        "title": "Suppliers",
                        "icon": "local_shipping",
                        "link": reverse_lazy("admin:stock_supplier_changelist"),
                    },
                    {
                        "title": "Purchase Orders",
                        "icon": "receipt",
                        "link": reverse_lazy("admin:stock_purchaseorder_changelist"),
                    },
                    {
                        "title": "Receiving",
                        "icon": "move_to_inbox",
                        "link": reverse_lazy("admin:stock_purchasereceiving_changelist"),
                    },
                ],
            },
            {
                "title": "Production",
                "separator": True,
                "items": [
                    {
                        "title": "Recipes",
                        "icon": "menu_book",
                        "link": reverse_lazy("admin:stock_recipe_changelist"),
                    },
                    {
                        "title": "Production Orders",
                        "icon": "precision_manufacturing",
                        "link": reverse_lazy("admin:stock_productionorder_changelist"),
                    },
                    {
                        "title": "Product Links",
                        "icon": "link",
                        "link": reverse_lazy("admin:stock_productstocklink_changelist"),
                    },
                ],
            },
            {
                "title": "Operations",
                "separator": True,
                "items": [
                    {
                        "title": "Transfers",
                        "icon": "sync_alt",
                        "link": reverse_lazy("admin:stock_stocktransfer_changelist"),
                    },
                    {
                        "title": "Stock Counts",
                        "icon": "fact_check",
                        "link": reverse_lazy("admin:stock_stockcount_changelist"),
                    },
                    {
                        "title": "Variance Codes",
                        "icon": "error_outline",
                        "link": reverse_lazy("admin:stock_variancereasoncode_changelist"),
                    },
                ],
            },
            {
                "title": "AI Assistant",
                "separator": True,
                "items": [
                    {
                        "title": "AI Stock Assistant",
                        "icon": "neurology",
                        "link": reverse_lazy("admin:stock_ai_assistant"),
                    },
                ],
            },
            {
                "title": "Settings",
                "separator": True,
                "items": [
                    {
                        "title": "Stock Settings",
                        "icon": "tune",
                        "link": reverse_lazy("admin:stock_stocksettings_changelist"),
                    },
                ],
            },
        ],
    },
}

CSRF_TRUSTED_ORIGINS = [
    'http://92.246.130.137',
    'https://92.246.130.137',
]

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',

    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',  
    ],

    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}



SPECTACULAR_SETTINGS = {
    'TITLE': 'Smart POS',
    'DESCRIPTION': 'Smart POS API documentation',
    'VERSION': '1.0.0',

    'SECURITY': [{'bearerAuth': []}],

    'COMPONENTS': {
        'securitySchemes': {
            'bearerAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
            }
        }
    },
}

