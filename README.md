# Smart POS

> Enterprise-grade restaurant management backend with service-oriented architecture, multi-branch support, and real-time cloud synchronization

![Python](https://img.shields.io/badge/Python-3.13+-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.x-092E20?logo=django&logoColor=white)
![DRF](https://img.shields.io/badge/DRF-3.x-ff1709?logo=django&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

Smart POS is a production-ready backend API for restaurant point-of-sale systems. Built with a clean service-layer architecture, it handles order management, kitchen coordination, inventory tracking, Telegram notifications, and multi-branch operations with real-time cloud sync.

---

## ✨ Features

### 📋 Order Management
- Dine-in, takeaway, and delivery orders
- Table management and floor plans
- Split bills and multiple payment methods
- Order modifications and special requests
- Real-time order status tracking

### 👨‍🍳 Kitchen Display System (KDS)
- Real-time order queue for kitchen staff
- Order prioritization and timing
- Per-item completion tracking
- Multi-station support

### 🖥️ Customer Display
- Secondary display API endpoints
- Live order summary and totals

### 📦 Inventory & Stock Management
- Real-time stock tracking
- Low stock alerts
- Ingredient-level inventory
- Stock movement history

### 🏢 Multi-Branch Support
- Centralized management across locations
- Branch-specific configurations
- Cross-branch reporting
- Per-branch permissions

### ☁️ Cloud Synchronization
- Real-time sync between terminals and cloud
- Offline-first with automatic reconnection
- Conflict resolution with sync queue
- Sync status monitoring

### 🖨️ Thermal Printing
- 80mm receipt printing (ESC/POS)
- Kitchen order tickets
- Shift and daily reports
- Customizable templates

### 📱 Telegram Bot Integration
- New order notifications
- Shift open/close alerts
- Pending order reminders
- Configurable per-branch

### 💳 Payments & Shifts
- Cash and card payments
- Shift management with reports
- Active session tracking
- Payment reconciliation

---

## 🏗️ Architecture

Smart POS follows a **service-oriented architecture** with clear separation between business logic, data access, and presentation layers.

```
┌─────────────────────────────────────────────────────────────────┐
│                       SMART POS BACKEND                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   PRESENTATION LAYER                                            │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐    │
│   │   Client    │  │    Main     │  │       Stock         │    │
│   │   Views     │  │    Views    │  │       Views         │    │
│   └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘    │
│          │                │                     │               │
│   ───────┴────────────────┴─────────────────────┴───────────   │
│                           │                                     │
│   MIDDLEWARE LAYER        │                                     │
│   ┌───────────────────────▼───────────────────────────────┐    │
│   │              Custom Middleware Pipeline               │    │
│   └───────────────────────┬───────────────────────────────┘    │
│                           │                                     │
│   SERVICE LAYER           │                                     │
│   ┌───────────────────────▼───────────────────────────────┐    │
│   │  services/  │  helpers/  │  utils/  │  bot/           │    │
│   │  Business   │  Shared    │  Common  │  Telegram       │    │
│   │  Logic      │  Helpers   │  Utils   │  Integration    │    │
│   └───────────────────────┬───────────────────────────────┘    │
│                           │                                     │
│   DATA LAYER              │                                     │
│   ┌───────────────────────▼───────────────────────────────┐    │
│   │  models.py  │  sync_mixin.py  │  migrations/          │    │
│   └───────────────────────┬───────────────────────────────┘    │
│                           │                                     │
│   ┌───────────────────────▼───────────────────────────────┐    │
│   │     SQLite (Local)    │    PostgreSQL (Cloud)         │    │
│   └───────────────────────────────────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Framework** | Django 4.x |
| **API** | Django REST Framework |
| **Database** | SQLite (local) / PostgreSQL (cloud) |
| **Async** | ASGI with `asgi.py` |
| **Notifications** | Telegram Bot API |
| **Printing** | ESC/POS Protocol |

---

## 📁 Project Structure

```
smart_pos/
│
├── main/                       # Core application
│   ├── bot/                   # Telegram bot integration
│   ├── helpers/               # Shared helper functions
│   ├── management/            # Custom Django commands
│   ├── migrations/            # Database migrations
│   ├── services/              # Business logic layer
│   ├── templates/             # Email/report templates
│   ├── utils/                 # Utility functions
│   ├── views/                 # API view modules
│   ├── models.py              # Database models
│   ├── middleware.py          # Custom middleware
│   ├── sync_mixin.py          # Cloud sync functionality
│   ├── urls.py                # URL routing
│   └── admin.py               # Admin configuration
│
├── client/                     # Client-facing API
│   ├── migrations/            # Client model migrations
│   ├── templates/             # Client templates
│   ├── models.py              # Client-specific models
│   ├── views.py               # Client API endpoints
│   └── urls.py                # Client URL routing
│
├── stock/                      # Inventory management
│   └── ...                    # Stock models & views
│
├── smart_jowi/                 # Django project config
│   ├── settings/              # Settings modules
│   ├── urls.py                # Root URL config
│   ├── asgi.py                # ASGI config
│   └── wsgi.py                # WSGI config
│
├── data/                       # Runtime data files
│   ├── active_session.json    # Current session state
│   ├── bot_config.json        # Telegram bot settings
│   ├── order_messages.json    # Order notification queue
│   ├── pending_notifications.json
│   ├── pending_order_notifications.json
│   ├── sync_queue.json        # Pending sync operations
│   └── sync_status.json       # Sync state tracking
│
├── logs/                       # Application logs
├── media/                      # Uploaded files
│
├── db.sqlite3                  # Local database
├── db_cloud.sqlite3            # Cloud database cache
│
├── manage.py                   # Django CLI
├── requirements.txt            # Dependencies
├── .env                        # Environment config
├── .env.cloud                  # Cloud sync config
├── .env-example                # Config template
│
├── install.bat                 # Windows installer
├── setup_database.bat          # DB setup script
├── start.bat                   # Start server
├── stop.bat                    # Stop server
└── hide_console.ps1            # Background runner
```

---

## 📦 Installation

### Prerequisites

- Python 3.10+
- Git

### Quick Start (Windows)

```bash
# Clone the repository
git clone https://github.com/MythicalCosmic/smart_pos.git
cd smart_pos

# Run installer
install.bat

# Setup database
setup_database.bat

# Start the server
start.bat
```

### Manual Installation

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env-example .env
# Edit .env with your settings

# Run migrations
python manage.py migrate

# Create admin user
python manage.py createsuperuser

# Start development server
python manage.py runserver
```

---

## ⚙️ Configuration

### Environment Variables (`.env`)

```env
# Django
SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=sqlite:///db.sqlite3

# Branch Settings
BRANCH_ID=1
BRANCH_NAME=Main Branch

# Telegram Bot
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
TELEGRAM_ENABLED=True

# Printer
PRINTER_ENABLED=True
PRINTER_NAME=POS-80
RECEIPT_WIDTH=80
```

### Cloud Configuration (`.env.cloud`)

```env
# Cloud Database
CLOUD_DATABASE_URL=postgresql://user:pass@host:5432/smart_pos

# Sync Settings
SYNC_ENABLED=True
SYNC_INTERVAL=30
CLOUD_API_URL=https://your-cloud-server.com/api
CLOUD_API_KEY=your-api-key
```

---

## 🔌 API Structure

### Main App Endpoints (`/api/`)

| Resource | Endpoints | Description |
|----------|-----------|-------------|
| **Orders** | `/api/orders/` | Order CRUD & status |
| **Products** | `/api/products/` | Menu items |
| **Categories** | `/api/categories/` | Product categories |
| **Tables** | `/api/tables/` | Table management |
| **Shifts** | `/api/shifts/` | Shift operations |
| **Reports** | `/api/reports/` | Sales & inventory reports |
| **Kitchen** | `/api/kitchen/` | KDS endpoints |

### Client App Endpoints (`/client/`)

| Resource | Description |
|----------|-------------|
| **Display** | Customer-facing display data |
| **Session** | Active session management |

### Stock App Endpoints (`/stock/`)

| Resource | Description |
|----------|-------------|
| **Inventory** | Stock levels |
| **Movements** | Stock transactions |
| **Alerts** | Low stock notifications |

---

## 🔄 Sync System

Smart POS uses a robust offline-first sync architecture:

### Data Files

| File | Purpose |
|------|---------|
| `active_session.json` | Current cashier session |
| `sync_queue.json` | Pending sync operations |
| `sync_status.json` | Last sync timestamps |
| `pending_notifications.json` | Queued Telegram messages |
| `order_messages.json` | Order notification templates |

### Sync Flow

```
Local Change → sync_queue.json → Cloud API → Confirmation → Clear Queue
                    ↓
            (If offline, retry on reconnect)
```

### Sync Mixin

Models inherit from `sync_mixin.py` to enable automatic cloud synchronization:

```python
class Order(SyncMixin, models.Model):
    # Automatically syncs to cloud on save
    ...
```

---

## 📱 Telegram Bot

### Configuration (`data/bot_config.json`)

```json
{
  "bot_token": "your-token",
  "chat_id": "your-chat-id",
  "notifications": {
    "new_order": true,
    "shift_open": true,
    "shift_close": true,
    "low_stock": true
  }
}
```

### Notification Types

| Event | Message |
|-------|---------|
| 🆕 New Order | Order #{id} - {items} - {total} |
| ✅ Shift Open | Shift opened by {cashier} |
| 🔒 Shift Close | Shift closed - Total: {amount} |
| ⚠️ Low Stock | {product} is running low ({qty} left) |

---

## 🖨️ Printing

### Supported Printers

- 80mm USB thermal printers
- ESC/POS compatible devices
- Network printers via IP

### Print Jobs

- Customer receipts
- Kitchen order tickets
- Shift reports
- Daily summaries

---

## 🚀 Deployment

### Production (Windows Service)

```bash
# Start in background
start.bat

# Or use PowerShell script
powershell -ExecutionPolicy Bypass -File hide_console.ps1
```

### Production (Linux)

```bash
# Using Gunicorn
gunicorn smart_jowi.wsgi:application --bind 0.0.0.0:8000

# Using ASGI (for async support)
uvicorn smart_jowi.asgi:application --host 0.0.0.0 --port 8000
```

---

## 🛡️ Security

- Token-based API authentication
- Role-based access control (Admin, Cashier, Kitchen)
- Session management with timeout
- Encrypted cloud communication
- Audit logging for all transactions

---

## 🐛 Troubleshooting

### Server Issues

```bash
# Port already in use
netstat -ano | findstr :8000
taskkill /PID <pid> /F

# Use different port
python manage.py runserver 8001
```

### Database Issues

```bash
# Reset migrations
python manage.py migrate --run-syncdb

# Fresh start
del db.sqlite3
python manage.py migrate
python manage.py createsuperuser
```

### Sync Issues

```bash
# Clear sync queue
del data\sync_queue.json

# Check sync status
type data\sync_status.json
```

### Telegram Not Working

1. Verify bot token in `.env`
2. Check `data/bot_config.json`
3. Ensure bot is added to chat
4. Check `data/pending_notifications.json` for queue

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/NewFeature`)
3. Commit changes (`git commit -m 'Add NewFeature'`)
4. Push to branch (`git push origin feature/NewFeature`)
5. Open a Pull Request

---

**Enterprise-ready POS backend built for reliability and scale.**
