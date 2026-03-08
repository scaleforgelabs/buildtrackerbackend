# BuildTracker Backend

BuildTracker is a robust, enterprise-grade project management and collaboration platform tailored for industries requiring structured workflows, intensive documentation, and rigorous file management. The backend is powered by Django and follows a highly modular architecture designed for scalability, security, and developer productivity.

---

## 🚀 Tech Stack

- **Framework:** Django 4.2 (LTS) & Django REST Framework (DRF)
- **Database:** PostgreSQL (Primary) & Redis (Cache/Broker)
- **Asynchronous Processing:** Celery (Redis Broker)
- **Authentication:** JWT (Rotational tokens), Social Login (Google & Apple OAuth)
- **Communications:** SMTP (Gmail) & SMS (Twilio Integration)
- **Documentation:** drf-spectacular (OpenAPI 3.0, Swagger UI, ReDoc)
- **Security:** CSRF/XSS protection via `Middleware` & `Bleach`, Secure Cookie handling
- **Storage:** Amazon S3 (via `django-storages` & `boto3`)
- **Payments:** Paystack & Flutterwave Integration

---

## 📁 System Architecture & Modules

The backend is composed of several specialized applications, each handling a distinct domain of the platform:

### Core Infrastructure
- **`auth_func`**: Advanced authentication engine supporting standard login, OTP verification, and secure social auth (Google/Apple).
- **`workspaces`**: The primary organizational unit. Manages collaboration boundaries and member roles.
- **`organizations`**: Multi-tenant structure providing an extra layer of governance above workspaces.
- **`subscriptions`**: Professional billing engine integrated with Nigerian payment gateways for plan management.

### Productivity & Collaboration
- **`tasks`**: High-performance task tracking with support for attachments, comments, milestones, and sprints.
- **`wiki`**: Integrated knowledge base for documentation and team wikis.
- **`files`**: Centralized file vault with strict security validation and cloud storage integration.
- **`search`**: Cross-module global search powered by indexed DRF views.

### System Intelligence & Monitoring
- **`monitoring`**: Real-time health metrics including CPU, RAM, and database connection tracking.
- **`analytics`**: Usage data insights and trend reporting for organization owners.
- **`logs`**: Comprehensive audit trails capturing system events, user activity, and workspace changes.

### Communication & Messaging
- **`notifications`**: Multi-channel notification center for real-time in-app alerts and updates.
- **Unified Messaging**: Centralized `core/messaging` logic supporting dual-channel notification (Email + SMS) for critical system events.
- **Automated Alerts**: Celery-driven tasks for deadline reminders, daily summaries, and subscription status updates.

### Utility & Maintenance
- **`backup`**: Facilities for full or incremental workspace backups and data exports.
- **`quicklinks`**: User-defined shortcuts for rapid navigation within workspaces.
- **`waitlist`**: Early-access user management.
- **`widgets`**: Extensible UI component data providers.

---

## 🛠️ Getting Started

### Prerequisites
- **Python 3.8+**
- **Redis** (Used for caching and as a message broker for Celery)
- **PostgreSQL** (Recommended development database)

### Installation

1. **Clone and Install:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configuration:**
   The system relies on environment variables for security.
   ```bash
   cp .env.example .env
   # Edit .env and provide your Database, AWS, and Social Auth credentials.
   ```

3. **Database Setup:**
   ```bash
   python manage.py migrate
   ```

4. **Start Development Infrastructure:**
   - **Main Server:** `python manage.py runserver`
   - **Celery Worker:** `celery -A buildtracker__backend worker --loglevel=info`

---

## 🛡️ Security Features

BuildTracker implements several advanced security measures:
- **Redacted Logging:** Multi-layered middleware prevents sensitive fields (passwords, tokens, secret keys) from being logged or exposed in stack traces.
- **ID Token Verification:** Cryptographic signature checks for social logins.
- **Dual-Channel OTP:** Secure 2FA/Verification via simultaneous Email and SMS (Twilio) for registration and critical account changes.
- **File Guard:** Extension whitelisting and size validation occur at the serializer level.
- **HSTS & Secure Cookies:** Enforced production-level headers to mitigate session hijacking.

---

## 📖 API Documentation

The backend automatically generates interactive documentation for all endpoints:

- **Swagger UI:** [/swagger/](http://localhost:8000/swagger/) (Interactive testing)
- **ReDoc:** [/redoc/](http://localhost:8000/redoc/) (Clean documentation)
- **OpenAPI Schema:** [/api/schema/](http://localhost:8000/api/schema/) (JSON/YAML download)

---

## 🧪 Support & Maintenance
For system maintenance, use the following core utilities:
- **Health Check:** `GET /api/index/`
- **Cache Verification:** `GET /api/cached-data/`
- **Async Task Check:** `POST /api/trigger-task/`