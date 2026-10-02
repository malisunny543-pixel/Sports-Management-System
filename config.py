# =============================================================================
# config.py — Database and Application Configuration
# =============================================================================
#
# WHAT DOES THIS FILE DO?
#   This file reads your database settings from environment variables
#   (stored in the .env file) and makes them available to the rest of
#   the application as a neat Python dictionary called DB_CONFIG.
#
# WHY USE ENVIRONMENT VARIABLES INSTEAD OF HARDCODING?
#   Hardcoding means writing the password directly in the code:
#       password = "mysecretpassword123"   ← NEVER do this
#
#   With environment variables, the password lives in .env on YOUR machine,
#   never in the code. When you push to GitHub, the password stays private.
#
# HOW IT WORKS:
#   1. python-dotenv reads your .env file when Flask starts up
#   2. The values from .env are loaded into os.environ (Python's env store)
#   3. os.getenv('DB_HOST') retrieves the value of DB_HOST from os.environ
#   4. A fallback default is provided in case the variable is missing
#
# =============================================================================

import os                    # Built-in Python module: reads environment variables
from dotenv import load_dotenv  # pip package: loads .env file into os.environ

# -----------------------------------------------------------------------------
# load_dotenv() scans for a .env file in the current directory (where app.py is)
# and loads every KEY=VALUE pair into Python's environment.
# If no .env file exists, it silently continues — no crash.
# -----------------------------------------------------------------------------
load_dotenv()

# =============================================================================
# DB_CONFIG — MySQL Connection Settings
# =============================================================================
#
# This dictionary holds all the information needed to open a connection
# to your MySQL database. It is imported by database.py and used whenever
# the app needs to talk to MySQL.
#
# os.getenv('VARIABLE_NAME', 'default_value')
#   → Returns the value of VARIABLE_NAME from .env
#   → If VARIABLE_NAME is not found, returns 'default_value' instead
#
# =============================================================================
# Base connection parameters (required in all environments)
_db_base = {
    'host':     os.getenv('DB_HOST', 'localhost'),   # MySQL server address
    'port':     int(os.getenv('DB_PORT', '3306')),   # MySQL port (must be int)
    'user':     os.getenv('DB_USER', 'root'),        # MySQL username
    'password': os.getenv('DB_PASSWORD', ''),        # MySQL password (from .env)
    'database': os.getenv('DB_NAME', 'sports_management'),  # Target database
}

# Optional TLS/SSL for managed databases (e.g. Aiven).
# Set DB_SSL_CA to the path of the CA certificate file (ca.pem) when required.
# Leave unset for local development — no SSL will be configured.
_ssl_ca = os.getenv('DB_SSL_CA', '')
if _ssl_ca:
    _db_base['ssl_ca']      = _ssl_ca
    _db_base['ssl_verify_cert'] = True
    _db_base['ssl_verify_identity'] = True

DB_CONFIG = _db_base

# =============================================================================
# APP_CONFIG — Flask Application Settings
# =============================================================================
APP_CONFIG = {
    # SECRET_KEY: Flask uses this to cryptographically sign session cookies.
    # A weak or hardcoded key is a security risk in production.
    'secret_key': os.getenv('FLASK_SECRET_KEY', 'dev-only-change-in-production'),

    # FLASK_ENV: 'production' enables secure-cookie and disables debug.
    # Set FLASK_ENV=production in the Render environment variables panel.
    'env': os.getenv('FLASK_ENV', 'development'),

    # SESSION_COOKIE_SECURE: True forces cookies over HTTPS only.
    # Controlled by the FLASK_ENV value or an explicit SESSION_COOKIE_SECURE env var.
    # Automatically True when FLASK_ENV=production unless explicitly overridden.
    'session_cookie_secure': os.getenv(
        'SESSION_COOKIE_SECURE',
        'true' if os.getenv('FLASK_ENV') == 'production' else 'false'
    ).lower() == 'true',
}
