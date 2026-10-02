# SportsPro — Sports Management System

A full-stack web application for managing sports organizations, tournaments, teams, players, match scheduling, results tracking, and performance analytics. Built with Python Flask and MySQL as a college project.

🌐 **Live Demo:** [sports-management-system-wqz2.onrender.com](https://sports-management-system-wqz2.onrender.com)

---

## Features

### Public Access
- Public homepage with system overview and statistics
- Player self-registration with secure password hashing
- Login / logout with session-based authentication

### Player Dashboard
- Personal dashboard with upcoming matches, recent results, and career statistics
- Profile management (update personal details and jersey number)
- View team roster, match history, and individual performance stats

### Admin Dashboard
- **Sports Management** — Create, edit, and delete sports categories
- **Team Management** — Create teams linked to sports, manage rosters
- **Player Management** — Add players, assign to teams, link to user accounts
- **Tournament Management** — Create tournaments with date ranges and status tracking
- **Match Scheduling** — Schedule matches between teams within tournaments, set venues and dates
- **Results & Scoring** — Record match results with score validation and winner determination
- **Tournament Standings** — Auto-calculated league tables with points, wins, draws, losses, goal/run differentials
- **Reports & Analytics** — System-wide KPI dashboard, tournament breakdowns, top player leaderboards
- **CSV Exports** — Export standings, matches, player statistics, and team summaries
- **User Management** — View all accounts, toggle active/inactive status, change user roles

### Security
- CSRF protection on all forms (Flask-WTF)
- Scrypt password hashing (Werkzeug)
- Role-based access control (`@login_required`, `@admin_required`, `@player_required`)
- Session security (HttpOnly, SameSite=Lax, configurable Secure flag)
- Security response headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy)
- SQL injection prevention via parameterized queries
- Reverse proxy support (ProxyFix for Render HTTPS)

---

## Technology Stack

| Layer | Technology |
| :--- | :--- |
| Backend | Python 3, Flask 3.1 |
| Database | MySQL 8.0 (Aiven managed) |
| Frontend | Jinja2 templates, vanilla CSS, vanilla JavaScript |
| Auth | Werkzeug scrypt hashing, Flask sessions, Flask-WTF CSRF |
| Deployment | Render (Gunicorn WSGI), Aiven MySQL with TLS |

---

## Project Structure

```
Sports-Management-System/
├── app.py                  # Main Flask application (routes, logic, WSGI entry)
├── auth.py                 # Authentication decorators and session helpers
├── config.py               # Environment variable loader (DB_CONFIG, APP_CONFIG)
├── database.py             # MySQL connection factory (get_db_connection)
├── create_admin.py         # CLI script to create admin accounts
├── create_user.py          # CLI script to create player accounts
├── requirements.txt        # Python dependencies (pinned versions)
├── Procfile                # Render/Gunicorn startup command
├── .env.example            # Template for environment variables (no secrets)
├── .gitignore              # Git exclusion rules
│
├── templates/              # Jinja2 HTML templates
│   ├── layout/base.html    #   Base template (nav, flash messages, footer)
│   ├── index.html          #   Public homepage
│   ├── auth/               #   Login, register, error pages (400-500)
│   ├── admin/              #   18 admin management templates
│   └── player/             #   Player dashboard and profile
│
├── static/                 # Client-side assets
│   ├── css/style.css       #   Application stylesheet
│   └── js/script.js        #   Frontend interactivity and validation
│
├── database/               # Database files
│   ├── schema.sql          #   Full schema with comments (local dev)
│   ├── schema_deploy.sql   #   Deployment schema (IF NOT EXISTS, no USE stmt)
│   ├── demo_data.sql       #   Fictional seed data for demonstrations
│   └── ca.pem              #   Aiven CA certificate for TLS connections
│
├── tests/                  # Unit and integration tests (271 tests)
│   ├── conftest.py         #   Path configuration for test discovery
│   └── test_*.py           #   17 test modules covering all phases
│
└── docs/                   # Project documentation and reports
    ├── PHASE_11A_DEPLOYMENT_READINESS.md
    ├── PHASE_11A_FINAL_CHECK.md
    ├── phase8_completion_report.md
    ├── phase9_completion_report.md
    ├── phase_9_5_report.md
    ├── phase_10_security_audit_report.md
    ├── player_dashboard_access_report.md
    ├── player_registration_report.md
    └── user_experience_review.md
```

---

## Local Setup

### Prerequisites
- Python 3.10+
- MySQL 8.0+ (local or remote)
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/malisunny543-pixel/Sports-Management-System.git
cd Sports-Management-System

# Create and activate virtual environment
python -m venv venv

# Windows
.\venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Environment Variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

| Variable | Description | Example |
| :--- | :--- | :--- |
| `FLASK_SECRET_KEY` | Random hex string for session signing | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FLASK_ENV` | `development` or `production` | `development` |
| `DB_HOST` | MySQL server hostname | `localhost` |
| `DB_PORT` | MySQL server port | `3306` |
| `DB_USER` | MySQL username | `root` |
| `DB_PASSWORD` | MySQL password | *(your password)* |
| `DB_NAME` | Database name | `sports_management` |
| `DB_SSL_CA` | Path to CA cert (optional, for Aiven) | `database/ca.pem` |

### Database Setup

```sql
-- Create the database in MySQL
CREATE DATABASE sports_management;
```

```bash
# Import the schema
mysql -u root -p sports_management < database/schema.sql

# (Optional) Import demo data
mysql -u root -p sports_management < database/demo_data.sql
```

### Create Admin Account

```bash
python create_admin.py
```

### Run the Application

```bash
python app.py
```

The application will be available at `http://127.0.0.1:5000`.

---

## Running Tests

All 271 tests use Python's built-in `unittest` framework:

```bash
# Run all tests
python -m pytest tests/ -v

# Or with unittest
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## Deployment (Render + Aiven MySQL)

The application is deployed on [Render](https://render.com) with a managed MySQL database on [Aiven](https://aiven.io).

**Render Settings:**
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn app:app --workers 2 --bind 0.0.0.0:$PORT --timeout 120 --log-file=-`

Set all environment variables from the table above in the Render dashboard. For Aiven MySQL, set `DB_SSL_CA` to the container path of the CA certificate (e.g., `/opt/render/project/src/database/ca.pem`).

See [`docs/PHASE_11A_DEPLOYMENT_READINESS.md`](docs/PHASE_11A_DEPLOYMENT_READINESS.md) for detailed deployment instructions.

---

## Screenshots

*Screenshots will be added in a future update.*

---

## License

This project was developed as a college project for educational purposes.
