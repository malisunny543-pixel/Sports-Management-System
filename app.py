# =============================================================================
# app.py — The heart of our Flask application
# =============================================================================
#
# What is Flask?
# Flask is a "micro web framework" for Python. "Micro" doesn't mean it's
# limited — it means Flask gives you the essentials and lets you add only
# what you need. It handles:
#   1. Receiving HTTP requests from browsers (GET, POST, etc.)
#   2. Running your Python code to process those requests
#   3. Sending back an HTML response to the browser
#
# PHASE 4 ADDITIONS:
#   - CSRF protection across all forms via Flask-WTF
#   - Session security hardening (HttpOnly, SameSite=Lax, Session Fixation Defense)
#   - Authentication routes: /login (GET+POST), /logout (POST only)
#   - Role-protected dashboards: /admin/dashboard and /player/dashboard
#   - Automatic request-scoped user verification (g.current_user)
# =============================================================================

import csv
import io
import re
from datetime import timedelta, date, datetime
from flask import (
    Flask, render_template, jsonify, request, redirect, url_for, session, flash, g, abort, make_response, Response
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import HTTPException
from flask_wtf.csrf import CSRFProtect
from mysql.connector import Error as MySQLError

from config import APP_CONFIG, DB_CONFIG

# database.py has our reusable MySQL connection function
from database import get_db_connection

# auth.py provides decorators and session verification
from auth import login_required, admin_required, player_required, get_current_user

# ProxyFix: tells Werkzeug to trust the X-Forwarded-* headers from Render's
# TLS-terminating reverse proxy so HTTPS-based redirects and secure cookies work.
from werkzeug.middleware.proxy_fix import ProxyFix

# =============================================================================
# Application Initialization & Security Configuration
# =============================================================================
app = Flask(__name__)

# Trust X-Forwarded-* headers from exactly one upstream proxy (Render's router).
# x_for=1: trust one forwarded IP (real client IP via Render)
# x_proto=1: trust forwarded protocol (https)
# x_host=1: trust forwarded hostname
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Secret key for cryptographic signing of sessions and CSRF tokens
app.config['SECRET_KEY'] = APP_CONFIG['secret_key']

# -----------------------------------------------------------------------------
# Session Security Settings
# -----------------------------------------------------------------------------
# 1. HttpOnly: Prevents client-side scripts from reading the session cookie (XSS protection)
app.config['SESSION_COOKIE_HTTPONLY'] = True

# 2. SameSite=Lax: Restricts cookie delivery on cross-site requests (CSRF mitigation)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# 3. Secure: True in production (HTTPS-only cookies). False in local dev (HTTP allowed).
#    Driven by FLASK_ENV=production or SESSION_COOKIE_SECURE=true in .env / Render vars.
app.config['SESSION_COOKIE_SECURE'] = APP_CONFIG['session_cookie_secure']

# 4. Session Lifetime: 2-hour inactivity sliding expiration
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

# Enable CSRF Protection globally
csrf = CSRFProtect(app)


# =============================================================================
# Request Context Hook: Populate g.current_user
# =============================================================================
@app.before_request
def load_logged_in_user():
    """
    Runs before every request. Populates Flask's request-scoped `g.current_user`
    from the database if a valid, active session exists.
    Available to all templates and routes.
    """
    g.current_user = get_current_user()


@app.after_request
def add_security_headers(response):
    """
    Applies standard defensive HTTP security response headers across all routes.
    """
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response


# =============================================================================
# Public Routes
# =============================================================================
@app.route('/')
def index():
    """
    Public SportsPro homepage.
    Displays product overview, key platform capabilities, live statistics,
    and role-based action CTAs.
    """
    stats = {
        'sports_count': 0,
        'tournaments_count': 0,
        'teams_count': 0,
        'players_count': 0,
        'matches_count': 0
    }
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT COUNT(*) AS c FROM sports")
            stats['sports_count'] = cursor.fetchone()['c']
            cursor.execute("SELECT COUNT(*) AS c FROM tournaments")
            stats['tournaments_count'] = cursor.fetchone()['c']
            cursor.execute("SELECT COUNT(*) AS c FROM teams")
            stats['teams_count'] = cursor.fetchone()['c']
            cursor.execute("SELECT COUNT(*) AS c FROM players")
            stats['players_count'] = cursor.fetchone()['c']
            cursor.execute("SELECT COUNT(*) AS c FROM matches WHERE status = 'completed'")
            stats['matches_count'] = cursor.fetchone()['c']
            cursor.close()
            conn.close()
        except Exception:
            if conn and conn.is_connected():
                conn.close()

    return render_template('index.html', stats=stats)



@app.route('/health')
def health():
    """
    Minimal public health endpoint for Render's uptime monitor.
    Returns HTTP 200 with {"status": "ok"} when the database is reachable,
    or HTTP 503 with {"status": "error"} if it is not.
    Exposes NO credentials, host names, ports, versions, or internal configuration.
    """
    conn = get_db_connection()
    if conn is None:
        return jsonify({"status": "error", "detail": "Database unavailable."}), 503
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        return jsonify({"status": "ok"}), 200
    except Exception:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"status": "error", "detail": "Database unavailable."}), 503


@app.route('/admin/db-test')
@login_required
@admin_required
def admin_db_test():
    """
    Admin-only database diagnostic endpoint.
    Accessible only to authenticated administrators.
    Returns MySQL version and connected database name — never credentials or host strings.
    """
    conn = get_db_connection()
    if conn is None:
        return jsonify({"status": "FAILED", "error": "Could not connect to MySQL."}), 503

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.execute("SELECT VERSION()")
        mysql_version = cursor.fetchone()[0]
        cursor.execute("SELECT DATABASE()")
        connected_db = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return jsonify({
            "status": "SUCCESS",
            "mysql_version": mysql_version,
            "connected_database": connected_db,
            "message": "Flask → MySQL connection is working."
        })
    except Exception as e:
        app.logger.error("Database connection error in /admin/db-test: %s", e)
        if conn and conn.is_connected():
            conn.close()
        return jsonify({
            "status": "FAILED",
            "error": "A database error occurred while testing the connection."
        }), 500




# =============================================================================
# Authentication Routes
# =============================================================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Public self-registration for player accounts.
    GET: Renders player registration form (or redirects if already authenticated).
    POST: Validates username, email, password; enforces role='player' (server-side);
          hashes password securely; stores account in database;
          flashes success message and redirects to login.
    """
    # If user is already authenticated with an active account, redirect to dashboard
    if g.current_user:
        if g.current_user['role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('player_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        def render_form_error(msg):
            flash(msg, "error")
            return render_template('auth/register.html', username=username, email=email)

        # 1. Username validation
        if not username:
            return render_form_error("Username is required and cannot be empty.")
        if len(username) > 50:
            return render_form_error("Username cannot exceed 50 characters.")
        if " " in username:
            return render_form_error("Username cannot contain spaces.")
        if not re.match(r'^[a-zA-Z0-9_.-]+$', username):
            return render_form_error("Username may only contain letters, numbers, dots, hyphens, and underscores.")

        # 2. Email validation
        if not email:
            return render_form_error("Email address is required.")
        if len(email) > 150:
            return render_form_error("Email address cannot exceed 150 characters.")
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            return render_form_error("Please enter a valid email address.")

        # 3. Password validation
        if not password or len(password) < 8:
            return render_form_error("Password must be at least 8 characters long.")
        if len(password) > 128:
            return render_form_error("Password cannot exceed 128 characters.")
        if password != confirm_password:
            return render_form_error("Passwords do not match. Please re-enter.")

        conn = get_db_connection()
        if conn is None:
            flash("Database service unavailable. Please try again later.", "error")
            return render_template('auth/register.html', username=username, email=email)

        try:
            cursor = conn.cursor(dictionary=True)

            # Check username uniqueness
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return render_form_error(f"Username '{username}' is already taken. Please choose another.")

            # Check email uniqueness
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return render_form_error(f"Email '{email}' is already registered. Please sign in or use another email.")

            # Hash password and insert - Mandatory: role is strictly 'player'
            pwd_hash = generate_password_hash(password)
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 1)
                """,
                (username, email, pwd_hash)
            )
            conn.commit()
            cursor.close()
            conn.close()

            flash("Registration successful! You may now sign in to your Player Portal.", "success")
            return redirect(url_for('login'))

        except MySQLError as e:
            if conn and conn.is_connected():
                conn.rollback()
                conn.close()
            if e.errno == 1062:
                return render_form_error("A user with that username or email already exists.")
            flash("A database error occurred while creating your account. Please try again.", "error")
            return render_template('auth/register.html', username=username, email=email)
        except Exception:
            if conn and conn.is_connected():
                conn.rollback()
                conn.close()
            flash("An unexpected error occurred. Please try again.", "error")
            return render_template('auth/register.html', username=username, email=email)
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    return render_template('auth/register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Handles user login.
    GET: Renders login form (or redirects if already logged in).
    POST: Validates credentials, executes session fixation defense,
          stores identity in session, and redirects by role.
    """
    # If user is already authenticated with an active account, redirect to dashboard
    if g.current_user:
        if g.current_user['role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('player_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Basic form presence validation
        if not username or not password:
            flash("Please enter both username and password.", "error")
            return render_template('auth/login.html', username=username)

        conn = get_db_connection()
        if conn is None:
            flash("Database service unavailable. Please try again later.", "error")
            return render_template('auth/login.html', username=username)

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, username, email, password_hash, role, is_active FROM users WHERE username = %s",
                (username,)
            )
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            # Generic error policy: Do NOT disclose whether the username exists,
            # whether the password was incorrect, or whether the account is disabled.
            is_valid_password = False
            if user:
                is_valid_password = check_password_hash(user['password_hash'], password)

            if not user or not is_valid_password or user.get('is_active') != 1:
                flash("Invalid username or password. Please try again.", "error")
                return render_template('auth/login.html', username=username)

            # Session Fixation Defense: Clear any prior anonymous or stale session data
            session.clear()

            # Establish authenticated session
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']

            # Redirect based on user role (POST/Redirect/GET pattern)
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('player_dashboard'))

        except Exception as e:
            if conn and conn.is_connected():
                conn.close()
            flash("An unexpected error occurred during login. Please try again.", "error")
            return render_template('auth/login.html', username=username)

    return render_template('auth/login.html')


@app.route('/logout', methods=['POST'])
def logout():
    """
    Handles user logout.
    Security requirement: POST only with CSRF token to prevent CSRF logout attacks.
    """
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for('login'))


# =============================================================================
# Protected Dashboard Routes
# =============================================================================
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Admin landing dashboard (accessible only by active admin accounts)."""
    return render_template('admin/dashboard.html')


# =============================================================================
# Phase 6: Player Dashboard & Self-Service Portal
# =============================================================================
@app.route('/player/dashboard')
@player_required
def player_dashboard():
    """
    Player portal dashboard.
    Derives identity exclusively from g.current_user['id'] in the session.
    Retrieves linked player profile, team fixtures, match history,
    individual performance statistics, and relevant tournament overviews.
    Handles unlinked player accounts gracefully.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return render_template('player/dashboard.html', player=None)

    try:
        cursor = conn.cursor(dictionary=True)
        user_id = g.current_user['id']

        # 1. Fetch linked player profile
        cursor.execute(
            """
            SELECT 
                p.id AS player_id,
                p.user_id,
                p.full_name,
                p.date_of_birth,
                p.gender,
                p.jersey_number,
                p.sport_id,
                s.name AS sport_name,
                p.team_id,
                t.name AS team_name,
                p.created_at
            FROM players p
            JOIN sports s ON p.sport_id = s.id
            LEFT JOIN teams t ON p.team_id = t.id
            WHERE p.user_id = %s
            """,
            (user_id,)
        )
        player = cursor.fetchone()

        if not player:
            return render_template('player/dashboard.html', player=None)

        player_id = player['player_id']
        team_id = player['team_id']

        # 2. Fetch player's individual match performance stats from completed matches
        cursor.execute(
            """
            SELECT 
                pms.match_id,
                pms.goals,
                pms.assists,
                pms.points,
                m.match_datetime,
                m.venue,
                tr.id AS tournament_id,
                tr.name AS tournament_name,
                t1.id AS team1_id,
                t1.name AS team1_name,
                t2.id AS team2_id,
                t2.name AS team2_name,
                r.team1_score,
                r.team2_score,
                r.winner_team_id
            FROM player_match_stats pms
            JOIN matches m ON pms.match_id = m.id
            JOIN results r ON r.match_id = m.id
            JOIN tournaments tr ON m.tournament_id = tr.id
            JOIN teams t1 ON m.team1_id = t1.id
            JOIN teams t2 ON m.team2_id = t2.id
            WHERE pms.player_id = %s
              AND m.status = 'completed'
            ORDER BY m.match_datetime DESC
            """,
            (player_id,)
        )
        player_stats = cursor.fetchall()

        career_goals = sum(s['goals'] for s in player_stats)
        career_assists = sum(s['assists'] for s in player_stats)
        career_points = sum(s['points'] for s in player_stats)
        stats_matches_count = len(player_stats)

        # 3. If player is assigned to a team, fetch upcoming fixtures, recent results, and tournaments
        upcoming_matches = []
        recent_results = []
        team_tournaments = []

        if team_id:
            # Upcoming matches for player's team
            cursor.execute(
                """
                SELECT 
                    m.id AS match_id,
                    m.tournament_id,
                    tr.name AS tournament_name,
                    s.name AS sport_name,
                    m.team1_id,
                    t1.name AS team1_name,
                    m.team2_id,
                    t2.name AS team2_name,
                    m.match_datetime,
                    m.venue,
                    m.status
                FROM matches m
                JOIN tournaments tr ON m.tournament_id = tr.id
                JOIN sports s ON tr.sport_id = s.id
                JOIN teams t1 ON m.team1_id = t1.id
                JOIN teams t2 ON m.team2_id = t2.id
                WHERE (m.team1_id = %s OR m.team2_id = %s)
                  AND m.status IN ('scheduled', 'ongoing')
                ORDER BY m.match_datetime ASC
                LIMIT 5
                """,
                (team_id, team_id)
            )
            upcoming_matches = cursor.fetchall()

            # Recent completed matches with results
            cursor.execute(
                """
                SELECT 
                    m.id AS match_id,
                    m.tournament_id,
                    tr.name AS tournament_name,
                    s.name AS sport_name,
                    m.team1_id,
                    t1.name AS team1_name,
                    m.team2_id,
                    t2.name AS team2_name,
                    m.match_datetime,
                    m.venue,
                    m.status,
                    r.team1_score,
                    r.team2_score,
                    r.winner_team_id,
                    tw.name AS winner_team_name,
                    r.notes
                FROM matches m
                JOIN tournaments tr ON m.tournament_id = tr.id
                JOIN sports s ON tr.sport_id = s.id
                JOIN teams t1 ON m.team1_id = t1.id
                JOIN teams t2 ON m.team2_id = t2.id
                JOIN results r ON r.match_id = m.id
                LEFT JOIN teams tw ON r.winner_team_id = tw.id
                WHERE (m.team1_id = %s OR m.team2_id = %s)
                  AND m.status = 'completed'
                ORDER BY m.match_datetime DESC
                LIMIT 10
                """,
                (team_id, team_id)
            )
            recent_results = cursor.fetchall()

            # Tournaments where player's team participates
            cursor.execute(
                """
                SELECT DISTINCT
                    tr.id,
                    tr.name,
                    tr.start_date,
                    tr.end_date,
                    tr.status,
                    tr.description
                FROM tournaments tr
                JOIN matches m ON m.tournament_id = tr.id
                WHERE (m.team1_id = %s OR m.team2_id = %s)
                ORDER BY tr.start_date DESC
                """,
                (team_id, team_id)
            )
            team_tournaments = cursor.fetchall()

        return render_template(
            'player/dashboard.html',
            player=player,
            player_stats=player_stats,
            career_goals=career_goals,
            career_assists=career_assists,
            career_points=career_points,
            stats_matches_count=stats_matches_count,
            upcoming_matches=upcoming_matches,
            recent_results=recent_results,
            team_tournaments=team_tournaments,
        )

    except HTTPException:
        raise
    except Exception:
        flash("Failed to load player portal dashboard.", "error")
        return render_template('player/dashboard.html', player=None)
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/player/profile', methods=['GET', 'POST'])
@player_required
def player_profile():
    """
    Self-service personal details management for players.
    Derives identity exclusively from g.current_user['id'] in the session.
    Allows updating only safe, permitted fields (email, full_name, date_of_birth, gender).
    Strictly forbids role escalation, team reassignment, or account status alterations.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('player_dashboard'))

    try:
        cursor = conn.cursor(dictionary=True)
        user_id = g.current_user['id']

        # Fetch current user record
        cursor.execute("SELECT id, username, email, role, is_active FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        # Fetch linked player profile if exists
        cursor.execute(
            """
            SELECT 
                p.id AS player_id,
                p.user_id,
                p.full_name,
                p.date_of_birth,
                p.gender,
                p.jersey_number,
                p.sport_id,
                s.name AS sport_name,
                p.team_id,
                t.name AS team_name,
                p.created_at
            FROM players p
            JOIN sports s ON p.sport_id = s.id
            LEFT JOIN teams t ON p.team_id = t.id
            WHERE p.user_id = %s
            """,
            (user_id,)
        )
        player = cursor.fetchone()

        if request.method == 'POST':
            email_raw = request.form.get('email', '').strip()
            full_name_raw = request.form.get('full_name', '').strip() if player else None
            dob_raw = request.form.get('date_of_birth', '').strip() if player else None
            gender_raw = request.form.get('gender', '').strip().lower() if player else None

            # 1. Validate email
            if not email_raw:
                flash("Email address is required.", "error")
                return render_template('player/profile.html', user=user, player=player)
            if len(email_raw) > 100 or '@' not in email_raw or '.' not in email_raw:
                flash("Please enter a valid email address.", "error")
                return render_template('player/profile.html', user=user, player=player)

            # Uniqueness check for email
            cursor.execute("SELECT id FROM users WHERE email = %s AND id != %s", (email_raw, user_id))
            if cursor.fetchone():
                flash("This email address is already in use by another account.", "error")
                return render_template('player/profile.html', user=user, player=player)

            # 2. Validate full_name (if player record linked)
            if player:
                if not full_name_raw:
                    flash("Full name is required.", "error")
                    return render_template('player/profile.html', user=user, player=player)
                if len(full_name_raw) > 150:
                    flash("Full name cannot exceed 150 characters.", "error")
                    return render_template('player/profile.html', user=user, player=player)

                # Validate Date of Birth
                dob_val = None
                if dob_raw:
                    try:
                        dob_val = datetime.strptime(dob_raw, '%Y-%m-%d').date()
                        if dob_val > date.today():
                            flash("Date of birth cannot be in the future.", "error")
                            return render_template('player/profile.html', user=user, player=player)
                    except ValueError:
                        flash("Invalid date of birth format. Please use YYYY-MM-DD.", "error")
                        return render_template('player/profile.html', user=user, player=player)

                # Validate Gender
                gender_val = None
                if gender_raw in ('male', 'female', 'other'):
                    gender_val = gender_raw

            # Execute safe updates
            cursor.execute("UPDATE users SET email = %s WHERE id = %s", (email_raw, user_id))
            if player:
                cursor.execute(
                    """
                    UPDATE players 
                    SET full_name = %s, date_of_birth = %s, gender = %s 
                    WHERE user_id = %s
                    """,
                    (full_name_raw, dob_val, gender_val, user_id)
                )

            conn.commit()
            flash("Your profile details have been updated successfully.", "success")
            return redirect(url_for('player_profile'))

        return render_template('player/profile.html', user=user, player=player)

    except HTTPException:
        raise
    except MySQLError as e:
        if conn and conn.is_connected():
            conn.rollback()
        flash("A database error occurred while updating your profile.", "error")
        return redirect(url_for('player_profile'))
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('player_profile'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()



# =============================================================================
# Phase 5.1: Sports Management Routes (Admin Only)
# =============================================================================
@app.route('/admin/sports')
@admin_required
def sports_list():
    """
    Renders the sports management overview page.
    Retrieves all sports along with counts of associated teams, players, and tournaments.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return render_template('admin/sports.html', sports=[])

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT 
                s.id, 
                s.name, 
                s.description, 
                s.created_at,
                (SELECT COUNT(*) FROM teams t WHERE t.sport_id = s.id) AS teams_count,
                (SELECT COUNT(*) FROM players p WHERE p.sport_id = s.id) AS players_count,
                (SELECT COUNT(*) FROM tournaments tm WHERE tm.sport_id = s.id) AS tournaments_count
            FROM sports s
            ORDER BY s.name ASC
            """
        )
        sports = cursor.fetchall()
        return render_template('admin/sports.html', sports=sports)
    except Exception as e:
        flash("Failed to retrieve sports records. Please try again.", "error")
        return render_template('admin/sports.html', sports=[])
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/sports/new', methods=['GET', 'POST'])
@admin_required
def sports_create():
    """
    Handles creating a new sport.
    GET: Renders blank sport creation form.
    POST: Validates input, prevents duplicates, executes parameterized insert.
    """
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        # Validation rules
        if not name:
            flash("Sport name is required and cannot be blank.", "error")
            return render_template('admin/sport_form.html', action='add', name=name, description=description)

        if len(name) > 100:
            flash("Sport name cannot exceed 100 characters.", "error")
            return render_template('admin/sport_form.html', action='add', name=name, description=description)

        if len(description) > 1000:
            flash("Description cannot exceed 1000 characters.", "error")
            return render_template('admin/sport_form.html', action='add', name=name, description=description)

        conn = get_db_connection()
        if conn is None:
            flash("Database service unavailable. Please try again later.", "error")
            return render_template('admin/sport_form.html', action='add', name=name, description=description)

        try:
            cursor = conn.cursor(dictionary=True)

            # Case-insensitive duplicate check
            cursor.execute("SELECT id FROM sports WHERE LOWER(TRIM(name)) = LOWER(%s)", (name,))
            if cursor.fetchone():
                flash(f"A sport with the name '{name}' already exists.", "error")
                return render_template('admin/sport_form.html', action='add', name=name, description=description)

            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                (name, description if description else None)
            )
            conn.commit()
            flash(f"Sport '{name}' registered successfully.", "success")
            return redirect(url_for('sports_list'))

        except MySQLError as e:
            if conn and conn.is_connected():
                conn.rollback()
            if e.errno == 1062:  # Duplicate entry
                flash(f"A sport with the name '{name}' already exists.", "error")
            else:
                flash("A database error occurred while creating the sport.", "error")
            return render_template('admin/sport_form.html', action='add', name=name, description=description)
        except Exception:
            if conn and conn.is_connected():
                conn.rollback()
            flash("An unexpected error occurred. Please try again.", "error")
            return render_template('admin/sport_form.html', action='add', name=name, description=description)
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    return render_template('admin/sport_form.html', action='add')


