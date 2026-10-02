# =============================================================================
# auth.py — Authentication and Authorization Decorators
# =============================================================================
#
# This module provides:
#   1. get_current_user() — Re-queries MySQL on every protected request to
#      verify that the user still exists and remains active (is_active = 1).
#   2. @login_required — Protects routes requiring an authenticated user.
#   3. @admin_required — Protects routes requiring the 'admin' role.
#
# Flask's request-scoped `g` object (g.current_user) is populated on each
# verified request, giving route handlers and Jinja templates access to fresh
# database-backed user properties without relying on stale session cookies.
# =============================================================================

from functools import wraps
from flask import session, redirect, url_for, flash, g, render_template
from database import get_db_connection


def get_current_user():
    """
    Retrieves the fresh user record from MySQL for the current session['user_id'].

    Returns:
        dict: User dictionary {id, username, email, role, is_active} if found and active.
        None: If session has no user_id, user is deleted, or is_active != 1.
    """
    user_id = session.get('user_id')
    if not user_id:
        return None

    conn = get_db_connection()
    if conn is None:
        return None

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, username, email, role, is_active FROM users WHERE id = %s",
            (user_id,)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and user.get('is_active') == 1:
            return user
        return None
    except Exception:
        if conn and conn.is_connected():
            conn.close()
        return None


def login_required(f):
    """
    Route decorator: ensures the request has an active, database-verified session.
    If unauthenticated or invalid, clears any stale session and redirects to /login.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))

        user = get_current_user()
        if user is None:
            session.clear()
            flash("Your session has expired. Please log in again.", "warning")
            return redirect(url_for('login'))

        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """
    Route decorator: ensures the request has an active session with role == 'admin'.
    If unauthenticated or invalid, clears stale session and redirects to /login.
    If authenticated but not admin, renders 403 Forbidden.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))

        user = get_current_user()
        if user is None:
            session.clear()
            flash("Your session has expired. Please log in again.", "warning")
            return redirect(url_for('login'))

        g.current_user = user

        if user.get('role') != 'admin':
            return render_template('auth/403.html'), 403

        return f(*args, **kwargs)
    return decorated_function


def player_required(f):
    """
    Route decorator: ensures the request has an active session with role == 'player'.
    If unauthenticated or invalid, clears stale session and redirects to /login.
    If authenticated but not player (e.g. admin or other role), renders 403 Forbidden.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))

        user = get_current_user()
        if user is None:
            session.clear()
            flash("Your session has expired. Please log in again.", "warning")
            return redirect(url_for('login'))

        g.current_user = user

        if user.get('role') != 'player':
            return render_template('auth/403.html'), 403

        return f(*args, **kwargs)
    return decorated_function

