import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# =============================================================================
# test_phase_10_security.py — Phase 10 Comprehensive Security Audit Test Suite
# =============================================================================
import unittest
from werkzeug.security import generate_password_hash

from app import app, make_safe_csv_response
from database import get_db_connection


class Phase10SecurityTestCase(unittest.TestCase):
    """
    Comprehensive Security Audit & Hardening Test Suite for SportsPro.
    Verifies HTTP security headers, authentication & authorization boundaries,
    privilege escalation defense, CSRF mitigation, SQLi & XSS protection,
    CSV formula injection defense, account linking integrity, and safe error handling.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.original_csrf_config = cls.app.config.get('WTF_CSRF_ENABLED', True)

        # Clean up any leftover test data
        cls.cleanup_test_data()

        # Seed isolated test records
        conn = get_db_connection()
        assert conn is not None, "Database connection failed during test setup"
        try:
            cursor = conn.cursor(dictionary=True)

            # 1. Test Sport
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_SEC_Sport', 'Test Sport for Security Audit')
            )
            cls.sport_id = cursor.lastrowid

            # 2. Test Team
            cursor.execute(
                "INSERT INTO teams (name, sport_id) VALUES (%s, %s)",
                ('_TEST_SEC_Team', cls.sport_id)
            )
            cls.team_id = cursor.lastrowid

            pwd_hash = generate_password_hash('SecAuditPass123!')

            # 3. Active Admin User
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'admin', 1)
                """,
                ('_TEST_sec_admin', '_test_sec_admin@example.com', pwd_hash)
            )
            cls.admin_user_id = cursor.lastrowid

            # 4. Active Player User
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 1)
                """,
                ('_TEST_sec_player1', '_test_sec_player1@example.com', pwd_hash)
            )
            cls.player_user_id1 = cursor.lastrowid

            # 5. Second Active Player User (for 1-to-1 linking tests)
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 1)
                """,
                ('_TEST_sec_player2', '_test_sec_player2@example.com', pwd_hash)
            )
            cls.player_user_id2 = cursor.lastrowid

            # 6. Inactive Player User
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 0)
                """,
                ('_TEST_sec_inactive', '_test_sec_inactive@example.com', pwd_hash)
            )
            cls.inactive_user_id = cursor.lastrowid

            # 7. Athlete Profile linked to player 1
            cursor.execute(
                """
                INSERT INTO players (full_name, sport_id, team_id, jersey_number, user_id)
                VALUES (%s, %s, %s, %s, %s)
                """,
                ('_TEST_Alice SecPlayer', cls.sport_id, cls.team_id, 10, cls.player_user_id1)
            )
            cls.player_profile_id1 = cursor.lastrowid

            # 8. Athlete Profile without linked user
            cursor.execute(
                """
                INSERT INTO players (full_name, sport_id, team_id, jersey_number, user_id)
                VALUES (%s, %s, %s, %s, NULL)
                """,
                ('_TEST_Bob Unlinked', cls.sport_id, cls.team_id, 20)
            )
            cls.player_profile_id2 = cursor.lastrowid

            conn.commit()
            cursor.close()
        finally:
            if conn and conn.is_connected():
                conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.cleanup_test_data()
        cls.app.config['WTF_CSRF_ENABLED'] = cls.original_csrf_config

    @classmethod
    def cleanup_test_data(cls):
        conn = get_db_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            # Clean test players
            cursor.execute("UPDATE players SET user_id = NULL WHERE full_name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM players WHERE full_name LIKE '_TEST_%'")
            # Clean test teams
            cursor.execute("DELETE FROM teams WHERE name LIKE '_TEST_%'")
            # Clean test sports
            cursor.execute("DELETE FROM sports WHERE name LIKE '_TEST_%'")
            # Clean test users
            cursor.execute("DELETE FROM users WHERE username LIKE '_TEST_%' OR email LIKE '_test_%'")
            conn.commit()
            cursor.close()
        finally:
            if conn and conn.is_connected():
                conn.close()

    def setUp(self):
        # Create fresh isolated test client for each test method
        self.client = self.app.test_client()
        self.app.config['WTF_CSRF_ENABLED'] = False

    def tearDown(self):
        self.app.config['WTF_CSRF_ENABLED'] = False

    # -------------------------------------------------------------------------
    # 1. HTTP Security Headers
    # -------------------------------------------------------------------------
    def test_security_headers_present_on_standard_response(self):
        """Verify defensive HTTP security headers are injected into standard responses."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(response.headers.get('X-Frame-Options'), 'SAMEORIGIN')
        self.assertEqual(response.headers.get('X-XSS-Protection'), '1; mode=block')
        self.assertEqual(response.headers.get('Referrer-Policy'), 'strict-origin-when-cross-origin')

    def test_security_headers_present_on_error_responses(self):
        """Verify defensive headers are also included on 404 and 403 responses."""
        res_404 = self.client.get('/nonexistent-route-for-security-check')
        self.assertEqual(res_404.status_code, 404)
        self.assertEqual(res_404.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(res_404.headers.get('X-Frame-Options'), 'SAMEORIGIN')

    # -------------------------------------------------------------------------
    # 2. Authentication & Authorization Boundaries
    # -------------------------------------------------------------------------
    def test_unauthenticated_protected_routes_redirect_to_login(self):
        """Verify unauthenticated users cannot access admin or player protected routes."""
        protected_routes = [
            '/admin/dashboard',
            '/admin/users',
            '/admin/reports',
            '/admin/sports',
            '/admin/tournaments',
            '/player/dashboard',
            '/player/profile'
        ]
        for route in protected_routes:
            with self.subTest(route=route):
                response = self.client.get(route, follow_redirects=False)
                self.assertEqual(response.status_code, 302, f"Route {route} did not redirect unauthenticated user")
                self.assertIn('/login', response.location)

    def test_player_role_cannot_access_admin_routes(self):
        """Verify users with player role receive 403 Forbidden on all admin-only routes."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.player_user_id1
            sess['username'] = '_TEST_sec_player1'
            sess['role'] = 'player'

        admin_routes = [
            '/admin/dashboard',
            '/admin/users',
            '/admin/reports',
            '/admin/sports/new',
            '/admin/teams/new',
            '/admin/players/new',
            '/admin/tournaments/new'
        ]
        for route in admin_routes:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 403, f"Player accessed admin route: {route}")
                self.assertIn(b"403 Forbidden", response.data)

    def test_admin_role_cannot_access_player_routes(self):
        """Verify users with admin role receive 403 Forbidden on player-specific portal routes."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin_user_id
            sess['username'] = '_TEST_sec_admin'
            sess['role'] = 'admin'

        player_routes = [
            '/player/dashboard',
            '/player/profile'
        ]
        for route in player_routes:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 403, f"Admin was allowed into player route: {route}")
                self.assertIn(b"403 Forbidden", response.data)

    # -------------------------------------------------------------------------
    # 3. Account Status & Session Lifetime Security
    # -------------------------------------------------------------------------
    def test_inactive_account_cannot_authenticate(self):
        """Verify inactive accounts are prevented from logging in."""
        response = self.client.post('/login', data={
            'username': '_TEST_sec_inactive',
            'password': 'SecAuditPass123!'
        }, follow_redirects=True)

        self.assertIn(b"inactive", response.data.lower())
        # Confirm no active session was established
        with self.client.session_transaction() as sess:
            self.assertNotIn('user_id', sess)

    def test_mid_session_account_deactivation(self):
        """Verify a user deactivated in the database mid-session is immediately revoked."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.player_user_id2
            sess['username'] = '_TEST_sec_player2'
            sess['role'] = 'player'

        # Deactivate player 2 in database
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_active = 0 WHERE id = %s", (self.player_user_id2,))
            conn.commit()
            cursor.close()
        finally:
            if conn and conn.is_connected():
                conn.close()

        # Subsequent request should immediately detect is_active == 0, clear session, and redirect to /login
        response = self.client.get('/player/dashboard', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.location)

        with self.client.session_transaction() as sess:
            self.assertNotIn('user_id', sess)

        # Restore player 2 to active status
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_active = 1 WHERE id = %s", (self.player_user_id2,))
            conn.commit()
            cursor.close()
        finally:
            if conn and conn.is_connected():
                conn.close()

    # -------------------------------------------------------------------------
    # 4. Privilege Escalation Defense on Registration & Profile Editing
    # -------------------------------------------------------------------------
    def test_public_registration_privilege_escalation_blocked(self):
        """Verify submitting role='admin' in public registration still creates player role."""
        response = self.client.post('/register', data={
            'username': '_TEST_sec_attacker',
            'email': '_test_sec_attacker@example.com',
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!',
            'role': 'admin'  # Attacker attempt
        }, follow_redirects=False)

        # Registration redirects to /login with success message
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.location)

        # Verify database record role is strictly 'player'
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT role FROM users WHERE username = %s", ('_TEST_sec_attacker',))
            user = cursor.fetchone()
            cursor.close()
            self.assertIsNotNone(user)
            self.assertEqual(user['role'], 'player')
        finally:
            if conn and conn.is_connected():
                conn.close()

    def test_public_registration_duplicate_username_and_email_rejection(self):
        """Verify registration rejects duplicate username and duplicate email."""
        # Duplicate username
        res1 = self.client.post('/register', data={
            'username': '_TEST_sec_admin',
            'email': '_test_sec_unique_mail@example.com',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        }, follow_redirects=True)
        self.assertIn(b"already taken", res1.data)

        # Duplicate email
        res2 = self.client.post('/register', data={
            'username': '_TEST_sec_unique_user',
            'email': '_test_sec_admin@example.com',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        }, follow_redirects=True)
        self.assertIn(b"already registered", res2.data)

    def test_player_profile_editing_cannot_alter_role_or_tamper_user_id(self):
        """Verify self-service profile update cannot alter role or user_id."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.player_user_id1
            sess['username'] = '_TEST_sec_player1'
            sess['role'] = 'player'

        # Attempt to POST modified role and user_id via profile form
        response = self.client.post('/player/profile', data={
            'email': '_test_sec_player1_updated@example.com',
            'full_name': '_TEST_Alice Modified',
            'role': 'admin',               # Malicious tamper attempt
            'user_id': str(self.admin_user_id)  # Malicious tamper attempt
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)

        # Verify user role is intact and player record is still bound to player_user_id1
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT role, email FROM users WHERE id = %s", (self.player_user_id1,))
            user = cursor.fetchone()
            self.assertEqual(user['role'], 'player')
            self.assertEqual(user['email'], '_test_sec_player1_updated@example.com')

            cursor.execute("SELECT user_id, full_name FROM players WHERE id = %s", (self.player_profile_id1,))
            p = cursor.fetchone()
            self.assertEqual(p['user_id'], self.player_user_id1)
            self.assertEqual(p['full_name'], '_TEST_Alice Modified')
            cursor.close()
        finally:
            if conn and conn.is_connected():
                conn.close()

    # -------------------------------------------------------------------------
    # 5. Account Linking Security & Isolation
    # -------------------------------------------------------------------------
    def test_admin_cannot_link_admin_user_to_player_profile(self):
        """Verify admin user accounts cannot be assigned to athlete profiles."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin_user_id
            sess['username'] = '_TEST_sec_admin'
            sess['role'] = 'admin'

        # Attempt to link admin account to unlinked player profile 2
        response = self.client.post(f'/admin/players/{self.player_profile_id2}/edit', data={
            'full_name': '_TEST_Bob Unlinked',
            'sport_id': str(self.sport_id),
            'team_id': str(self.team_id),
            'jersey_number': '20',
            'user_id': str(self.admin_user_id)  # Admin user ID attempted
        }, follow_redirects=True)

        self.assertIn(b"not a valid player user account", response.data)

        # Verify player record user_id remains NULL
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT user_id FROM players WHERE id = %s", (self.player_profile_id2,))
            p = cursor.fetchone()
            cursor.close()
            self.assertIsNone(p['user_id'])
        finally:
            if conn and conn.is_connected():
                conn.close()

    def test_account_linking_prevents_duplicate_assignment(self):
        """Verify one player user cannot be linked to multiple athlete profiles."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin_user_id
            sess['username'] = '_TEST_sec_admin'
            sess['role'] = 'admin'

        # player_user_id1 is already linked to player_profile_id1
        # Attempt to link player_user_id1 to player_profile_id2
        response = self.client.post(f'/admin/players/{self.player_profile_id2}/edit', data={
            'full_name': '_TEST_Bob Unlinked',
            'sport_id': str(self.sport_id),
            'team_id': str(self.team_id),
            'jersey_number': '20',
            'user_id': str(self.player_user_id1)  # Already assigned to Alice
        }, follow_redirects=True)

        self.assertIn(b"already linked to another player", response.data)

        # Verify player 2 remains unlinked
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT user_id FROM players WHERE id = %s", (self.player_profile_id2,))
            p = cursor.fetchone()
            cursor.close()
            self.assertIsNone(p['user_id'])
        finally:
            if conn and conn.is_connected():
                conn.close()

    # -------------------------------------------------------------------------
    # 6. CSRF Protection
    # -------------------------------------------------------------------------
    def test_csrf_protection_rejects_missing_token_on_post(self):
        """Verify state-changing POST without CSRF token returns 400 Bad Request."""
        self.app.config['WTF_CSRF_ENABLED'] = True
        try:
            response = self.client.post('/login', data={
                'username': '_TEST_sec_admin',
                'password': 'SecAuditPass123!'
            })
            self.assertEqual(response.status_code, 400)
            self.assertIn(b"400 Bad Request", response.data)
            self.assertIn(b"CSRF", response.data)
        finally:
            self.app.config['WTF_CSRF_ENABLED'] = False

    # -------------------------------------------------------------------------
    # 7. CSV Formula Injection Defense
    # -------------------------------------------------------------------------
    def test_csv_formula_injection_defense(self):
        """Verify CSV streaming prefixes formula-triggering characters with a single quote."""
        malicious_rows = [
            ['ID', 'Name', 'Description'],
            [1, '=SUM(A1:A10)', 'Formula payload 1'],
            [2, '+cmd|"/C calc"!A0', 'Formula payload 2'],
            [3, '-cmd|"/C notepad"!A0', 'Formula payload 3'],
            [4, '@HYPERLINK("http://evil.com")', 'Formula payload 4'],
            [5, '\tTAB_COMMAND', 'Tab payload'],
            [6, '%PERCENT_CMD', 'Percent payload'],
            [7, 'Safe Athlete Name', 'Normal entry']
        ]

        csv_response = make_safe_csv_response(malicious_rows, 'test_export.csv')
        csv_text = csv_response.get_data(as_text=True)

        # Check that dangerous triggers have been single-quote neutralized
        self.assertIn("'=SUM(A1:A10)", csv_text)
        self.assertIn("'+cmd|", csv_text)
        self.assertIn("'-cmd|", csv_text)
        self.assertIn("'@HYPERLINK", csv_text)
        self.assertIn("'\tTAB_COMMAND", csv_text)
        self.assertIn("'%PERCENT_CMD", csv_text)
        # Check safe value is untouched
        self.assertIn("Safe Athlete Name", csv_text)

    # -------------------------------------------------------------------------
    # 8. SQL Injection & XSS Defense
    # -------------------------------------------------------------------------
    def test_sql_injection_defense_in_url_and_lookup_parameters(self):
        """Verify malformed IDs and SQL injection attempts in routes return 404 cleanly."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin_user_id
            sess['username'] = '_TEST_sec_admin'
            sess['role'] = 'admin'

        sqli_paths = [
            "/admin/sports/999999/edit",
            "/admin/sports/1' OR '1'='1/edit",
            "/admin/players/1; DROP TABLE users;--/edit",
            "/admin/teams/invalid-id-string/edit"
        ]
        for path in sqli_paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                # Should return 404 without unhandled 500 error or database syntax crash
                self.assertEqual(response.status_code, 404, f"SQLi probe on {path} returned {response.status_code}")

    def test_xss_autoescaping_in_templates(self):
        """Verify stored strings with HTML/script characters are properly escaped in output."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin_user_id
            sess['username'] = '_TEST_sec_admin'
            sess['role'] = 'admin'

        xss_sport_name = "_TEST_SEC_<script>alert('xss')</script>"
        res = self.client.post('/admin/sports/new', data={
            'name': xss_sport_name,
            'description': 'XSS Test Sport'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        # Raw unescaped script tag should NEVER be present in the HTML output
        self.assertNotIn(b"<script>alert('xss')</script>", res.data)
        # Escaped entity should be present
        self.assertIn(b"&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;", res.data)

    # -------------------------------------------------------------------------
    # 9. Information Disclosure Defense
    # -------------------------------------------------------------------------
    def test_db_test_does_not_leak_passwords_or_raw_traceback(self):
        """Verify /db-test endpoint does not expose sensitive credentials."""
        response = self.client.get('/db-test')
        text = response.get_data(as_text=True)

        # Check for absence of passwords or secret key
        self.assertNotIn('password', text.lower())
        self.assertNotIn(app.config['SECRET_KEY'], text)


if __name__ == '__main__':
    unittest.main()