@app.route('/admin/sports/<int:sport_id>/edit', methods=['GET', 'POST'])
@admin_required
def sports_edit(sport_id):
    """
    Handles editing an existing sport.
    GET: Renders form populated with existing sport details.
    POST: Validates input, prevents duplicate names, updates record.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('sports_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name, description FROM sports WHERE id = %s", (sport_id,))
        sport = cursor.fetchone()

        if not sport:
            cursor.close()
            conn.close()
            abort(404)

        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()

            # Validation rules
            if not name:
                flash("Sport name is required and cannot be blank.", "error")
                return render_template('admin/sport_form.html', action='edit', sport=sport, name=name, description=description)

            if len(name) > 100:
                flash("Sport name cannot exceed 100 characters.", "error")
                return render_template('admin/sport_form.html', action='edit', sport=sport, name=name, description=description)

            if len(description) > 1000:
                flash("Description cannot exceed 1000 characters.", "error")
                return render_template('admin/sport_form.html', action='edit', sport=sport, name=name, description=description)

            # Case-insensitive duplicate check excluding current sport
            cursor.execute(
                "SELECT id FROM sports WHERE LOWER(TRIM(name)) = LOWER(%s) AND id <> %s",
                (name, sport_id)
            )
            if cursor.fetchone():
                flash(f"Another sport with the name '{name}' already exists.", "error")
                return render_template('admin/sport_form.html', action='edit', sport=sport, name=name, description=description)

            cursor.execute(
                "UPDATE sports SET name = %s, description = %s WHERE id = %s",
                (name, description if description else None, sport_id)
            )
            conn.commit()
            flash(f"Sport '{name}' updated successfully.", "success")
            return redirect(url_for('sports_list'))

        return render_template('admin/sport_form.html', action='edit', sport=sport)

    except HTTPException:
        raise
    except MySQLError as e:
        if conn and conn.is_connected():
            conn.rollback()
        if e.errno == 1062:
            flash(f"Another sport with the name '{name}' already exists.", "error")
        else:
            flash("A database error occurred while updating the sport.", "error")
        return render_template('admin/sport_form.html', action='edit', sport=sport, name=name, description=description)
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('sports_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/sports/<int:sport_id>/delete', methods=['POST'])
@admin_required
def sports_delete(sport_id):
    """
    Safely deletes a sport if no dependent records (teams, players, tournaments) exist.
    Deletion is restricted to POST with CSRF protection.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('sports_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM sports WHERE id = %s", (sport_id,))
        sport = cursor.fetchone()

        if not sport:
            cursor.close()
            conn.close()
            abort(404)

        # Check for dependent records (3 placeholders: teams, players, tournaments)
        cursor.execute(
            """
            SELECT 
                (SELECT COUNT(*) FROM teams WHERE sport_id = %s) AS teams_count,
                (SELECT COUNT(*) FROM players WHERE sport_id = %s) AS players_count,
                (SELECT COUNT(*) FROM tournaments WHERE sport_id = %s) AS tournaments_count
            """,
            (sport_id, sport_id, sport_id)
        )
        counts = cursor.fetchone()
        teams_count = counts['teams_count']
        players_count = counts['players_count']
        tournaments_count = counts['tournaments_count']

        if teams_count > 0 or players_count > 0 or tournaments_count > 0:
            deps = []
            if teams_count:
                deps.append(f"{teams_count} team(s)")
            if players_count:
                deps.append(f"{players_count} player(s)")
            if tournaments_count:
                deps.append(f"{tournaments_count} tournament(s)")
            dep_msg = ", ".join(deps)
            flash(
                f"Cannot delete sport '{sport['name']}': It is currently referenced by {dep_msg}. "
                "These dependent records must be removed or reallocated first.",
                "warning"
            )
            return redirect(url_for('sports_list'))

        # Safe to delete
        cursor.execute("DELETE FROM sports WHERE id = %s", (sport_id,))
        conn.commit()
        flash(f"Sport '{sport['name']}' deleted successfully.", "success")
        return redirect(url_for('sports_list'))

    except HTTPException:
        raise
    except MySQLError as e:
        if conn and conn.is_connected():
            conn.rollback()
        if e.errno == 1451:  # Foreign key constraint failure
            flash(
                f"Cannot delete sport '{sport['name']}': Dependent records exist in the database.",
                "warning"
            )
        else:
            flash("A database error occurred while deleting the sport.", "error")
        return redirect(url_for('sports_list'))
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('sports_list'))

    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# =============================================================================
