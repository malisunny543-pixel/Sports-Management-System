import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
"""
test_user_experience.py
========================
Dedicated User Experience & Role Verification Test Suite
Sports Management System (SportsPro)

Validates:
1. Public Homepage experience (unauthenticated visitor sees product presentation, live stats, CTAs).
2. Public Homepage experience for logged-in admin (admin console CTA).
3. Public Homepage experience for logged-in player (player portal CTA).
4. Role-based login redirection (/admin/dashboard vs /player/dashboard).
5. Role-based /login bypass when already authenticated.
6. Admin-only navigation isolation (players cannot see admin navbar links).
7. Admin route protection (@admin_required returns 403 for player accounts).
8. Player route protection (@player_required returns 403 for admin accounts).
9. Linked player experience (/player/dashboard with sport, team, stats, fixtures).
10. Unlinked player experience (graceful informational warning).
"""

import unittest
from werkzeug.security import generate_password_hash
from app import app
from database import get_db_connection


class UserExperienceTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.client = cls.app.test_client()

        conn = get_db_connection()
        if conn is None:
            raise RuntimeError("Database service unavailable for UX test suite.")

        cursor = conn.cursor(dictionary=True)
        try:
            # Clean up prior test artifacts if any
            cursor.execute("DELETE FROM player_match_stats WHERE player_id IN (SELECT id FROM players WHERE full_name LIKE '_TEST_UX_%')")
            cursor.execute("DELETE FROM results WHERE match_id IN (SELECT id FROM matches WHERE venue LIKE '_TEST_UX_%')")
            cursor.execute("DELETE FROM matches WHERE venue LIKE '_TEST_UX_%'")
            cursor.execute("DELETE FROM tournaments WHERE name LIKE '_TEST_UX_%'")
            cursor.execute("DELETE FROM players WHERE full_name LIKE '_TEST_UX_%'")
            cursor.execute("DELETE FROM teams WHERE name LIKE '_TEST_UX_%'")
            cursor.execute("DELETE FROM sports WHERE name LIKE '_TEST_UX_%'")
            cursor.execute("DELETE FROM users WHERE username LIKE '_TEST_UX_%'")
            conn.commit()

            pwd_hash = generate_password_hash('Password123!')

            # 1. Admin User
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'admin', 1)
                """,
                ('_TEST_UX_admin', '_test_ux_admin@example.com', pwd_hash)
            )
            cls.admin_user_id = cursor.lastrowid

            # 2. Linked Player User
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 1)
                """,
                ('_TEST_UX_player_linked', '_test_ux_player_linked@example.com', pwd_hash)
            )
            cls.player_linked_user_id = cursor.lastrowid

            # 3. Unlinked Player User
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 1)
                """,
                ('_TEST_UX_player_unlinked', '_test_ux_player_unlinked@example.com', pwd_hash)
            )
            cls.player_unlinked_user_id = cursor.lastrowid

            # 4. Sport & Team
            cursor.execute("INSERT INTO sports (name, description) VALUES ('_TEST_UX_Basketball', 'Basketball League')")
            cls.sport_id = cursor.lastrowid

            cursor.execute("INSERT INTO teams (name, sport_id) VALUES ('_TEST_UX_Warriors', %s)", (cls.sport_id,))
            cls.team_id = cursor.lastrowid

            # 5. Linked Player Profile
            cursor.execute(
                """
                INSERT INTO players (full_name, date_of_birth, gender, sport_id, team_id, jersey_number, user_id)
                VALUES (%s, '2000-05-15', 'male', %s, %s, 30, %s)
                """,
                ('_TEST_UX_Stephen', cls.sport_id, cls.team_id, cls.player_linked_user_id)
            )
            cls.player_id = cursor.lastrowid
            conn.commit()

        finally:
            cursor.close()
            conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.app.config['WTF_CSRF_ENABLED'] = True
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM player_match_stats WHERE player_id IN (SELECT id FROM players WHERE full_name LIKE '_TEST_UX_%')")
                cursor.execute("DELETE FROM results WHERE match_id IN (SELECT id FROM matches WHERE venue LIKE '_TEST_UX_%')")
                cursor.execute("DELETE FROM matches WHERE venue LIKE '_TEST_UX_%'")
                cursor.execute("DELETE FROM tournaments WHERE name LIKE '_TEST_UX_%'")
                cursor.execute("DELETE FROM players WHERE full_name LIKE '_TEST_UX_%'")
                cursor.execute("DELETE FROM teams WHERE name LIKE '_TEST_UX_%'")
                cursor.execute("DELETE FROM sports WHERE name LIKE '_TEST_UX_%'")
                cursor.execute("DELETE FROM users WHERE username LIKE '_TEST_UX_%'")
                conn.commit()
            finally:
                cursor.close()
                conn.close()

    def setUp(self):
        with self.client.session_transaction() as sess:
            sess.clear()

    def set_session(self, user_id, username, role):
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['username'] = username
            sess['role'] = role

    # -------------------------------------------------------------------------
    # Scenario 1: Public Homepage presents SportsPro as a complete platform
    # -------------------------------------------------------------------------
    def test_01_public_homepage_presentation(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # Brand and Product Headings
        self.assertIn('SportsPro', html)
        self.assertIn('Next-Generation Sports Management', html)
        self.assertIn('Modern Leagues', html)

        # Technical Phase 1 demo references removed
        self.assertNotIn('Phase 1 — Foundation', html)
        self.assertNotIn('Flask backend is running successfully', html)
        self.assertNotIn('Development (debug=True)', html)

        # Call-to-actions for unauthenticated visitors
        self.assertIn('Sign In to SportsPro', html)
        self.assertIn('Explore Capabilities', html)
        self.assertIn('btn-hero-signin', html)

        # Metrics display elements
        self.assertIn('id="metric-sports-count"', html)
        self.assertIn('id="metric-tournaments-count"', html)
        self.assertIn('id="metric-teams-count"', html)
        self.assertIn('id="metric-players-count"', html)

        # Capabilities showcase
        self.assertIn('Tournament &amp; Match Scheduling', html)
        self.assertIn('Automated Standings &amp; Points Tables', html)
        self.assertIn('Player Self-Service Portal', html)

        # Access model guidance
        self.assertIn('Account Access &amp; Athlete Onboarding', html)

    # -------------------------------------------------------------------------
    # Scenario 2: Public Homepage for Authenticated Admin
    # -------------------------------------------------------------------------
    def test_02_homepage_authenticated_admin_cta(self):
        self.set_session(self.admin_user_id, '_TEST_UX_admin', 'admin')
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        self.assertIn('btn-hero-admin', html)
        self.assertIn('Open Admin Console', html)
        self.assertIn('btn-hero-reports', html)
        self.assertNotIn('btn-hero-signin', html)

    # -------------------------------------------------------------------------
    # Scenario 3: Public Homepage for Authenticated Player
    # -------------------------------------------------------------------------
    def test_03_homepage_authenticated_player_cta(self):
        self.set_session(self.player_linked_user_id, '_TEST_UX_player_linked', 'player')
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        self.assertIn('btn-hero-player', html)
        self.assertIn('Go to My Player Portal', html)
        self.assertIn('btn-hero-profile', html)
        self.assertNotIn('btn-hero-signin', html)

    # -------------------------------------------------------------------------
    # Scenario 4: Role-based login redirection
    # -------------------------------------------------------------------------
    def test_04_role_based_login_redirections(self):
        # 1. Admin login redirect
        res_admin = self.client.post('/login', data={
            'username': '_TEST_UX_admin',
            'password': 'Password123!'
        }, follow_redirects=False)
        self.assertEqual(res_admin.status_code, 302)
        self.assertEqual(res_admin.headers['Location'], '/admin/dashboard')

        # Clear session
        with self.client.session_transaction() as sess:
            sess.clear()

        # 2. Player login redirect
        res_player = self.client.post('/login', data={
            'username': '_TEST_UX_player_linked',
            'password': 'Password123!'
        }, follow_redirects=False)
        self.assertEqual(res_player.status_code, 302)
        self.assertEqual(res_player.headers['Location'], '/player/dashboard')

    # -------------------------------------------------------------------------
    # Scenario 5: Logged-in user visiting /login redirects to role dashboard
    # -------------------------------------------------------------------------
    def test_05_authenticated_user_accessing_login_redirects(self):
        # Admin visits /login
        self.set_session(self.admin_user_id, '_TEST_UX_admin', 'admin')
        res_admin = self.client.get('/login')
        self.assertEqual(res_admin.status_code, 302)
        self.assertEqual(res_admin.headers['Location'], '/admin/dashboard')

        # Player visits /login
        self.set_session(self.player_linked_user_id, '_TEST_UX_player_linked', 'player')
        res_player = self.client.get('/login')
        self.assertEqual(res_player.status_code, 302)
        self.assertEqual(res_player.headers['Location'], '/player/dashboard')

    # -------------------------------------------------------------------------
    # Scenario 6: Player cannot see admin navigation and cannot access admin routes
    # -------------------------------------------------------------------------
    def test_06_player_isolation_and_admin_block(self):
        self.set_session(self.player_linked_user_id, '_TEST_UX_player_linked', 'player')

        # Check navbar on player dashboard
        res_dash = self.client.get('/player/dashboard')
        self.assertEqual(res_dash.status_code, 200)
        html_dash = res_dash.data.decode('utf-8')

        self.assertIn('nav-player-dashboard', html_dash)
        self.assertIn('nav-player-profile', html_dash)
        self.assertNotIn('nav-admin-dashboard', html_dash)
        self.assertNotIn('nav-admin-users', html_dash)
        self.assertNotIn('nav-admin-reports', html_dash)

        # Attempting admin routes results in 403 Forbidden
        admin_routes = ['/admin/dashboard', '/admin/sports', '/admin/teams', '/admin/users', '/admin/reports']
        for route in admin_routes:
            res_admin_route = self.client.get(route)
            self.assertEqual(res_admin_route.status_code, 403, f"Player was not blocked from {route}")

    # -------------------------------------------------------------------------
    # Scenario 7: Admin cannot access player-only portal routes
    # -------------------------------------------------------------------------
    def test_07_admin_blocked_from_player_portal(self):
        self.set_session(self.admin_user_id, '_TEST_UX_admin', 'admin')

        # Admin attempting player portal receives 403 Forbidden
        res_player_dash = self.client.get('/player/dashboard')
        self.assertEqual(res_player_dash.status_code, 403)

        res_player_prof = self.client.get('/player/profile')
        self.assertEqual(res_player_prof.status_code, 403)

    # -------------------------------------------------------------------------
    # Scenario 8: Linked player experience displays profile, team, and stats
    # -------------------------------------------------------------------------
    def test_08_linked_player_dashboard_experience(self):
        self.set_session(self.player_linked_user_id, '_TEST_UX_player_linked', 'player')
        res = self.client.get('/player/dashboard')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        self.assertIn('_TEST_UX_Stephen', html)
        self.assertIn('_TEST_UX_Basketball', html)
        self.assertIn('_TEST_UX_Warriors', html)
        self.assertIn('#30', html)
        self.assertIn('stat-matches-count', html)
        self.assertIn('stat-goals-count', html)
        self.assertIn('stat-assists-count', html)
        self.assertIn('stat-points-count', html)

    # -------------------------------------------------------------------------
    # Scenario 9: Unlinked player experience displays graceful informational state
    # -------------------------------------------------------------------------
    def test_09_unlinked_player_dashboard_experience(self):
        self.set_session(self.player_unlinked_user_id, '_TEST_UX_player_unlinked', 'player')
        res = self.client.get('/player/dashboard')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        self.assertIn('Athletic Profile Unlinked', html)
        self.assertIn('Your user account is active, but an administrator has not yet linked your account', html)
        self.assertIn('btn-unlinked-profile', html)


if __name__ == '__main__':
    unittest.main()