# Phase 5.2: Teams Management Routes (Admin Only)
# =============================================================================
@app.route('/admin/teams')
@admin_required
def teams_list():
    """
    Renders the teams management overview page.
    Retrieves all teams along with their associated sport and active player count.
    Also retrieves the list of sports for dropdown filtering.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return render_template('admin/teams.html', teams=[], sports=[])

    try:
        cursor = conn.cursor(dictionary=True)
        # Fetch all sports for filter dropdown
        cursor.execute("SELECT id, name FROM sports ORDER BY name ASC")
        sports = cursor.fetchall()

        # Fetch all teams with sport name and player count
        cursor.execute(
            """
            SELECT 
                t.id, 
                t.name, 
                t.sport_id, 
                s.name AS sport_name, 
                t.created_at,
                (SELECT COUNT(*) FROM players p WHERE p.team_id = t.id) AS players_count
            FROM teams t
            JOIN sports s ON t.sport_id = s.id
            ORDER BY t.name ASC
            """
        )
        teams = cursor.fetchall()
        return render_template('admin/teams.html', teams=teams, sports=sports)
    except Exception:
        flash("Failed to retrieve teams records. Please try again.", "error")
        return render_template('admin/teams.html', teams=[], sports=[])
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/teams/new', methods=['GET', 'POST'])
@admin_required
def teams_create():
    """
    Handles creating a new team.
    GET: Renders blank team creation form with active sports.
    POST: Validates input, prevents duplicate (name, sport_id), executes parameterized insert.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('teams_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM sports ORDER BY name ASC")
        sports = cursor.fetchall()

        if not sports:
            flash("No sports are currently registered. You must register at least one sport before creating teams.", "warning")
            return redirect(url_for('sports_create'))

        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            sport_id_raw = request.form.get('sport_id', '').strip()

            # Name validation
            if not name:
                flash("Team name is required and cannot be blank.", "error")
                return render_template('admin/team_form.html', action='add', sports=sports, name=name, selected_sport_id=sport_id_raw)

            if len(name) > 100:
                flash("Team name cannot exceed 100 characters.", "error")
                return render_template('admin/team_form.html', action='add', sports=sports, name=name, selected_sport_id=sport_id_raw)

            # Sport validation
            if not sport_id_raw:
                flash("Please select a valid sport category.", "error")
                return render_template('admin/team_form.html', action='add', sports=sports, name=name, selected_sport_id=sport_id_raw)

            try:
                sport_id = int(sport_id_raw)
            except ValueError:
                flash("Invalid sport category selected.", "error")
                return render_template('admin/team_form.html', action='add', sports=sports, name=name, selected_sport_id=sport_id_raw)

            # Verify that the sport actually exists in DB
            cursor.execute("SELECT id, name FROM sports WHERE id = %s", (sport_id,))
            target_sport = cursor.fetchone()
            if not target_sport:
                flash("The selected sport does not exist in the system.", "error")
                return render_template('admin/team_form.html', action='add', sports=sports, name=name, selected_sport_id=sport_id_raw)

            # Duplicate check within the same sport: (LOWER(TRIM(name)), sport_id)
            cursor.execute(
                "SELECT id FROM teams WHERE LOWER(TRIM(name)) = LOWER(%s) AND sport_id = %s",
                (name, sport_id)
            )
            if cursor.fetchone():
                flash(f"A team named '{name}' already exists in {target_sport['name']}.", "error")
                return render_template('admin/team_form.html', action='add', sports=sports, name=name, selected_sport_id=sport_id_raw)

            # Execute insert
            creator_id = g.current_user['id'] if g.current_user else None
            cursor.execute(
                "INSERT INTO teams (name, sport_id, created_by) VALUES (%s, %s, %s)",
                (name, sport_id, creator_id)
            )
            conn.commit()
            flash(f"Team '{name}' registered successfully under {target_sport['name']}.", "success")
            return redirect(url_for('teams_list'))

        return render_template('admin/team_form.html', action='add', sports=sports)

    except MySQLError as e:
        if conn and conn.is_connected():
            conn.rollback()
        if e.errno == 1062:  # Duplicate entry
            flash("A team with this name already exists in the selected sport.", "error")
        else:
            flash("A database error occurred while creating the team.", "error")
        return render_template('admin/team_form.html', action='add', sports=sports, name=request.form.get('name', '').strip(), selected_sport_id=request.form.get('sport_id', '').strip())
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('teams_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/teams/<int:team_id>/edit', methods=['GET', 'POST'])
@admin_required
def teams_edit(team_id):
    """
    Handles editing an existing team.
    GET: Renders form populated with current team values.
    POST: Validates input, prevents duplicate names within sport, updates record.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('teams_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name, sport_id, created_at FROM teams WHERE id = %s", (team_id,))
        team = cursor.fetchone()

        if not team:
            cursor.close()
            conn.close()
            abort(404)

        cursor.execute("SELECT id, name FROM sports ORDER BY name ASC")
        sports = cursor.fetchall()

        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            sport_id_raw = request.form.get('sport_id', '').strip()

            # Name validation
            if not name:
                flash("Team name is required and cannot be blank.", "error")
                return render_template('admin/team_form.html', action='edit', team=team, sports=sports, name=name, selected_sport_id=sport_id_raw)

            if len(name) > 100:
                flash("Team name cannot exceed 100 characters.", "error")
                return render_template('admin/team_form.html', action='edit', team=team, sports=sports, name=name, selected_sport_id=sport_id_raw)

            # Sport validation
            if not sport_id_raw:
                flash("Please select a valid sport category.", "error")
                return render_template('admin/team_form.html', action='edit', team=team, sports=sports, name=name, selected_sport_id=sport_id_raw)

            try:
                new_sport_id = int(sport_id_raw)
            except ValueError:
                flash("Invalid sport category selected.", "error")
                return render_template('admin/team_form.html', action='edit', team=team, sports=sports, name=name, selected_sport_id=sport_id_raw)

            # Verify target sport exists
            cursor.execute("SELECT id, name FROM sports WHERE id = %s", (new_sport_id,))
            target_sport = cursor.fetchone()
            if not target_sport:
                flash("The selected sport does not exist in the system.", "error")
                return render_template('admin/team_form.html', action='edit', team=team, sports=sports, name=name, selected_sport_id=sport_id_raw)

            # Check if sport is being changed when dependent records exist
            if new_sport_id != team['sport_id']:
                cursor.execute(
                    """
                    SELECT 
                        (SELECT COUNT(*) FROM players WHERE team_id = %s) AS players_count,
                        (SELECT COUNT(*) FROM matches WHERE team1_id = %s OR team2_id = %s) AS matches_count
                    """,
                    (team_id, team_id, team_id)
                )
                dep_counts = cursor.fetchone()
                p_count = dep_counts['players_count']
                m_count = dep_counts['matches_count']

                if p_count > 0 or m_count > 0:
                    deps = []
                    if p_count:
                        deps.append(f"{p_count} assigned player(s)")
                    if m_count:
                        deps.append(f"{m_count} scheduled match(es)")
                    dep_str = " and ".join(deps)
                    flash(
                        f"Cannot change sport category for '{team['name']}': This team has {dep_str} "
                        "tied to its current sport. Reassign or remove these records before changing the sport affiliation.",
                        "warning"
                    )
                    return render_template('admin/team_form.html', action='edit', team=team, sports=sports, name=name, selected_sport_id=sport_id_raw)

            # Duplicate check within new_sport_id excluding this team
            cursor.execute(
                "SELECT id FROM teams WHERE LOWER(TRIM(name)) = LOWER(%s) AND sport_id = %s AND id <> %s",
                (name, new_sport_id, team_id)
            )
            if cursor.fetchone():
                flash(f"Another team named '{name}' already exists in {target_sport['name']}.", "error")
                return render_template('admin/team_form.html', action='edit', team=team, sports=sports, name=name, selected_sport_id=sport_id_raw)

            # Execute update
            cursor.execute(
                "UPDATE teams SET name = %s, sport_id = %s WHERE id = %s",
                (name, new_sport_id, team_id)
            )
            conn.commit()
            flash(f"Team '{name}' updated successfully.", "success")
            return redirect(url_for('teams_list'))

        return render_template('admin/team_form.html', action='edit', team=team, sports=sports)

    except HTTPException:
        raise
    except MySQLError as e:
        if conn and conn.is_connected():
            conn.rollback()
        if e.errno == 1062:
            flash("Another team with this name already exists in the selected sport.", "error")
        else:
            flash("A database error occurred while updating the team.", "error")
        return render_template('admin/team_form.html', action='edit', team=team, sports=sports, name=request.form.get('name', '').strip(), selected_sport_id=request.form.get('sport_id', '').strip())
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('teams_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/teams/<int:team_id>/delete', methods=['POST'])
@admin_required
def teams_delete(team_id):
    """
    Safely deletes a team if no dependent records (players, matches, results) exist.
    Restricted to POST with CSRF protection.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('teams_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM teams WHERE id = %s", (team_id,))
        team = cursor.fetchone()

        if not team:
            cursor.close()
            conn.close()
            abort(404)

        # Check for dependent records:
        # 1. Players assigned to this team
        # 2. Matches where this team is team1 or team2
        # 3. Results where this team is recorded as winner
        cursor.execute(
            """
            SELECT 
                (SELECT COUNT(*) FROM players WHERE team_id = %s) AS players_count,
                (SELECT COUNT(*) FROM matches WHERE team1_id = %s OR team2_id = %s) AS matches_count,
                (SELECT COUNT(*) FROM results WHERE winner_team_id = %s) AS results_count
            """,
            (team_id, team_id, team_id, team_id)
        )
        counts = cursor.fetchone()
        players_count = counts['players_count']
        matches_count = counts['matches_count']
        results_count = counts['results_count']

        if players_count > 0 or matches_count > 0 or results_count > 0:
            deps = []
            if players_count:
                deps.append(f"{players_count} assigned player(s)")
            if matches_count:
                deps.append(f"{matches_count} scheduled match(es)")
            if results_count:
                deps.append(f"{results_count} match result(s)")
            dep_msg = ", ".join(deps)
            flash(
                f"Cannot delete team '{team['name']}': It is currently referenced by {dep_msg}. "
                "These records must be reallocated, cancelled, or resolved before this team can be removed.",
                "warning"
            )
            return redirect(url_for('teams_list'))

        # Safe to delete
        cursor.execute("DELETE FROM teams WHERE id = %s", (team_id,))
        conn.commit()
        flash(f"Team '{team['name']}' deleted successfully.", "success")
        return redirect(url_for('teams_list'))

    except HTTPException:
        raise
    except MySQLError as e:
        if conn and conn.is_connected():
            conn.rollback()
        if e.errno == 1451:
            flash(
                f"Cannot delete team '{team['name']}': Dependent records exist in the database.",
                "warning"
            )
        else:
            flash("A database error occurred while deleting the team.", "error")
        return redirect(url_for('teams_list'))
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('teams_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# =============================================================================
# Phase 5.3: Player Management Routes (Admin Only)
# =============================================================================
@app.route('/admin/players')
@admin_required
def players_list():
    """
    Renders the player management overview page.
    Retrieves all players with joined sport, team, and linked user info.
    Also retrieves all sports and teams for dropdown filtering.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return render_template('admin/players.html', players=[], sports=[], teams=[])

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM sports ORDER BY name ASC")
        sports = cursor.fetchall()

        cursor.execute(
            """
            SELECT t.id, t.name, t.sport_id, s.name AS sport_name
            FROM teams t
            JOIN sports s ON t.sport_id = s.id
            ORDER BY t.name ASC
            """
        )
        teams = cursor.fetchall()

        cursor.execute(
            """
            SELECT 
                p.id, 
                p.full_name, 
                p.date_of_birth, 
                p.gender, 
                p.sport_id, 
                s.name AS sport_name, 
                p.team_id, 
                t.name AS team_name, 
                p.jersey_number, 
                p.user_id, 
                u.username,
                p.created_at
            FROM players p
            JOIN sports s ON p.sport_id = s.id
            LEFT JOIN teams t ON p.team_id = t.id
            LEFT JOIN users u ON p.user_id = u.id
            ORDER BY p.full_name ASC
            """
        )
        players = cursor.fetchall()
        return render_template('admin/players.html', players=players, sports=sports, teams=teams)
    except Exception:
        flash("Failed to retrieve player records. Please try again.", "error")
        return render_template('admin/players.html', players=[], sports=[], teams=[])
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/players/new', methods=['GET', 'POST'])
@admin_required
def players_create():
    """
    Handles creating a new player.
    GET: Renders blank player registration form.
    POST: Validates inputs, verifies sport/team compatibility, executes insert.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('players_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM sports ORDER BY name ASC")
        sports = cursor.fetchall()

        if not sports:
            flash("No sports are currently registered. You must register at least one sport before adding players.", "warning")
            return redirect(url_for('sports_create'))

        cursor.execute(
            """
            SELECT t.id, t.name, t.sport_id, s.name AS sport_name
            FROM teams t
            JOIN sports s ON t.sport_id = s.id
            ORDER BY t.name ASC
            """
        )
        teams = cursor.fetchall()

        cursor.execute(
            """
            SELECT id, username, email FROM users 
            WHERE role = 'player' AND id NOT IN (SELECT user_id FROM players WHERE user_id IS NOT NULL)
            ORDER BY username ASC
            """
        )
        available_users = cursor.fetchall()

        max_date = date.today().isoformat()

        if request.method == 'POST':
            full_name = request.form.get('full_name', '').strip()
            sport_id_raw = request.form.get('sport_id', '').strip()
            team_id_raw = request.form.get('team_id', '').strip()
            date_of_birth_raw = request.form.get('date_of_birth', '').strip()
            gender_raw = request.form.get('gender', '').strip()
            jersey_number_raw = request.form.get('jersey_number', '').strip()
            user_id_raw = request.form.get('user_id', '').strip()

            def render_form_error(message):
                flash(message, "error")
                return render_template(
                    'admin/player_form.html',
                    action='add',
                    sports=sports,
                    teams=teams,
                    available_users=available_users,
                    max_date=max_date,
                    full_name=full_name,
                    selected_sport_id=sport_id_raw,
                    selected_team_id=team_id_raw,
                    date_of_birth=date_of_birth_raw,
                    gender=gender_raw,
                    jersey_number=jersey_number_raw,
                    selected_user_id=user_id_raw
                )

            # 1. Full name validation
            if not full_name:
                return render_form_error("Full name is required and cannot be blank.")
            if len(full_name) > 150:
                return render_form_error("Full name cannot exceed 150 characters.")

            # 2. Sport validation
            if not sport_id_raw:
                return render_form_error("Please select a valid sport discipline.")
            try:
                sport_id = int(sport_id_raw)
            except ValueError:
                return render_form_error("Invalid sport discipline selected.")

            cursor.execute("SELECT id, name FROM sports WHERE id = %s", (sport_id,))
            target_sport = cursor.fetchone()
            if not target_sport:
                return render_form_error("The selected sport discipline does not exist in the system.")

            # 3. Team validation (optional)
            team_id = None
            if team_id_raw:
                try:
                    team_id = int(team_id_raw)
                except ValueError:
                    return render_form_error("Invalid team selected.")

                cursor.execute("SELECT id, name, sport_id FROM teams WHERE id = %s", (team_id,))
                target_team = cursor.fetchone()
                if not target_team:
                    return render_form_error("The selected team does not exist in the system.")

                # Sport & Team compatibility enforcement
                if target_team['sport_id'] != sport_id:
                    return render_form_error(
                        f"The selected team '{target_team['name']}' does not compete in {target_sport['name']}."
                    )

            # 4. Date of birth validation (optional)
            date_of_birth = None
            if date_of_birth_raw:
                try:
                    dob = datetime.strptime(date_of_birth_raw, '%Y-%m-%d').date()
                except ValueError:
                    return render_form_error("Invalid date of birth format. Please use YYYY-MM-DD.")

                if dob > date.today():
                    return render_form_error("Date of birth cannot be in the future.")
                if dob < date(1900, 1, 1):
                    return render_form_error("Invalid date of birth.")
                date_of_birth = dob

            # 5. Gender validation (optional)
            gender = None
            if gender_raw:
                if gender_raw not in ('male', 'female', 'other'):
                    return render_form_error("Gender must be 'male', 'female', or 'other'.")
                gender = gender_raw

            # 6. Jersey number validation (optional)
            jersey_number = None
            if jersey_number_raw:
                try:
                    j_num = int(jersey_number_raw)
                except ValueError:
                    return render_form_error("Jersey number must be a valid integer.")

                if j_num < 0 or j_num > 255:
                    return render_form_error("Jersey number must be between 0 and 255.")
                jersey_number = j_num

            # 7. User account linking (optional)
            user_id = None
            if user_id_raw:
                try:
                    u_id = int(user_id_raw)
                except ValueError:
                    return render_form_error("Invalid user account selected.")

                cursor.execute("SELECT id, username, role FROM users WHERE id = %s", (u_id,))
                target_user = cursor.fetchone()
                if not target_user or target_user['role'] != 'player':
                    return render_form_error("Selected account is not a valid player user account.")

                cursor.execute("SELECT id FROM players WHERE user_id = %s", (u_id,))
                if cursor.fetchone():
                    return render_form_error("That user account is already linked to another player.")
                user_id = u_id

            # Insert player
            cursor.execute(
                """
                INSERT INTO players (full_name, date_of_birth, gender, sport_id, team_id, jersey_number, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (full_name, date_of_birth, gender, sport_id, team_id, jersey_number, user_id)
            )
            conn.commit()
            flash(f"Player '{full_name}' registered successfully.", "success")
            return redirect(url_for('players_list'))

        return render_template(
            'admin/player_form.html',
            action='add',
            sports=sports,
            teams=teams,
            available_users=available_users,
            max_date=max_date
        )

    except MySQLError as e:
        if conn and conn.is_connected():
            conn.rollback()
        if e.errno == 1062:
            flash("A player is already linked to that user account.", "error")
        else:
            flash("A database error occurred while registering the player.", "error")
        return redirect(url_for('players_list'))
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('players_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/players/<int:player_id>/edit', methods=['GET', 'POST'])
@admin_required
def players_edit(player_id):
    """
    Handles editing an existing player.
    GET: Renders form populated with current player values.
    POST: Validates inputs, verifies sport/team compatibility, updates record.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('players_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM players WHERE id = %s", (player_id,))
        player = cursor.fetchone()

        if not player:
            cursor.close()
            conn.close()
            abort(404)

        cursor.execute("SELECT id, name FROM sports ORDER BY name ASC")
        sports = cursor.fetchall()

        cursor.execute(
            """
            SELECT t.id, t.name, t.sport_id, s.name AS sport_name
            FROM teams t
            JOIN sports s ON t.sport_id = s.id
            ORDER BY t.name ASC
            """
        )
        teams = cursor.fetchall()

        # Available users: unlinked player users OR the user currently linked to this player
        cursor.execute(
            """
            SELECT id, username, email FROM users 
            WHERE role = 'player' AND (id NOT IN (SELECT user_id FROM players WHERE user_id IS NOT NULL) OR id = %s)
            ORDER BY username ASC
            """,
            (player['user_id'] or 0,)
        )
        available_users = cursor.fetchall()

        max_date = date.today().isoformat()

        if request.method == 'POST':
            full_name = request.form.get('full_name', '').strip()
            sport_id_raw = request.form.get('sport_id', '').strip()
            team_id_raw = request.form.get('team_id', '').strip()
            date_of_birth_raw = request.form.get('date_of_birth', '').strip()
            gender_raw = request.form.get('gender', '').strip()
            jersey_number_raw = request.form.get('jersey_number', '').strip()
            user_id_raw = request.form.get('user_id', '').strip()

            def render_form_error(message):
                flash(message, "error")
                return render_template(
                    'admin/player_form.html',
                    action='edit',
                    player=player,
                    sports=sports,
                    teams=teams,
                    available_users=available_users,
                    max_date=max_date,
                    full_name=full_name,
                    selected_sport_id=sport_id_raw,
                    selected_team_id=team_id_raw,
                    date_of_birth=date_of_birth_raw,
                    gender=gender_raw,
                    jersey_number=jersey_number_raw,
                    selected_user_id=user_id_raw
                )

            # 1. Full name validation
            if not full_name:
                return render_form_error("Full name is required and cannot be blank.")
            if len(full_name) > 150:
                return render_form_error("Full name cannot exceed 150 characters.")

            # 2. Sport validation
            if not sport_id_raw:
                return render_form_error("Please select a valid sport discipline.")
            try:
                sport_id = int(sport_id_raw)
            except ValueError:
                return render_form_error("Invalid sport discipline selected.")

            cursor.execute("SELECT id, name FROM sports WHERE id = %s", (sport_id,))
            target_sport = cursor.fetchone()
            if not target_sport:
                return render_form_error("The selected sport discipline does not exist in the system.")

            # 3. Team validation (optional)
            team_id = None
            if team_id_raw:
                try:
                    team_id = int(team_id_raw)
                except ValueError:
                    return render_form_error("Invalid team selected.")

                cursor.execute("SELECT id, name, sport_id FROM teams WHERE id = %s", (team_id,))
                target_team = cursor.fetchone()
                if not target_team:
                    return render_form_error("The selected team does not exist in the system.")

                # Sport & Team compatibility enforcement
                if target_team['sport_id'] != sport_id:
                    return render_form_error(
                        f"The selected team '{target_team['name']}' does not compete in {target_sport['name']}."
                    )

            # 4. Date of birth validation (optional)
            date_of_birth = None
            if date_of_birth_raw:
                try:
                    dob = datetime.strptime(date_of_birth_raw, '%Y-%m-%d').date()
                except ValueError:
                    return render_form_error("Invalid date of birth format. Please use YYYY-MM-DD.")

                if dob > date.today():
                    return render_form_error("Date of birth cannot be in the future.")
                if dob < date(1900, 1, 1):
                    return render_form_error("Invalid date of birth.")
                date_of_birth = dob

            # 5. Gender validation (optional)
            gender = None
            if gender_raw:
                if gender_raw not in ('male', 'female', 'other'):
                    return render_form_error("Gender must be 'male', 'female', or 'other'.")
                gender = gender_raw

            # 6. Jersey number validation (optional)
            jersey_number = None
            if jersey_number_raw:
                try:
                    j_num = int(jersey_number_raw)
                except ValueError:
                    return render_form_error("Jersey number must be a valid integer.")

                if j_num < 0 or j_num > 255:
                    return render_form_error("Jersey number must be between 0 and 255.")
                jersey_number = j_num

            # 7. User account linking (optional)
            user_id = None
            if user_id_raw:
                try:
                    u_id = int(user_id_raw)
                except ValueError:
                    return render_form_error("Invalid user account selected.")

                cursor.execute("SELECT id, username, role FROM users WHERE id = %s", (u_id,))
                target_user = cursor.fetchone()
                if not target_user or target_user['role'] != 'player':
                    return render_form_error("Selected account is not a valid player user account.")

                cursor.execute("SELECT id FROM players WHERE user_id = %s AND id <> %s", (u_id, player_id))
                if cursor.fetchone():
                    return render_form_error("That user account is already linked to another player.")
                user_id = u_id

            # Execute update
            cursor.execute(
                """
                UPDATE players 
                SET full_name = %s, date_of_birth = %s, gender = %s, sport_id = %s, team_id = %s, jersey_number = %s, user_id = %s
                WHERE id = %s
                """,
                (full_name, date_of_birth, gender, sport_id, team_id, jersey_number, user_id, player_id)
            )
            conn.commit()
            flash(f"Player '{full_name}' updated successfully.", "success")
            return redirect(url_for('players_list'))

        return render_template(
            'admin/player_form.html',
            action='edit',
            player=player,
            sports=sports,
            teams=teams,
            available_users=available_users,
            max_date=max_date
        )

    except HTTPException:
        raise
    except MySQLError as e:
        if conn and conn.is_connected():
            conn.rollback()
        if e.errno == 1062:
            flash("A player is already linked to that user account.", "error")
        else:
            flash("A database error occurred while updating the player.", "error")
        return redirect(url_for('players_list'))
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('players_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/players/<int:player_id>/delete', methods=['POST'])
@admin_required
def players_delete(player_id):
    """
    Safely deletes a player if no dependent records (e.g. match statistics) exist.
    Deletion is restricted to POST with CSRF protection.
    Linked user account is NOT deleted.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('players_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, full_name, user_id FROM players WHERE id = %s", (player_id,))
        player = cursor.fetchone()

        if not player:
            cursor.close()
            conn.close()
            abort(404)

        # Check for dependent match performance statistics
        cursor.execute("SELECT COUNT(*) AS stats_count FROM player_match_stats WHERE player_id = %s", (player_id,))
        stats_count = cursor.fetchone()['stats_count']

        if stats_count > 0:
            flash(
                f"Cannot delete player '{player['full_name']}': This player has {stats_count} recorded match "
                "performance statistic(s). Removing this player would delete their match history. "
                "Match statistics must be resolved first.",
                "warning"
            )
            return redirect(url_for('players_list'))

        # Safe to delete
        cursor.execute("DELETE FROM players WHERE id = %s", (player_id,))
        conn.commit()
        flash(f"Player '{player['full_name']}' deleted successfully.", "success")
        return redirect(url_for('players_list'))

    except HTTPException:
        raise
    except MySQLError as e:
        if conn and conn.is_connected():
            conn.rollback()
        flash("A database error occurred while deleting the player.", "error")
        return redirect(url_for('players_list'))
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('players_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# =============================================================================
# Phase 5.4: Tournament Management Routes (Admin Only)
# =============================================================================
@app.route('/admin/tournaments')
@admin_required
def tournaments_list():
    """
    Renders the tournament management overview page.
    Retrieves all tournaments with joined sport and associated match count.
    Also retrieves sports for dropdown filtering.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return render_template('admin/tournaments.html', tournaments=[], sports=[])

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM sports ORDER BY name ASC")
        sports = cursor.fetchall()

        cursor.execute(
            """
            SELECT 
                t.id, 
                t.name, 
                t.sport_id, 
                s.name AS sport_name, 
                t.start_date, 
                t.end_date, 
                t.status, 
                t.description, 
                t.created_at,
                (SELECT COUNT(*) FROM matches WHERE tournament_id = t.id) AS match_count
            FROM tournaments t
            JOIN sports s ON t.sport_id = s.id
            ORDER BY t.start_date DESC, t.id DESC
            """
        )
        tournaments = cursor.fetchall()
        return render_template('admin/tournaments.html', tournaments=tournaments, sports=sports)
    except Exception:
        flash("Failed to retrieve tournament records. Please try again.", "error")
        return render_template('admin/tournaments.html', tournaments=[], sports=[])
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/tournaments/new', methods=['GET', 'POST'])
@admin_required
def tournaments_create():
    """
    Handles creating a new tournament.
    GET: Renders blank tournament creation form.
    POST: Validates inputs, verifies dates and sport, executes insert.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('tournaments_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM sports ORDER BY name ASC")
        sports = cursor.fetchall()

        if not sports:
            flash("No sports are currently registered. You must register at least one sport before creating tournaments.", "warning")
            return redirect(url_for('sports_create'))

        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            sport_id_raw = request.form.get('sport_id', '').strip()
            start_date_raw = request.form.get('start_date', '').strip()
            end_date_raw = request.form.get('end_date', '').strip()
            status = request.form.get('status', 'upcoming').strip().lower()
            description = request.form.get('description', '').strip()

            def render_form_error(message):
                flash(message, "error")
                return render_template(
                    'admin/tournament_form.html',
                    action='add',
                    sports=sports,
                    name=name,
                    selected_sport_id=sport_id_raw,
                    start_date=start_date_raw,
                    end_date=end_date_raw,
                    status=status,
                    description=description
                )

            # 1. Tournament Name validation
            if not name:
                return render_form_error("Tournament name is required and cannot be blank.")
            if len(name) > 150:
                return render_form_error("Tournament name cannot exceed 150 characters.")

            # 2. Sport validation
            if not sport_id_raw:
                return render_form_error("Please select a valid sport category.")
            try:
                sport_id = int(sport_id_raw)
            except ValueError:
                return render_form_error("Invalid sport category selected.")

            cursor.execute("SELECT id, name FROM sports WHERE id = %s", (sport_id,))
            target_sport = cursor.fetchone()
            if not target_sport:
                return render_form_error("The selected sport category does not exist in the system.")

            # 3. Start date & End date validation
            if not start_date_raw:
                return render_form_error("Start date is required.")
            try:
                start_date = datetime.strptime(start_date_raw, '%Y-%m-%d').date()
            except ValueError:
                return render_form_error("Invalid start date format. Please use YYYY-MM-DD.")

            if not end_date_raw:
                return render_form_error("End date is required.")
            try:
                end_date = datetime.strptime(end_date_raw, '%Y-%m-%d').date()
            except ValueError:
                return render_form_error("Invalid end date format. Please use YYYY-MM-DD.")

            if end_date < start_date:
                return render_form_error("End date cannot be earlier than start date.")

            # 4. Status validation
            allowed_statuses = ('upcoming', 'ongoing', 'completed', 'cancelled')
            if status not in allowed_statuses:
                return render_form_error(f"Status must be one of: {', '.join(allowed_statuses)}.")

            # 5. Description formatting
            desc_val = description if description else None

            # Execute insert
            cursor.execute(
                """
                INSERT INTO tournaments (name, sport_id, start_date, end_date, status, description)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (name, sport_id, start_date, end_date, status, desc_val)
            )
            conn.commit()
            flash(f"Tournament '{name}' created successfully.", "success")
            return redirect(url_for('tournaments_list'))

        return render_template('admin/tournament_form.html', action='add', sports=sports)

    except MySQLError as e:
        if conn and conn.is_connected():
            conn.rollback()
        flash("A database error occurred while creating the tournament.", "error")
        return redirect(url_for('tournaments_list'))
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('tournaments_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/tournaments/<int:tournament_id>/edit', methods=['GET', 'POST'])
@admin_required
def tournaments_edit(tournament_id):
    """
    Handles editing an existing tournament.
    GET: Renders form populated with current tournament values.
    POST: Validates inputs, dates, and sport, executes update.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('tournaments_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM tournaments WHERE id = %s", (tournament_id,))
        tournament = cursor.fetchone()

        if not tournament:
            cursor.close()
            conn.close()
            abort(404)

        cursor.execute("SELECT id, name FROM sports ORDER BY name ASC")
        sports = cursor.fetchall()

        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            sport_id_raw = request.form.get('sport_id', '').strip()
            start_date_raw = request.form.get('start_date', '').strip()
            end_date_raw = request.form.get('end_date', '').strip()
            status = request.form.get('status', 'upcoming').strip().lower()
            description = request.form.get('description', '').strip()

            def render_form_error(message):
                flash(message, "error")
                return render_template(
                    'admin/tournament_form.html',
                    action='edit',
                    tournament=tournament,
                    sports=sports,
                    name=name,
                    selected_sport_id=sport_id_raw,
                    start_date=start_date_raw,
                    end_date=end_date_raw,
                    status=status,
                    description=description
                )

            # 1. Tournament Name validation
            if not name:
                return render_form_error("Tournament name is required and cannot be blank.")
            if len(name) > 150:
                return render_form_error("Tournament name cannot exceed 150 characters.")

            # 2. Sport validation
            if not sport_id_raw:
                return render_form_error("Please select a valid sport category.")
            try:
                sport_id = int(sport_id_raw)
            except ValueError:
                return render_form_error("Invalid sport category selected.")

            cursor.execute("SELECT id, name FROM sports WHERE id = %s", (sport_id,))
            target_sport = cursor.fetchone()
            if not target_sport:
                return render_form_error("The selected sport category does not exist in the system.")

            # 3. Start date & End date validation
            if not start_date_raw:
                return render_form_error("Start date is required.")
            try:
                start_date = datetime.strptime(start_date_raw, '%Y-%m-%d').date()
            except ValueError:
                return render_form_error("Invalid start date format. Please use YYYY-MM-DD.")

            if not end_date_raw:
                return render_form_error("End date is required.")
            try:
                end_date = datetime.strptime(end_date_raw, '%Y-%m-%d').date()
            except ValueError:
                return render_form_error("Invalid end date format. Please use YYYY-MM-DD.")

            if end_date < start_date:
                return render_form_error("End date cannot be earlier than start date.")

            # 4. Status validation
            allowed_statuses = ('upcoming', 'ongoing', 'completed', 'cancelled')
            if status not in allowed_statuses:
                return render_form_error(f"Status must be one of: {', '.join(allowed_statuses)}.")

            # 5. Description formatting
            desc_val = description if description else None

            # Execute update
            cursor.execute(
                """
                UPDATE tournaments 
                SET name = %s, sport_id = %s, start_date = %s, end_date = %s, status = %s, description = %s
                WHERE id = %s
                """,
                (name, sport_id, start_date, end_date, status, desc_val, tournament_id)
            )
            conn.commit()
            flash(f"Tournament '{name}' updated successfully.", "success")
            return redirect(url_for('tournaments_list'))

        return render_template('admin/tournament_form.html', action='edit', tournament=tournament, sports=sports)

    except HTTPException:
        raise
    except MySQLError as e:
        if conn and conn.is_connected():
            conn.rollback()
        flash("A database error occurred while updating the tournament.", "error")
        return redirect(url_for('tournaments_list'))
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('tournaments_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/tournaments/<int:tournament_id>/delete', methods=['POST'])
@admin_required
def tournaments_delete(tournament_id):
    """
    Safely deletes a tournament if no dependent records (e.g. matches) exist.
    Deletion is restricted to POST with CSRF protection.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('tournaments_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM tournaments WHERE id = %s", (tournament_id,))
        tournament = cursor.fetchone()

        if not tournament:
            cursor.close()
            conn.close()
            abort(404)

        # Check for dependent matches
        cursor.execute("SELECT COUNT(*) AS match_count FROM matches WHERE tournament_id = %s", (tournament_id,))
        match_count = cursor.fetchone()['match_count']

        if match_count > 0:
            flash(
                f"Cannot delete tournament '{tournament['name']}': It is currently referenced by {match_count} "
                "scheduled or recorded match(es). Matches must be cancelled, resolved, or removed before this tournament can be deleted.",
                "warning"
            )
            return redirect(url_for('tournaments_list'))

        # Safe to delete
        cursor.execute("DELETE FROM tournaments WHERE id = %s", (tournament_id,))
        conn.commit()
        flash(f"Tournament '{tournament['name']}' deleted successfully.", "success")
        return redirect(url_for('tournaments_list'))

    except HTTPException:
        raise
    except MySQLError as e:
        if conn and conn.is_connected():
            conn.rollback()
        if e.errno == 1451:
            flash(
                f"Cannot delete tournament '{tournament['name']}': Dependent matches exist in the database.",
                "warning"
            )
        else:
            flash("A database error occurred while deleting the tournament.", "error")
        return redirect(url_for('tournaments_list'))
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('tournaments_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# =============================================================================
# Phase 5.5: Matches Management Routes (Admin Only)
# =============================================================================
@app.route('/admin/matches')
@admin_required
def matches_list():
    """
    Renders the matches management overview page.
    Retrieves all matches with joined tournament, sport, competing teams, and result summary.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return render_template('admin/matches.html', matches=[], tournaments=[], sports=[], teams=[])

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT t.id, t.name, t.sport_id, s.name AS sport_name 
            FROM tournaments t 
            JOIN sports s ON t.sport_id = s.id 
            ORDER BY t.name ASC
            """
        )
        tournaments = cursor.fetchall()

        cursor.execute("SELECT id, name FROM sports ORDER BY name ASC")
        sports = cursor.fetchall()

        cursor.execute(
            """
            SELECT tm.id, tm.name, tm.sport_id, s.name AS sport_name 
            FROM teams tm 
            JOIN sports s ON tm.sport_id = s.id 
            ORDER BY tm.name ASC
            """
        )
        teams = cursor.fetchall()

        cursor.execute(
            """
            SELECT 
                m.id, 
                m.tournament_id, 
                tr.name AS tournament_name, 
                tr.sport_id, 
                s.name AS sport_name,
                m.team1_id, 
                t1.name AS team1_name, 
                m.team2_id, 
                t2.name AS team2_name, 
                m.match_datetime, 
                m.venue, 
                m.status, 
                m.created_at,
                r.id AS result_id,
                r.team1_score,
                r.team2_score,
                CASE WHEN r.id IS NOT NULL THEN 1 ELSE 0 END AS has_result
            FROM matches m
            JOIN tournaments tr ON m.tournament_id = tr.id
            JOIN sports s ON tr.sport_id = s.id
            JOIN teams t1 ON m.team1_id = t1.id
            JOIN teams t2 ON m.team2_id = t2.id
            LEFT JOIN results r ON r.match_id = m.id
            ORDER BY m.match_datetime DESC, m.id DESC
            """
        )
        matches = cursor.fetchall()
        return render_template('admin/matches.html', matches=matches, tournaments=tournaments, sports=sports, teams=teams)
    except Exception:
        flash("Failed to retrieve match fixtures. Please try again.", "error")
        return render_template('admin/matches.html', matches=[], tournaments=[], sports=[], teams=[])
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/matches/new', methods=['GET', 'POST'])
@admin_required
def matches_create():
    """
    Handles scheduling a new match.
    GET: Renders blank match fixture form.
    POST: Validates inputs, verifies sport compatibility, executes insert.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('matches_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT t.id, t.name, t.sport_id, s.name AS sport_name 
            FROM tournaments t 
            JOIN sports s ON t.sport_id = s.id 
            ORDER BY t.name ASC
            """
        )
        tournaments = cursor.fetchall()

        cursor.execute(
            """
            SELECT tm.id, tm.name, tm.sport_id, s.name AS sport_name 
            FROM teams tm 
            JOIN sports s ON tm.sport_id = s.id 
            ORDER BY tm.name ASC
            """
        )
        teams = cursor.fetchall()

        if not tournaments:
            flash("No tournaments exist. You must create at least one tournament before scheduling matches.", "warning")
            return redirect(url_for('tournaments_create'))

        if len(teams) < 2:
            flash("At least two teams are required to schedule a match.", "warning")
            return redirect(url_for('teams_create'))

        if request.method == 'POST':
            tournament_id_raw = request.form.get('tournament_id', '').strip()
            team1_id_raw = request.form.get('team1_id', '').strip()
            team2_id_raw = request.form.get('team2_id', '').strip()
            match_datetime_raw = request.form.get('match_datetime', '').strip()
            venue = request.form.get('venue', '').strip()
            status = request.form.get('status', 'scheduled').strip().lower()

            def render_form_error(message):
                flash(message, "error")
                return render_template(
                    'admin/match_form.html',
                    action='add',
                    tournaments=tournaments,
                    teams=teams,
                    selected_tournament_id=tournament_id_raw,
                    selected_team1_id=team1_id_raw,
                    selected_team2_id=team2_id_raw,
                    match_datetime=match_datetime_raw,
                    venue=venue,
                    status=status
                )

            # 1. Tournament validation
            if not tournament_id_raw:
                return render_form_error("Please select a valid tournament.")
            try:
                tournament_id = int(tournament_id_raw)
            except ValueError:
                return render_form_error("Invalid tournament selected.")

            cursor.execute("SELECT id, name, sport_id FROM tournaments WHERE id = %s", (tournament_id,))
            target_tournament = cursor.fetchone()
            if not target_tournament:
                return render_form_error("The selected tournament does not exist in the system.")

            # 2. Competing Teams validation
            if not team1_id_raw or not team2_id_raw:
                return render_form_error("Please select both competing teams.")
            try:
                team1_id = int(team1_id_raw)
                team2_id = int(team2_id_raw)
            except ValueError:
                return render_form_error("Invalid team selection.")

            if team1_id == team2_id:
                return render_form_error("Team 1 and Team 2 must be different teams.")

            cursor.execute("SELECT id, name, sport_id FROM teams WHERE id = %s", (team1_id,))
            target_team1 = cursor.fetchone()
            cursor.execute("SELECT id, name, sport_id FROM teams WHERE id = %s", (team2_id,))
            target_team2 = cursor.fetchone()

            if not target_team1 or not target_team2:
                return render_form_error("One or both of the selected teams do not exist in the system.")

            # Sport compatibility: both teams must belong to tournament sport
            tourney_sport_id = target_tournament['sport_id']
            if target_team1['sport_id'] != tourney_sport_id or target_team2['sport_id'] != tourney_sport_id:
                return render_form_error(
                    "Both competing teams must belong to the same sport discipline as the tournament."
                )

            # 3. Match Date & Time validation
            if not match_datetime_raw:
                return render_form_error("Match date and time is required.")

            match_datetime = None
            for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
                try:
                    match_datetime = datetime.strptime(match_datetime_raw, fmt)
                    break
                except ValueError:
                    pass

            if not match_datetime:
                return render_form_error("Invalid match date and time format. Please provide a valid date and time.")

            # 4. Status validation
            allowed_statuses = ('scheduled', 'ongoing', 'completed', 'cancelled')
            if status not in allowed_statuses:
                return render_form_error(f"Status must be one of: {', '.join(allowed_statuses)}.")

            # 5. Venue formatting
            if len(venue) > 200:
                return render_form_error("Venue cannot exceed 200 characters.")
            venue_val = venue if venue else None

            # Execute insert
            cursor.execute(
                """
                INSERT INTO matches (tournament_id, team1_id, team2_id, match_datetime, venue, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (tournament_id, team1_id, team2_id, match_datetime, venue_val, status)
            )
            conn.commit()
            flash(
                f"Match '{target_team1['name']} vs {target_team2['name']}' scheduled successfully in '{target_tournament['name']}'.",
                "success"
            )
            return redirect(url_for('matches_list'))

        return render_template('admin/match_form.html', action='add', tournaments=tournaments, teams=teams)

    except MySQLError as e:
        if conn and conn.is_connected():
            conn.rollback()
        flash("A database error occurred while scheduling the match.", "error")
        return redirect(url_for('matches_list'))
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('matches_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/matches/<int:match_id>')
@admin_required
def matches_detail(match_id):
    """
    Renders detailed information for a specific match fixture, including result info if recorded.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('matches_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT 
                m.id, 
                m.tournament_id, 
                tr.name AS tournament_name, 
                tr.sport_id, 
                s.name AS sport_name,
                tr.start_date AS tournament_start_date,
                tr.end_date AS tournament_end_date,
                m.team1_id, 
                t1.name AS team1_name, 
                m.team2_id, 
                t2.name AS team2_name, 
                m.match_datetime, 
                m.venue, 
                m.status, 
                m.created_at
            FROM matches m
            JOIN tournaments tr ON m.tournament_id = tr.id
            JOIN sports s ON tr.sport_id = s.id
            JOIN teams t1 ON m.team1_id = t1.id
            JOIN teams t2 ON m.team2_id = t2.id
            WHERE m.id = %s
            """,
            (match_id,)
        )
        match = cursor.fetchone()

        if not match:
            cursor.close()
            conn.close()
            abort(404)

        # Retrieve related result if any
        cursor.execute(
            """
            SELECT 
                r.id, 
                r.team1_score, 
                r.team2_score, 
                r.winner_team_id, 
                tw.name AS winner_team_name, 
                r.notes, 
                r.created_at
            FROM results r
            LEFT JOIN teams tw ON r.winner_team_id = tw.id
            WHERE r.match_id = %s
            """,
            (match_id,)
        )
        result = cursor.fetchone()

        return render_template('admin/match_detail.html', match=match, result=result)

    except HTTPException:
        raise
    except Exception:
        flash("Failed to retrieve match details.", "error")
        return redirect(url_for('matches_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/matches/<int:match_id>/edit', methods=['GET', 'POST'])
@admin_required
def matches_edit(match_id):
    """
    Handles editing an existing match fixture.
    GET: Renders form populated with current match values.
    POST: Validates inputs, verifies sport compatibility, executes update.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('matches_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM matches WHERE id = %s", (match_id,))
        match = cursor.fetchone()

        if not match:
            cursor.close()
            conn.close()
            abort(404)

        # Format datetime for datetime-local input
        if match.get('match_datetime'):
            if isinstance(match['match_datetime'], datetime):
                match['formatted_datetime'] = match['match_datetime'].strftime('%Y-%m-%dT%H:%M')
            else:
                match['formatted_datetime'] = str(match['match_datetime'])[:16].replace(' ', 'T')

        cursor.execute(
            """
            SELECT t.id, t.name, t.sport_id, s.name AS sport_name 
            FROM tournaments t 
            JOIN sports s ON t.sport_id = s.id 
            ORDER BY t.name ASC
            """
        )
        tournaments = cursor.fetchall()

        cursor.execute(
            """
            SELECT tm.id, tm.name, tm.sport_id, s.name AS sport_name 
            FROM teams tm 
            JOIN sports s ON tm.sport_id = s.id 
            ORDER BY tm.name ASC
            """
        )
        teams = cursor.fetchall()

        if request.method == 'POST':
            tournament_id_raw = request.form.get('tournament_id', '').strip()
            team1_id_raw = request.form.get('team1_id', '').strip()
            team2_id_raw = request.form.get('team2_id', '').strip()
            match_datetime_raw = request.form.get('match_datetime', '').strip()
            venue = request.form.get('venue', '').strip()
            status = request.form.get('status', 'scheduled').strip().lower()

            def render_form_error(message):
                flash(message, "error")
                return render_template(
                    'admin/match_form.html',
                    action='edit',
                    match=match,
                    tournaments=tournaments,
                    teams=teams,
                    selected_tournament_id=tournament_id_raw,
                    selected_team1_id=team1_id_raw,
                    selected_team2_id=team2_id_raw,
                    match_datetime=match_datetime_raw,
                    venue=venue,
                    status=status
                )

            # 1. Tournament validation
            if not tournament_id_raw:
                return render_form_error("Please select a valid tournament.")
            try:
                tournament_id = int(tournament_id_raw)
            except ValueError:
                return render_form_error("Invalid tournament selected.")

            cursor.execute("SELECT id, name, sport_id FROM tournaments WHERE id = %s", (tournament_id,))
            target_tournament = cursor.fetchone()
            if not target_tournament:
                return render_form_error("The selected tournament does not exist in the system.")

            # 2. Competing Teams validation
            if not team1_id_raw or not team2_id_raw:
                return render_form_error("Please select both competing teams.")
            try:
                team1_id = int(team1_id_raw)
                team2_id = int(team2_id_raw)
            except ValueError:
                return render_form_error("Invalid team selection.")

            if team1_id == team2_id:
                return render_form_error("Team 1 and Team 2 must be different teams.")

            cursor.execute("SELECT id, name, sport_id FROM teams WHERE id = %s", (team1_id,))
            target_team1 = cursor.fetchone()
            cursor.execute("SELECT id, name, sport_id FROM teams WHERE id = %s", (team2_id,))
            target_team2 = cursor.fetchone()

            if not target_team1 or not target_team2:
                return render_form_error("One or both of the selected teams do not exist in the system.")

            # Sport compatibility: both teams must belong to tournament sport
            tourney_sport_id = target_tournament['sport_id']
            if target_team1['sport_id'] != tourney_sport_id or target_team2['sport_id'] != tourney_sport_id:
                return render_form_error(
                    "Both competing teams must belong to the same sport discipline as the tournament."
                )

            # 3. Match Date & Time validation
            if not match_datetime_raw:
                return render_form_error("Match date and time is required.")

            match_datetime = None
            for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
                try:
                    match_datetime = datetime.strptime(match_datetime_raw, fmt)
                    break
                except ValueError:
                    pass

            if not match_datetime:
                return render_form_error("Invalid match date and time format. Please provide a valid date and time.")

            # 4. Status validation
            allowed_statuses = ('scheduled', 'ongoing', 'completed', 'cancelled')
            if status not in allowed_statuses:
                return render_form_error(f"Status must be one of: {', '.join(allowed_statuses)}.")

            # 5. Venue formatting
            if len(venue) > 200:
                return render_form_error("Venue cannot exceed 200 characters.")
            venue_val = venue if venue else None

            # Execute update
            cursor.execute(
                """
                UPDATE matches 
                SET tournament_id = %s, team1_id = %s, team2_id = %s, match_datetime = %s, venue = %s, status = %s
                WHERE id = %s
                """,
                (tournament_id, team1_id, team2_id, match_datetime, venue_val, status, match_id)
            )
            conn.commit()
            flash(
                f"Match #{match_id} ({target_team1['name']} vs {target_team2['name']}) updated successfully.",
                "success"
            )
            return redirect(url_for('matches_list'))

        return render_template('admin/match_form.html', action='edit', match=match, tournaments=tournaments, teams=teams)

    except HTTPException:
        raise
    except MySQLError as e:
        if conn and conn.is_connected():
            conn.rollback()
        flash("A database error occurred while updating the match.", "error")
        return redirect(url_for('matches_list'))
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('matches_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/matches/<int:match_id>/delete', methods=['POST'])
@admin_required
def matches_delete(match_id):
    """
    Safely deletes a match if no dependent records (e.g. results or player statistics) exist.
    Deletion is restricted to POST with CSRF protection.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('matches_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT m.id, t1.name AS team1_name, t2.name AS team2_name
            FROM matches m
            JOIN teams t1 ON m.team1_id = t1.id
            JOIN teams t2 ON m.team2_id = t2.id
            WHERE m.id = %s
            """,
            (match_id,)
        )
        match = cursor.fetchone()

        if not match:
            cursor.close()
            conn.close()
            abort(404)

        # Check for related results or player statistics
        cursor.execute(
            """
            SELECT 
                (SELECT COUNT(*) FROM results WHERE match_id = %s) AS results_count,
                (SELECT COUNT(*) FROM player_match_stats WHERE match_id = %s) AS stats_count
            """,
            (match_id, match_id)
        )
        counts = cursor.fetchone()
        r_count = counts['results_count']
        s_count = counts['stats_count']

        if r_count > 0 or s_count > 0:
            deps = []
            if r_count:
                deps.append(f"{r_count} recorded result")
            if s_count:
                deps.append(f"{s_count} player match statistic(s)")
            dep_msg = " and ".join(deps)
            flash(
                f"Cannot delete Match #{match_id} ({match['team1_name']} vs {match['team2_name']}): "
                f"It has {dep_msg}. These historical records cannot be deleted as a side effect.",
                "warning"
            )
            return redirect(url_for('matches_list'))

        # Safe to delete
        cursor.execute("DELETE FROM matches WHERE id = %s", (match_id,))
        conn.commit()
        flash(f"Match #{match_id} ({match['team1_name']} vs {match['team2_name']}) deleted successfully.", "success")
        return redirect(url_for('matches_list'))

    except HTTPException:
        raise
    except MySQLError as e:
        if conn and conn.is_connected():
            conn.rollback()
        if e.errno == 1451:
            flash(
                f"Cannot delete Match #{match_id}: Dependent records exist in the database.",
                "warning"
            )
        else:
            flash("A database error occurred while deleting the match.", "error")
        return redirect(url_for('matches_list'))
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('matches_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# =============================================================================
# Phase 5.6: Results & Score Management Routes (Admin Only)
# =============================================================================
def validate_match_result(team1_id, team2_id, team1_score_raw, team2_score_raw, tie_breaker_winner_raw, notes_raw):
    """
    Validates score inputs, derives winner_team_id, and enforces tie-break rules.
    Returns (is_valid, error_message, team1_score, team2_score, winner_team_id, notes)
    """
    if team1_score_raw == '' or team2_score_raw == '':
        return False, "Both team scores are required.", None, None, None, None

    try:
        t1_score = int(team1_score_raw)
        t2_score = int(team2_score_raw)
    except ValueError:
        return False, "Scores must be valid whole numbers.", None, None, None, None

    if t1_score < 0 or t2_score < 0:
        return False, "Scores cannot be negative.", None, None, None, None

    if t1_score > 65535 or t2_score > 65535:
        return False, "Scores exceed the maximum permitted limit of 65,535.", None, None, None, None

    notes = notes_raw.strip() if notes_raw else ""

    # Rule A: Team 1 score is greater -> Winner must be Team 1
    if t1_score > t2_score:
        winner_team_id = team1_id
    # Rule B: Team 2 score is greater -> Winner must be Team 2
    elif t2_score > t1_score:
        winner_team_id = team2_id
    # Rule C: Scores are equal
    else:
        if tie_breaker_winner_raw:
            try:
                tb_winner = int(tie_breaker_winner_raw)
            except ValueError:
                return False, "Invalid tie-break winner selected.", None, None, None, None

            if tb_winner not in (team1_id, team2_id):
                return False, "Tie-break winner must be one of the two competing teams.", None, None, None, None

            if not notes:
                return False, "A tie-break winner requires non-empty explanatory notes specifying the tie-break method and outcome.", None, None, None, None

            winner_team_id = tb_winner
        else:
            winner_team_id = None  # Official draw

    notes_val = notes if notes else None
    return True, None, t1_score, t2_score, winner_team_id, notes_val


@app.route('/admin/results')
@admin_required
def results_list():
    """
    Renders the results and score management overview page.
    Retrieves all matches joined with tournament, sport, competing teams, and official results.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return render_template('admin/results.html', matches=[], tournaments=[], sports=[], recorded_count=0, pending_count=0)

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM tournaments ORDER BY name ASC")
        tournaments = cursor.fetchall()

        cursor.execute("SELECT id, name FROM sports ORDER BY name ASC")
        sports = cursor.fetchall()

        cursor.execute(
            """
            SELECT 
                m.id, 
                m.tournament_id, 
                tr.name AS tournament_name, 
                tr.sport_id, 
                s.name AS sport_name,
                m.team1_id, 
                t1.name AS team1_name, 
                m.team2_id, 
                t2.name AS team2_name, 
                m.match_datetime, 
                m.venue, 
                m.status, 
                r.id AS result_id,
                r.team1_score,
                r.team2_score,
                r.winner_team_id,
                tw.name AS winner_team_name,
                r.notes,
                CASE WHEN r.id IS NOT NULL THEN 1 ELSE 0 END AS has_result
            FROM matches m
            JOIN tournaments tr ON m.tournament_id = tr.id
            JOIN sports s ON tr.sport_id = s.id
            JOIN teams t1 ON m.team1_id = t1.id
            JOIN teams t2 ON m.team2_id = t2.id
            LEFT JOIN results r ON r.match_id = m.id
            LEFT JOIN teams tw ON r.winner_team_id = tw.id
            ORDER BY m.match_datetime DESC, m.id DESC
            """
        )
        matches = cursor.fetchall()

        recorded_count = sum(1 for m in matches if m['has_result'])
        pending_count = len(matches) - recorded_count

        return render_template(
            'admin/results.html',
            matches=matches,
            tournaments=tournaments,
            sports=sports,
            recorded_count=recorded_count,
            pending_count=pending_count
        )
    except Exception:
        flash("Failed to retrieve match results. Please try again.", "error")
        return render_template('admin/results.html', matches=[], tournaments=[], sports=[], recorded_count=0, pending_count=0)
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/results/<int:match_id>/edit', methods=['GET', 'POST'])
@admin_required
def results_edit(match_id):
    """
    Handles creating or updating the official score and result for a match.
    Enforces atomic transaction: writes results and marks match completed.
    Cancelled matches cannot have results recorded or modified.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('results_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT 
                m.id, 
                m.tournament_id, 
                tr.name AS tournament_name, 
                tr.sport_id, 
                s.name AS sport_name,
                m.team1_id, 
                t1.name AS team1_name, 
                m.team2_id, 
                t2.name AS team2_name, 
                m.match_datetime, 
                m.venue, 
                m.status
            FROM matches m
            JOIN tournaments tr ON m.tournament_id = tr.id
            JOIN sports s ON tr.sport_id = s.id
            JOIN teams t1 ON m.team1_id = t1.id
            JOIN teams t2 ON m.team2_id = t2.id
            WHERE m.id = %s
            """,
            (match_id,)
        )
        match = cursor.fetchone()

        if not match:
            cursor.close()
            conn.close()
            abort(404)

        if match['status'] == 'cancelled':
            flash(f"Cannot record or modify results for Match #{match_id}: This match has been cancelled.", "warning")
            return redirect(url_for('results_list'))

        cursor.execute("SELECT * FROM results WHERE match_id = %s", (match_id,))
        result = cursor.fetchone()

        if request.method == 'POST':
            team1_score_raw = request.form.get('team1_score', '').strip()
            team2_score_raw = request.form.get('team2_score', '').strip()
            tie_breaker_winner_raw = request.form.get('tie_breaker_winner', '').strip()
            notes_raw = request.form.get('notes', '').strip()

            is_valid, err_msg, t1_score, t2_score, winner_team_id, notes_val = validate_match_result(
                match['team1_id'],
                match['team2_id'],
                team1_score_raw,
                team2_score_raw,
                tie_breaker_winner_raw,
                notes_raw
            )

            if not is_valid:
                flash(err_msg, "error")
                return render_template(
                    'admin/result_form.html',
                    match=match,
                    result=result,
                    team1_score=team1_score_raw,
                    team2_score=team2_score_raw,
                    tie_breaker_winner=tie_breaker_winner_raw,
                    notes=notes_raw
                )

            # Atomic transaction: insert/update result and set match to completed
            if result:
                cursor.execute(
                    """
                    UPDATE results 
                    SET team1_score = %s, team2_score = %s, winner_team_id = %s, notes = %s
                    WHERE match_id = %s
                    """,
                    (t1_score, t2_score, winner_team_id, notes_val, match_id)
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO results (match_id, team1_score, team2_score, winner_team_id, notes)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (match_id, t1_score, t2_score, winner_team_id, notes_val)
                )

            cursor.execute(
                "UPDATE matches SET status = 'completed' WHERE id = %s",
                (match_id,)
            )

            conn.commit()
            flash(f"Official result for Match #{match_id} recorded successfully.", "success")
            return redirect(url_for('results_list'))

        return render_template('admin/result_form.html', match=match, result=result)

    except HTTPException:
        raise
    except MySQLError as e:
        if conn and conn.is_connected():
            conn.rollback()
        flash("A database error occurred while saving the match result.", "error")
        return redirect(url_for('results_list'))
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('results_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()

# =============================================================================
# Phase 5.7: Tournament Standings & Leaderboards (Admin Only)
# =============================================================================
def calculate_tournament_standings(sport_name, matches_results):
    """
    Calculates standings statistics from completed matches with valid results.
    - Counts matches only once per participating team.
    - Excludes teams that did not participate in any qualifying completed matches.
    - Derives wins, losses, ordinary draws (equal scores with NULL winner),
      and tie-break decisions (equal scores with winner specified).
    - Calculates score totals (GF/PF/SF), score conceded (GA/PA/SA), and difference (GD/PD/SD).
    - Applies sport-specific scoring rules:
        * Football/Soccer: Standard 3-1-0 points system (3 for win/tie-break win, 1 for draw, 0 for loss).
        * Other sports (Basketball, Volleyball, Carrom, etc.): Documents that tournament point systems
          are not formally configured. Points set to None, ordered deterministically by performance metrics.
    Returns: (standings_list, scoring_info_dict)
    """
    sport_lower = (sport_name or '').lower()
    is_football = 'football' in sport_lower or 'soccer' in sport_lower
    is_basketball = 'basketball' in sport_lower

    if is_football:
        scoring_info = {
            'system_name': 'Association Football (Soccer) 3-1-0 Point System',
            'description': '3 points for a regulation or tie-break win, 1 point for an ordinary draw, 0 points for a loss.',
            'has_points_rule': True,
            'is_official_ranking': True,
            'metric_name': 'Goals',
            'metric_for': 'GF',
            'metric_against': 'GA',
            'metric_diff': 'GD',
        }
    elif is_basketball:
        scoring_info = {
            'system_name': 'Basketball Performance Summary',
            'description': f'Official tournament league points and tie-breakers are not configured for {sport_name}. Statistics are ordered by Wins → Score Difference → Points For for display purposes only.',
            'has_points_rule': False,
            'is_official_ranking': False,
            'metric_name': 'Points',
            'metric_for': 'PF',
            'metric_against': 'PA',
            'metric_diff': 'PD',
        }
    else:
        scoring_info = {
            'system_name': f'{sport_name or "Sport"} Performance Summary',
            'description': f'Official tournament league points and tie-breakers are not configured for {sport_name or "this sport"}. Statistics are ordered by Wins → Score Difference → Score For for display purposes only.',
            'has_points_rule': False,
            'is_official_ranking': False,
            'metric_name': 'Score',
            'metric_for': 'SF',
            'metric_against': 'SA',
            'metric_diff': 'SD',
        }

    teams_stats = {}

    for m in matches_results:
        t1_id = m['team1_id']
        t2_id = m['team2_id']
        t1_name = m['team1_name']
        t2_name = m['team2_name']
        s1 = m['team1_score']
        s2 = m['team2_score']
        winner_id = m['winner_team_id']

        if t1_id not in teams_stats:
            teams_stats[t1_id] = {
                'team_id': t1_id,
                'team_name': t1_name,
                'played': 0,
                'wins': 0,
                'draws': 0,
                'losses': 0,
                'tie_break_wins': 0,
                'tie_break_losses': 0,
                'score_for': 0,
                'score_against': 0,
            }
        if t2_id not in teams_stats:
            teams_stats[t2_id] = {
                'team_id': t2_id,
                'team_name': t2_name,
                'played': 0,
                'wins': 0,
                'draws': 0,
                'losses': 0,
                'tie_break_wins': 0,
                'tie_break_losses': 0,
                'score_for': 0,
                'score_against': 0,
            }

        # Update played count and scores
        teams_stats[t1_id]['played'] += 1
        teams_stats[t2_id]['played'] += 1
        teams_stats[t1_id]['score_for'] += s1
        teams_stats[t1_id]['score_against'] += s2
        teams_stats[t2_id]['score_for'] += s2
        teams_stats[t2_id]['score_against'] += s1

        # Match outcome
        if s1 > s2:
            # Decisive Win for Team 1
            teams_stats[t1_id]['wins'] += 1
            teams_stats[t2_id]['losses'] += 1
        elif s2 > s1:
            # Decisive Win for Team 2
            teams_stats[t2_id]['wins'] += 1
            teams_stats[t1_id]['losses'] += 1
        else:
            # Equal scores
            if winner_id is None:
                # Ordinary Draw
                teams_stats[t1_id]['draws'] += 1
                teams_stats[t2_id]['draws'] += 1
            elif winner_id == t1_id:
                # Tie-break win for Team 1
                teams_stats[t1_id]['tie_break_wins'] += 1
                teams_stats[t2_id]['tie_break_losses'] += 1
            elif winner_id == t2_id:
                # Tie-break win for Team 2
                teams_stats[t2_id]['tie_break_wins'] += 1
                teams_stats[t1_id]['tie_break_losses'] += 1

    standings = []
    for t in teams_stats.values():
        score_diff = t['score_for'] - t['score_against']
        total_wins = t['wins'] + t['tie_break_wins']
        total_losses = t['losses'] + t['tie_break_losses']

        if scoring_info['has_points_rule']:
            # Football 3-1-0: 3 for win (incl. tie-break win), 1 for draw, 0 for loss
            points = (t['wins'] * 3) + (t['tie_break_wins'] * 3) + (t['draws'] * 1)
        else:
            points = None

        standings.append({
            'team_id': t['team_id'],
            'team_name': t['team_name'],
            'played': t['played'],
            'wins': t['wins'],
            'draws': t['draws'],
            'losses': t['losses'],
            'tie_break_wins': t['tie_break_wins'],
            'tie_break_losses': t['tie_break_losses'],
            'total_wins': total_wins,
            'total_losses': total_losses,
            'score_for': t['score_for'],
            'score_against': t['score_against'],
            'score_diff': score_diff,
            'points': points,
        })

    # Deterministic sorting
    if scoring_info['has_points_rule']:
        standings.sort(
            key=lambda item: (
                -item['points'],
                -item['score_diff'],
                -item['score_for'],
                -item['total_wins'],
                item['team_name'].lower()
            )
        )
    else:
        standings.sort(
            key=lambda item: (
                -item['total_wins'],
                -item['wins'],
                -item['score_diff'],
                -item['score_for'],
                item['team_name'].lower()
            )
        )

    return standings, scoring_info


def get_tournament_leaderboards(tournament_id, sport_name, cursor):
    """
    Aggregates player-match statistics for a tournament's completed matches with valid results.
    Avoids duplicate counting and returns categorized leaderboards based on sport discipline.
    """
    cursor.execute(
        """
        SELECT 
            p.id AS player_id,
            p.full_name AS player_name,
            p.jersey_number,
            t.id AS team_id,
            t.name AS team_name,
            COUNT(DISTINCT pms.match_id) AS matches_played,
            COALESCE(SUM(pms.goals), 0) AS total_goals,
            COALESCE(SUM(pms.assists), 0) AS total_assists,
            COALESCE(SUM(pms.points), 0) AS total_points
        FROM player_match_stats pms
        JOIN players p ON pms.player_id = p.id
        JOIN matches m ON pms.match_id = m.id
        JOIN results r ON r.match_id = m.id
        LEFT JOIN teams t ON p.team_id = t.id
        WHERE m.tournament_id = %s
          AND m.status = 'completed'
        GROUP BY p.id, p.full_name, p.jersey_number, t.id, t.name
        ORDER BY p.full_name ASC
        """,
        (tournament_id,)
    )
    rows = cursor.fetchall()

    sport_lower = (sport_name or '').lower()
    is_football = 'football' in sport_lower or 'soccer' in sport_lower
    is_basketball = 'basketball' in sport_lower

    goals_leaderboard = [r for r in rows if r['total_goals'] > 0]
    goals_leaderboard.sort(key=lambda x: (-x['total_goals'], x['matches_played'], x['player_name'].lower()))

    assists_leaderboard = [r for r in rows if r['total_assists'] > 0]
    assists_leaderboard.sort(key=lambda x: (-x['total_assists'], x['matches_played'], x['player_name'].lower()))

    points_leaderboard = [r for r in rows if r['total_points'] > 0]
    points_leaderboard.sort(key=lambda x: (-x['total_points'], x['matches_played'], x['player_name'].lower()))

    has_any = (len(goals_leaderboard) > 0 or len(assists_leaderboard) > 0 or len(points_leaderboard) > 0)

    # Determine which leaderboards to display based on sport
    show_goals = is_football or (not is_basketball and len(goals_leaderboard) > 0)
    show_assists = is_football or is_basketball or len(assists_leaderboard) > 0
    show_points = is_basketball or (not is_football and len(points_leaderboard) > 0)

    return {
        'has_any': has_any,
        'show_goals': show_goals,
        'show_assists': show_assists,
        'show_points': show_points,
        'goals': goals_leaderboard,
        'assists': assists_leaderboard,
        'points': points_leaderboard,
    }


@app.route('/admin/standings')
@admin_required
def standings_redirect():
    """
    Convenience route for standings. Redirects to the first tournament's standings page,
    or redirects to tournaments list if none exist.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('tournaments_list'))
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM tournaments ORDER BY id ASC LIMIT 1")
        row = cursor.fetchone()
        if row:
            return redirect(url_for('tournaments_standings', tournament_id=row['id']))
        flash("No tournaments exist in the system. Create a tournament first.", "warning")
        return redirect(url_for('tournaments_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/tournaments/<int:tournament_id>/standings')
@admin_required
def tournaments_standings(tournament_id):
    """
    Renders the official standings table and player leaderboards for a tournament.
    Only completed matches with valid results are included in standings calculations.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('tournaments_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        # Fetch tournament with sport
        cursor.execute(
            """
            SELECT 
                t.id, 
                t.name, 
                t.sport_id, 
                s.name AS sport_name, 
                t.start_date, 
                t.end_date, 
                t.status, 
                t.description
            FROM tournaments t
            JOIN sports s ON t.sport_id = s.id
            WHERE t.id = %s
            """,
            (tournament_id,)
        )
        tournament = cursor.fetchone()

        if not tournament:
            cursor.close()
            conn.close()
            abort(404)

        # Fetch all tournaments for switcher
        cursor.execute(
            """
            SELECT t.id, t.name, s.name AS sport_name 
            FROM tournaments t 
            JOIN sports s ON t.sport_id = s.id 
            ORDER BY t.name ASC
            """
        )
        all_tournaments = cursor.fetchall()

        # Query completed matches with results
        cursor.execute(
            """
            SELECT 
                m.id AS match_id,
                m.tournament_id,
                m.team1_id,
                t1.name AS team1_name,
                m.team2_id,
                t2.name AS team2_name,
                r.team1_score,
                r.team2_score,
                r.winner_team_id,
                r.notes
            FROM matches m
            JOIN results r ON r.match_id = m.id
            JOIN teams t1 ON m.team1_id = t1.id
            JOIN teams t2 ON m.team2_id = t2.id
            WHERE m.tournament_id = %s
              AND m.status = 'completed'
            ORDER BY m.match_datetime ASC, m.id ASC
            """,
            (tournament_id,)
        )
        completed_matches = cursor.fetchall()

        # Compute standings
        standings, scoring_info = calculate_tournament_standings(
            tournament['sport_name'],
            completed_matches
        )

        # Compute player leaderboards
        leaderboard_data = get_tournament_leaderboards(
            tournament_id,
            tournament['sport_name'],
            cursor
        )

        return render_template(
            'admin/standings.html',
            tournament=tournament,
            all_tournaments=all_tournaments,
            completed_matches_count=len(completed_matches),
            standings=standings,
            scoring_info=scoring_info,
            has_any_player_stats=leaderboard_data['has_any'],
            show_goals_leaderboard=leaderboard_data['show_goals'],
            show_assists_leaderboard=leaderboard_data['show_assists'],
            show_points_leaderboard=leaderboard_data['show_points'],
            goals_leaderboard=leaderboard_data['goals'],
            assists_leaderboard=leaderboard_data['assists'],
            points_leaderboard=leaderboard_data['points'],
        )

    except HTTPException:
        raise
    except Exception:
        flash("Failed to retrieve tournament standings.", "error")
        return redirect(url_for('tournaments_list'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# =============================================================================
# Phase 7: User Management Routes
# =============================================================================
@app.route('/admin/users', methods=['GET'])
@login_required
@admin_required
def users_list():
    """
    Admin-only page to view, search, and filter user accounts.
    Displays username, email, role, status, and creation date. Never exposes password hashes.
    """
    search_query = request.args.get('search', request.args.get('q', '')).strip()
    role_filter = request.args.get('role', '').strip().lower()
    status_filter = request.args.get('status', '').strip().lower()

    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('admin_dashboard'))

    try:
        cursor = conn.cursor(dictionary=True)

        # Summary statistics
        cursor.execute("""
            SELECT 
                COUNT(*) AS total_users,
                SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active_users,
                SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) AS inactive_users,
                SUM(CASE WHEN role = 'admin' THEN 1 ELSE 0 END) AS admin_users,
                SUM(CASE WHEN role = 'player' THEN 1 ELSE 0 END) AS player_users
            FROM users
        """)
        summary = cursor.fetchone() or {}

        # Base query joining players table to check for linked player profile
        query = """
            SELECT 
                u.id, 
                u.username, 
                u.email, 
                u.role, 
                u.is_active, 
                u.created_at,
                p.id AS player_id,
                p.full_name AS player_name
            FROM users u
            LEFT JOIN players p ON p.user_id = u.id
            WHERE 1=1
        """
        params = []

        if search_query:
            query += " AND (u.username LIKE %s OR u.email LIKE %s)"
            like_term = f"%{search_query}%"
            params.extend([like_term, like_term])

        if role_filter in ['admin', 'player']:
            query += " AND u.role = %s"
            params.append(role_filter)

        if status_filter in ['active', '1']:
            query += " AND u.is_active = 1"
        elif status_filter in ['inactive', '0']:
            query += " AND u.is_active = 0"

        query += " ORDER BY u.id ASC"

        cursor.execute(query, tuple(params))
        users = cursor.fetchall()
        cursor.close()
        conn.close()

        return render_template(
            'admin/users.html',
            users=users,
            summary=summary,
            search_query=search_query,
            role_filter=role_filter,
            status_filter=status_filter
        )

    except HTTPException:
        raise
    except Exception:
        flash("An error occurred while loading user accounts.", "error")
        return redirect(url_for('admin_dashboard'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def user_create():
    """
    Admin-only page to create a new user account (role: 'player' or 'admin').
    GET: Renders user creation form.
    POST: Validates username, email, role, and password; hashes password and inserts user into database.
    """
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        role = request.form.get('role', 'player').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        def render_form_error(msg):
            flash(msg, "error")
            return render_template(
                'admin/user_form.html',
                username=username,
                email=email,
                role=role
            )

        # Validate username
        if not username:
            return render_form_error("Username is required and cannot be empty.")
        if len(username) > 50:
            return render_form_error("Username cannot exceed 50 characters.")
        if " " in username:
            return render_form_error("Username cannot contain spaces.")
        if not re.match(r'^[a-zA-Z0-9_.-]+$', username):
            return render_form_error("Username may only contain letters, numbers, dots, hyphens, and underscores.")

        # Validate email
        if not email:
            return render_form_error("Email address is required.")
        if len(email) > 150:
            return render_form_error("Email address cannot exceed 150 characters.")
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            return render_form_error("Please enter a valid email address.")

        # Validate role
        if role not in ['player', 'admin']:
            return render_form_error("Invalid role specified. Must be 'player' or 'admin'.")

        # Validate password
        if not password or len(password) < 8:
            return render_form_error("Password must be at least 8 characters long.")
        if len(password) > 128:
            return render_form_error("Password cannot exceed 128 characters.")
        if password != confirm_password:
            return render_form_error("Passwords do not match. Please re-enter.")

        conn = get_db_connection()
        if conn is None:
            flash("Database service unavailable. Please try again later.", "error")
            return redirect(url_for('users_list'))

        try:
            cursor = conn.cursor(dictionary=True)

            # Check username uniqueness
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return render_form_error(f"Username '{username}' is already taken.")

            # Check email uniqueness
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return render_form_error(f"Email '{email}' is already registered.")

            # Hash password and insert
            pwd_hash = generate_password_hash(password)
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, %s, 1)
                """,
                (username, email, pwd_hash, role)
            )
            conn.commit()
            cursor.close()
            conn.close()

            flash(f"User account '{username}' ({role.capitalize()}) created successfully.", "success")
            return redirect(url_for('users_list'))

        except MySQLError as e:
            if conn and conn.is_connected():
                conn.rollback()
                conn.close()
            if e.errno == 1062:
                return render_form_error("A user with that username or email already exists.")
            flash("A database error occurred while creating the user account.", "error")
            return redirect(url_for('users_list'))
        except Exception:
            if conn and conn.is_connected():
                conn.rollback()
                conn.close()
            flash("An unexpected error occurred. Please try again.", "error")
            return redirect(url_for('users_list'))
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    return render_template('admin/user_form.html', role='player')


@app.route('/admin/users/<int:user_id>/status', methods=['POST'])
@app.route('/admin/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def user_toggle_status(user_id):
    """
    Activates or deactivates a user account.
    Guarantees:
      - Admin cannot deactivate their own account.
      - Last active administrator cannot be deactivated (row-locked check).
      - Deactivated users immediately lose access to authenticated routes.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('users_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, username, email, role, is_active FROM users WHERE id = %s",
            (user_id,)
        )
        target_user = cursor.fetchone()
        if not target_user:
            cursor.close()
            conn.close()
            abort(404)

        status_param = request.form.get('status', '').strip().lower()
        if status_param in ['activate', '1']:
            new_status = 1
        elif status_param in ['deactivate', '0']:
            new_status = 0
        else:
            new_status = 0 if target_user['is_active'] == 1 else 1

        # Prevent deactivating self
        if new_status == 0 and target_user['id'] == g.current_user['id']:
            cursor.close()
            conn.close()
            flash("You cannot deactivate your own administrator account.", "error")
            return redirect(url_for('users_list'))

        # Prevent deactivating the last active administrator
        if new_status == 0 and target_user['role'] == 'admin' and target_user['is_active'] == 1:
            if not conn.in_transaction:
                conn.start_transaction()
            cursor.execute(
                "SELECT COUNT(*) AS active_admins FROM users WHERE role = 'admin' AND is_active = 1 FOR UPDATE"
            )
            active_admin_row = cursor.fetchone()
            active_admin_count = active_admin_row['active_admins'] if active_admin_row else 0
            if active_admin_count <= 1:
                if conn.in_transaction:
                    conn.rollback()
                cursor.close()
                conn.close()
                flash("Cannot deactivate the last active administrator.", "error")
                return redirect(url_for('users_list'))

        # Check if already in desired state
        if new_status == target_user['is_active']:
            action_desc = "active" if new_status == 1 else "deactivated"
            flash(f"User '{target_user['username']}' is already {action_desc}.", "info")
            cursor.close()
            conn.close()
            return redirect(url_for('users_list'))

        # Update status
        cursor.execute("UPDATE users SET is_active = %s WHERE id = %s", (new_status, user_id))
        conn.commit()
        cursor.close()
        conn.close()

        action_word = "activated" if new_status == 1 else "deactivated"
        flash(f"User '{target_user['username']}' account has been {action_word}.", "success")
        return redirect(url_for('users_list'))

    except HTTPException:
        raise
    except Exception:
        if conn and conn.is_connected():
            if conn.in_transaction:
                conn.rollback()
            conn.close()
        flash("An error occurred while updating account status.", "error")
        return redirect(url_for('users_list'))


@app.route('/admin/users/<int:user_id>/role', methods=['POST'])
@login_required
@admin_required
def user_change_role(user_id):
    """
    Updates the role of a user account between 'admin' and 'player'.
    Guarantees:
      - Supported roles: 'admin' and 'player'.
      - Admin cannot remove their own admin role.
      - Last active administrator cannot be demoted (row-locked check).
      - Player linked to an active player profile cannot be changed to 'admin'
        until unlinked in Player Management.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('users_list'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, username, email, role, is_active FROM users WHERE id = %s",
            (user_id,)
        )
        target_user = cursor.fetchone()
        if not target_user:
            cursor.close()
            conn.close()
            abort(404)

        new_role = request.form.get('role', '').strip().lower()

        # Validate role value
        if new_role not in ['admin', 'player']:
            cursor.close()
            conn.close()
            flash("Invalid role specified. Supported roles are 'admin' and 'player'.", "error")
            return redirect(url_for('users_list'))

        # Check if already has specified role
        if new_role == target_user['role']:
            cursor.close()
            conn.close()
            flash(f"User '{target_user['username']}' already has the '{new_role}' role.", "info")
            return redirect(url_for('users_list'))

        # Prevent removing own admin role
        if target_user['id'] == g.current_user['id'] and target_user['role'] == 'admin' and new_role != 'admin':
            cursor.close()
            conn.close()
            flash("You cannot remove your own administrator role.", "error")
            return redirect(url_for('users_list'))

        # Prevent removing the role of the last active administrator
        if target_user['role'] == 'admin' and target_user['is_active'] == 1 and new_role != 'admin':
            if not conn.in_transaction:
                conn.start_transaction()
            cursor.execute(
                "SELECT COUNT(*) AS active_admins FROM users WHERE role = 'admin' AND is_active = 1 FOR UPDATE"
            )
            active_admin_row = cursor.fetchone()
            active_admin_count = active_admin_row['active_admins'] if active_admin_row else 0
            if active_admin_count <= 1:
                if conn.in_transaction:
                    conn.rollback()
                cursor.close()
                conn.close()
                flash("Cannot remove admin role from the last active administrator.", "error")
                return redirect(url_for('users_list'))

        # Check account linking compatibility when promoting player to admin
        if target_user['role'] == 'player' and new_role == 'admin':
            cursor.execute(
                "SELECT id, full_name FROM players WHERE user_id = %s",
                (user_id,)
            )
            linked_player = cursor.fetchone()
            if linked_player:
                if conn.in_transaction:
                    conn.rollback()
                cursor.close()
                conn.close()
                flash(
                    f"Cannot change role to 'admin' while user is linked to player profile '{linked_player['full_name']}'. "
                    "Please unlink the player profile in Player Management first.",
                    "error"
                )
                return redirect(url_for('users_list'))

        # Update role
        cursor.execute("UPDATE users SET role = %s WHERE id = %s", (new_role, user_id))
        conn.commit()
        cursor.close()
        conn.close()

        flash(f"Role for user '{target_user['username']}' has been updated to '{new_role}'.", "success")
        return redirect(url_for('users_list'))

    except HTTPException:
        raise
    except Exception:
        if conn and conn.is_connected():
            if conn.in_transaction:
                conn.rollback()
            conn.close()
        flash("An error occurred while updating user role.", "error")
        return redirect(url_for('users_list'))


# =============================================================================
# Phase 8: Reports & Analytics Routes
# =============================================================================

def make_safe_csv_response(rows, filename):
    """
    Constructs an HTTP Response streaming a CSV with proper headers, MIME type,
    RFC 4180 escaping, and formula injection defense.
    """
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    for row in rows:
        safe_row = []
        for cell in row:
            if isinstance(cell, str) and cell and cell[0] in ('=', '+', '-', '@', '\t', '\r', '%'):
                # Prefix leading formula characters with a single quote to prevent spreadsheet injection
                safe_row.append("'" + cell)
            elif cell is None:
                safe_row.append('')
            else:
                safe_row.append(str(cell))
        writer.writerow(safe_row)

    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@app.route('/admin/reports', methods=['GET'])
@login_required
@admin_required
def admin_reports():
    """
    Admin-only reports and analytics dashboard.
    Displays system-wide KPI summary metrics, tournament-specific breakdown
    (reusing Phase 5.7 standings calculation), team roster activity, and
    overall player performance rankings.
    """
    tournament_id_raw = request.args.get('tournament_id', '').strip()
    selected_tournament_id = None
    if tournament_id_raw:
        try:
            selected_tournament_id = int(tournament_id_raw)
            if selected_tournament_id <= 0:
                abort(404)
        except ValueError:
            abort(404)

    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable. Please try again later.", "error")
        return redirect(url_for('admin_dashboard'))

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. System-wide summary KPIs
        cursor.execute("SELECT COUNT(*) AS total_sports FROM sports")
        total_sports = cursor.fetchone()['total_sports']

        cursor.execute("SELECT COUNT(*) AS total_teams FROM teams")
        total_teams = cursor.fetchone()['total_teams']

        cursor.execute("SELECT COUNT(*) AS total_players FROM players")
        total_players = cursor.fetchone()['total_players']

        cursor.execute("SELECT COUNT(*) AS total_tournaments FROM tournaments")
        total_tournaments = cursor.fetchone()['total_tournaments']

        cursor.execute("SELECT COUNT(*) AS total_matches FROM matches")
        total_matches = cursor.fetchone()['total_matches']

        cursor.execute("SELECT COUNT(*) AS completed_matches FROM matches WHERE status = 'completed'")
        completed_matches_count = cursor.fetchone()['completed_matches']

        cursor.execute("SELECT COUNT(*) AS upcoming_matches FROM matches WHERE status IN ('scheduled', 'ongoing')")
        upcoming_matches_count = cursor.fetchone()['upcoming_matches']

        cursor.execute("""
            SELECT COUNT(*) AS matches_without_results
            FROM matches m
            LEFT JOIN results r ON r.match_id = m.id
            WHERE r.id IS NULL
        """)
        matches_without_results_count = cursor.fetchone()['matches_without_results']

        summary = {
            'total_sports': total_sports,
            'total_teams': total_teams,
            'total_players': total_players,
            'total_tournaments': total_tournaments,
            'total_matches': total_matches,
            'completed_matches': completed_matches_count,
            'upcoming_matches': upcoming_matches_count,
            'matches_without_results': matches_without_results_count,
        }

        # 2. All tournaments list for the selector
        cursor.execute("""
            SELECT t.id, t.name, s.name AS sport_name, t.status
            FROM tournaments t
            JOIN sports s ON t.sport_id = s.id
            ORDER BY t.name ASC
        """)
        all_tournaments = cursor.fetchall()

        # 3. Tournament-specific report (if tournament_id specified)
        selected_tournament = None
        standings = []
        scoring_info = {}
        tournament_matches = []
        participating_teams = []

        if selected_tournament_id:
            cursor.execute("""
                SELECT t.id, t.name, t.sport_id, s.name AS sport_name,
                       t.start_date, t.end_date, t.status, t.description
                FROM tournaments t
                JOIN sports s ON t.sport_id = s.id
                WHERE t.id = %s
            """, (selected_tournament_id,))
            selected_tournament = cursor.fetchone()
            if not selected_tournament:
                cursor.close()
                conn.close()
                abort(404)

            # Query all matches for this tournament
            cursor.execute("""
                SELECT m.id, m.tournament_id, m.match_datetime, m.venue, m.status,
                       m.team1_id, t1.name AS team1_name,
                       m.team2_id, t2.name AS team2_name,
                       r.id AS result_id, r.team1_score, r.team2_score, r.winner_team_id,
                       w.name AS winner_name
                FROM matches m
                JOIN teams t1 ON m.team1_id = t1.id
                JOIN teams t2 ON m.team2_id = t2.id
                LEFT JOIN results r ON r.match_id = m.id
                LEFT JOIN teams w ON r.winner_team_id = w.id
                WHERE m.tournament_id = %s
                ORDER BY m.match_datetime ASC, m.id ASC
            """, (selected_tournament_id,))
            tournament_matches = cursor.fetchall()

            # Re-use Phase 5.7 standings calculation
            completed_matches_results = [
                m for m in tournament_matches
                if m['status'] == 'completed' and m['result_id'] is not None
            ]
            standings, scoring_info = calculate_tournament_standings(
                selected_tournament['sport_name'],
                completed_matches_results
            )

            # Participating teams in this tournament
            cursor.execute("""
                SELECT DISTINCT tm.id, tm.name, s.name AS sport_name,
                       COUNT(DISTINCT p.id) AS player_count
                FROM teams tm
                JOIN sports s ON tm.sport_id = s.id
                LEFT JOIN players p ON p.team_id = tm.id
                WHERE tm.id IN (
                    SELECT team1_id FROM matches WHERE tournament_id = %s
                    UNION
                    SELECT team2_id FROM matches WHERE tournament_id = %s
                )
                GROUP BY tm.id, tm.name, s.name
                ORDER BY tm.name ASC
            """, (selected_tournament_id, selected_tournament_id))
            participating_teams = cursor.fetchall()

        # 4. Overall top performing players across the database
        cursor.execute("""
            SELECT p.id, p.full_name, p.jersey_number, s.name AS sport_name,
                   t.name AS team_name,
                   COUNT(DISTINCT pms.match_id) AS matches_played,
                   COALESCE(SUM(pms.goals), 0) AS total_goals,
                   COALESCE(SUM(pms.assists), 0) AS total_assists,
                   COALESCE(SUM(pms.points), 0) AS total_points
            FROM players p
            JOIN sports s ON p.sport_id = s.id
            LEFT JOIN teams t ON p.team_id = t.id
            LEFT JOIN player_match_stats pms ON pms.player_id = p.id
            GROUP BY p.id, p.full_name, p.jersey_number, s.name, t.name
            HAVING matches_played > 0 OR total_goals > 0 OR total_assists > 0 OR total_points > 0
            ORDER BY total_goals DESC, total_points DESC, total_assists DESC, p.full_name ASC
            LIMIT 50
        """)
        top_players = cursor.fetchall()

        # 5. Team summaries across the database
        cursor.execute("""
            SELECT t.id, t.name, s.name AS sport_name,
                   COUNT(DISTINCT p.id) AS roster_count,
                   COUNT(DISTINCT m.id) AS match_count
            FROM teams t
            JOIN sports s ON t.sport_id = s.id
            LEFT JOIN players p ON p.team_id = t.id
            LEFT JOIN matches m ON (m.team1_id = t.id OR m.team2_id = t.id)
            GROUP BY t.id, t.name, s.name
            ORDER BY t.name ASC
        """)
        team_summaries = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template(
            'admin/reports.html',
            summary=summary,
            all_tournaments=all_tournaments,
            selected_tournament=selected_tournament,
            standings=standings,
            scoring_info=scoring_info,
            tournament_matches=tournament_matches,
            participating_teams=participating_teams,
            top_players=top_players,
            team_summaries=team_summaries
        )

    except HTTPException:
        raise
    except Exception:
        flash("An error occurred while generating reports.", "error")
        return redirect(url_for('admin_dashboard'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/reports/export/standings', methods=['GET'])
@login_required
@admin_required
def reports_export_standings():
    """
    Exports tournament standings to a CSV file.
    Requires a valid tournament_id parameter.
    """
    tournament_id_raw = request.args.get('tournament_id', '').strip()
    if not tournament_id_raw:
        abort(404)

    try:
        tournament_id = int(tournament_id_raw)
        if tournament_id <= 0:
            abort(404)
    except ValueError:
        abort(404)

    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable.", "error")
        return redirect(url_for('admin_reports'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT t.id, t.name, s.name AS sport_name
            FROM tournaments t
            JOIN sports s ON t.sport_id = s.id
            WHERE t.id = %s
        """, (tournament_id,))
        tournament = cursor.fetchone()
        if not tournament:
            cursor.close()
            conn.close()
            abort(404)

        cursor.execute("""
            SELECT m.id, m.tournament_id, m.status,
                   m.team1_id, t1.name AS team1_name,
                   m.team2_id, t2.name AS team2_name,
                   r.id AS result_id, r.team1_score, r.team2_score, r.winner_team_id
            FROM matches m
            JOIN teams t1 ON m.team1_id = t1.id
            JOIN teams t2 ON m.team2_id = t2.id
            LEFT JOIN results r ON r.match_id = m.id
            WHERE m.tournament_id = %s AND m.status = 'completed' AND r.id IS NOT NULL
        """, (tournament_id,))
        completed_matches = cursor.fetchall()
        cursor.close()
        conn.close()

        standings, scoring_info = calculate_tournament_standings(
            tournament['sport_name'],
            completed_matches
        )

        metric_for = scoring_info.get('metric_for', 'GF')
        metric_against = scoring_info.get('metric_against', 'GA')
        metric_diff = scoring_info.get('metric_diff', 'GD')

        headers = ['Rank', 'Team Name', 'Played', 'Wins', 'Draws', 'Losses', metric_for, metric_against, metric_diff, 'Points']
        rows = [headers]
        for idx, team in enumerate(standings, start=1):
            rows.append([
                idx,
                team['team_name'],
                team['played'],
                team['wins'],
                team['draws'],
                team['losses'],
                team['score_for'],
                team['score_against'],
                team['score_diff'],
                team['points'] if team['points'] is not None else 'N/A'
            ])

        clean_tourn_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in tournament['name']).strip('_')
        filename = f"standings_tournament_{tournament_id}_{clean_tourn_name}.csv"
        return make_safe_csv_response(rows, filename)

    except HTTPException:
        raise
    except Exception:
        flash("Failed to export standings.", "error")
        return redirect(url_for('admin_reports'))
    finally:
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/reports/export/matches', methods=['GET'])
@login_required
@admin_required
def reports_export_matches():
    """
    Exports match schedules and results to a CSV file.
    Accepts optional tournament_id filter.
    """
    tournament_id_raw = request.args.get('tournament_id', '').strip()
    tournament_id = None
    if tournament_id_raw:
        try:
            tournament_id = int(tournament_id_raw)
            if tournament_id <= 0:
                abort(404)
        except ValueError:
            abort(404)

    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable.", "error")
        return redirect(url_for('admin_reports'))

    try:
        cursor = conn.cursor(dictionary=True)

        if tournament_id:
            cursor.execute("SELECT id, name FROM tournaments WHERE id = %s", (tournament_id,))
            tournament = cursor.fetchone()
            if not tournament:
                cursor.close()
                conn.close()
                abort(404)

            cursor.execute("""
                SELECT m.id, tr.name AS tournament_name, m.match_datetime, m.venue, m.status,
                       t1.name AS team1_name, t2.name AS team2_name,
                       r.team1_score, r.team2_score,
                       w.name AS winner_name,
                       CASE WHEN r.id IS NOT NULL THEN 'Yes' ELSE 'No' END AS result_recorded
                FROM matches m
                JOIN tournaments tr ON m.tournament_id = tr.id
                JOIN teams t1 ON m.team1_id = t1.id
                JOIN teams t2 ON m.team2_id = t2.id
                LEFT JOIN results r ON r.match_id = m.id
                LEFT JOIN teams w ON r.winner_team_id = w.id
                WHERE m.tournament_id = %s
                ORDER BY m.match_datetime ASC, m.id ASC
            """, (tournament_id,))
            filename = f"matches_report_tournament_{tournament_id}.csv"
        else:
            cursor.execute("""
                SELECT m.id, tr.name AS tournament_name, m.match_datetime, m.venue, m.status,
                       t1.name AS team1_name, t2.name AS team2_name,
                       r.team1_score, r.team2_score,
                       w.name AS winner_name,
                       CASE WHEN r.id IS NOT NULL THEN 'Yes' ELSE 'No' END AS result_recorded
                FROM matches m
                JOIN tournaments tr ON m.tournament_id = tr.id
                JOIN teams t1 ON m.team1_id = t1.id
                JOIN teams t2 ON m.team2_id = t2.id
                LEFT JOIN results r ON r.match_id = m.id
                LEFT JOIN teams w ON r.winner_team_id = w.id
                ORDER BY m.match_datetime ASC, m.id ASC
            """)
            filename = "matches_report_all.csv"

        matches = cursor.fetchall()
        cursor.close()
        conn.close()

        headers = [
            'Match ID', 'Tournament', 'Date & Time', 'Venue', 'Team 1', 'Team 2',
            'Status', 'Team 1 Score', 'Team 2 Score', 'Winner', 'Result Recorded'
        ]
        rows = [headers]
        for m in matches:
            rows.append([
                m['id'],
                m['tournament_name'],
                str(m['match_datetime']),
                m['venue'] or '',
                m['team1_name'],
                m['team2_name'],
                m['status'],
                m['team1_score'] if m['team1_score'] is not None else '',
                m['team2_score'] if m['team2_score'] is not None else '',
                m['winner_name'] or ('Draw' if m['team1_score'] is not None and m['team1_score'] == m['team2_score'] else ''),
                m['result_recorded']
            ])

        return make_safe_csv_response(rows, filename)

    except HTTPException:
        raise
    except Exception:
        flash("Failed to export matches report.", "error")
        return redirect(url_for('admin_reports'))
    finally:
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/reports/export/players', methods=['GET'])
@login_required
@admin_required
def reports_export_players():
    """
    Exports overall player performance statistics to CSV.
    Excludes sensitive authentication fields (no passwords, emails, or system IDs).
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable.", "error")
        return redirect(url_for('admin_reports'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT p.id, p.full_name, p.jersey_number, s.name AS sport_name,
                   t.name AS team_name,
                   COUNT(DISTINCT pms.match_id) AS matches_played,
                   COALESCE(SUM(pms.goals), 0) AS total_goals,
                   COALESCE(SUM(pms.assists), 0) AS total_assists,
                   COALESCE(SUM(pms.points), 0) AS total_points
            FROM players p
            JOIN sports s ON p.sport_id = s.id
            LEFT JOIN teams t ON p.team_id = t.id
            LEFT JOIN player_match_stats pms ON pms.player_id = p.id
            GROUP BY p.id, p.full_name, p.jersey_number, s.name, t.name
            ORDER BY total_goals DESC, total_points DESC, total_assists DESC, p.full_name ASC
        """)
        players = cursor.fetchall()
        cursor.close()
        conn.close()

        headers = [
            'Player ID', 'Full Name', 'Jersey Number', 'Sport', 'Team',
            'Matches Played', 'Goals', 'Assists', 'Points'
        ]
        rows = [headers]
        for p in players:
            rows.append([
                p['id'],
                p['full_name'],
                p['jersey_number'] if p['jersey_number'] is not None else '',
                p['sport_name'],
                p['team_name'] or 'Unassigned',
                p['matches_played'],
                p['total_goals'],
                p['total_assists'],
                p['total_points']
            ])

        return make_safe_csv_response(rows, "player_statistics_report.csv")

    except HTTPException:
        raise
    except Exception:
        flash("Failed to export player statistics.", "error")
        return redirect(url_for('admin_reports'))
    finally:
        if conn and conn.is_connected():
            conn.close()


@app.route('/admin/reports/export/teams', methods=['GET'])
@login_required
@admin_required
def reports_export_teams():
    """
    Exports team activity summaries to CSV.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database service unavailable.", "error")
        return redirect(url_for('admin_reports'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT t.id, t.name, s.name AS sport_name,
                   COUNT(DISTINCT p.id) AS roster_count,
                   COUNT(DISTINCT m.id) AS match_count
            FROM teams t
            JOIN sports s ON t.sport_id = s.id
            LEFT JOIN players p ON p.team_id = t.id
            LEFT JOIN matches m ON (m.team1_id = t.id OR m.team2_id = t.id)
            GROUP BY t.id, t.name, s.name
            ORDER BY t.name ASC
        """)
        teams = cursor.fetchall()
        cursor.close()
        conn.close()

        headers = ['Team ID', 'Team Name', 'Sport', 'Active Roster Count', 'Scheduled Matches Count']
        rows = [headers]
        for t in teams:
            rows.append([
                t['id'],
                t['name'],
                t['sport_name'],
                t['roster_count'],
                t['match_count']
            ])

        return make_safe_csv_response(rows, "teams_summary_report.csv")

    except HTTPException:
        raise
    except Exception:
        flash("Failed to export teams summary.", "error")
        return redirect(url_for('admin_reports'))
    finally:
        if conn and conn.is_connected():
            conn.close()


# =============================================================================
# Error Handlers
# =============================================================================
@app.errorhandler(400)
def bad_request(e):
    """Custom 400 Bad Request handler (e.g. CSRF validation failure or bad input)."""
    return render_template('auth/400.html', error_description=getattr(e, 'description', None)), 400


@app.errorhandler(403)
def forbidden(e):
    """Custom 403 Forbidden handler."""
    return render_template('auth/403.html'), 403


@app.errorhandler(404)
def not_found(e):
    """Custom 404 Not Found handler."""
    return render_template('auth/404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    """Custom 500 Internal Server Error handler."""
    return render_template('auth/500.html'), 500


# =============================================================================
# Application Entry Point  (local development only)
# =============================================================================
# Production uses: gunicorn app:app
# Debug mode is read from FLASK_ENV. It is NEVER True in production.
if __name__ == '__main__':
    debug_mode = APP_CONFIG.get('env', 'development') != 'production'
    app.run(debug=debug_mode)

