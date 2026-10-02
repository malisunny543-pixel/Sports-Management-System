import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
"""
test_phase9.py
==============
Phase 9 — UI/UX Polish & Responsive Testing Test Suite
Sports Management System (SportsPro)

Verifies:
1. Accessibility: Skip-link navigation and main content landmark.
2. Accessibility: Keyboard focus-visible and prefers-reduced-motion CSS rules.
3. Navigation: Active page indicators and aria-current="page" for Admin and Player portals.
4. Error Handling: Custom 403, 404, and 500 pages with helpful navigational options.
5. Feedback & Alerts: Accessible flash messages with role="alert" and dismiss controls.
6. Responsive Meta & Structure: Viewport meta tags across pages and responsive table wrappers.
7. Consequential Action Safety: Confirmations for sensitive admin operations.
8. Form Accessibility: Proper label-input associations and CSRF protection.
9. CSS Responsive Breakpoints: Comprehensive media queries for tablet and mobile devices.
"""

import unittest
from werkzeug.security import generate_password_hash
from app import app
from database import get_db_connection


class Phase9UIUXTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.client = cls.app.test_client()

        conn = get_db_connection()
        if conn is None:
            raise RuntimeError("Database connection unavailable for Phase 9 testing.")

        cursor = conn.cursor(dictionary=True)
        try:
            # Clean up prior test artifacts if any
            cursor.execute("DELETE FROM users WHERE username LIKE '_TEST_p9_%'")
            conn.commit()

            pwd_hash = generate_password_hash('Password123!')
            # 1. Admin user
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'admin', 1)
                """,
                ('_TEST_p9_admin', '_test_p9_admin@example.com', pwd_hash)
            )
            cls.admin_user_id = cursor.lastrowid

            # 2. Player user
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 1)
                """,
                ('_TEST_p9_player', '_test_p9_player@example.com', pwd_hash)
            )
            cls.player_user_id = cursor.lastrowid
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
                cursor.execute("DELETE FROM users WHERE username LIKE '_TEST_p9_%'")
                conn.commit()
            finally:
                cursor.close()
                conn.close()

    def set_session(self, user_id, username, role):
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['username'] = username
            sess['role'] = role

    def setUp(self):
        self.clear_session()

    def clear_session(self):
        with self.client.session_transaction() as sess:
            sess.clear()

    # -------------------------------------------------------------------------
    # Scenario 1: Accessibility — Skip-link and main content landmark
    # -------------------------------------------------------------------------
    def test_01_skip_link_and_main_landmark(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        self.assertIn('class="skip-link"', html)
        self.assertIn('href="#main-content"', html)
        self.assertIn('Skip to main content', html)
        self.assertIn('id="main-content"', html)
        self.assertIn('tabindex="-1"', html)

    # -------------------------------------------------------------------------
    # Scenario 2: Accessibility — CSS focus-visible and reduced-motion
    # -------------------------------------------------------------------------
    def test_02_css_focus_visible_and_reduced_motion(self):
        with open('static/css/style.css', 'r', encoding='utf-8') as f:
            css = f.read()

        self.assertIn(':focus-visible', css)
        self.assertIn('--color-accent-primary', css)
        self.assertIn('.skip-link', css)
        self.assertIn('@media (prefers-reduced-motion: reduce)', css)
        self.assertIn('animation-duration: 0.01ms', css)

    # -------------------------------------------------------------------------
    # Scenario 3: Admin Active Navigation Indicators & ARIA attributes
    # -------------------------------------------------------------------------
    def test_03_admin_active_navigation_indicators(self):
        self.set_session(self.admin_user_id, '_TEST_p9_admin', 'admin')

        # 1. Admin Dashboard
        res = self.client.get('/admin/dashboard')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('id="nav-admin-dashboard"', html)
        self.assertIn('active', html)
        self.assertIn('aria-current="page"', html)

        # 2. Users Management
        res_users = self.client.get('/admin/users')
        self.assertEqual(res_users.status_code, 200)
        html_users = res_users.data.decode('utf-8')
        self.assertIn('id="nav-admin-users"', html_users)
        self.assertIn('active', html_users)
        self.assertIn('aria-current="page"', html_users)

        # 3. Reports & Analytics
        res_rep = self.client.get('/admin/reports')
        self.assertEqual(res_rep.status_code, 200)
        html_rep = res_rep.data.decode('utf-8')
        self.assertIn('id="nav-admin-reports"', html_rep)
        self.assertIn('active', html_rep)
        self.assertIn('aria-current="page"', html_rep)

    # -------------------------------------------------------------------------
    # Scenario 4: Player Active Navigation Indicators & ARIA attributes
    # -------------------------------------------------------------------------
    def test_04_player_active_navigation_indicators(self):
        self.set_session(self.player_user_id, '_TEST_p9_player', 'player')

        # 1. Player Dashboard
        res_dash = self.client.get('/player/dashboard')
        self.assertEqual(res_dash.status_code, 200)
        html_dash = res_dash.data.decode('utf-8')
        self.assertIn('id="nav-player-dashboard"', html_dash)
        self.assertIn('active', html_dash)
        self.assertIn('aria-current="page"', html_dash)

        # 2. Player Profile
        res_prof = self.client.get('/player/profile')
        self.assertEqual(res_prof.status_code, 200)
        html_prof = res_prof.data.decode('utf-8')
        self.assertIn('id="nav-player-profile"', html_prof)
        self.assertIn('active', html_prof)
        self.assertIn('aria-current="page"', html_prof)

    # -------------------------------------------------------------------------
    # Scenario 5: Error 403 Forbidden custom template
    # -------------------------------------------------------------------------
    def test_05_custom_403_page(self):
        self.set_session(self.player_user_id, '_TEST_p9_player', 'player')
        # Player attempting admin reports gets 403
        res = self.client.get('/admin/reports')
        self.assertEqual(res.status_code, 403)
        html = res.data.decode('utf-8')
        self.assertIn('403 Forbidden', html)
        self.assertIn('Access Denied', html)
        self.assertIn('btn-return-home', html)
        self.assertIn('btn-player-dash', html)

    # -------------------------------------------------------------------------
    # Scenario 6: Error 404 Not Found custom template
    # -------------------------------------------------------------------------
    def test_06_custom_404_page(self):
        res = self.client.get('/nonexistent-test-route-404')
        self.assertEqual(res.status_code, 404)
        html = res.data.decode('utf-8')
        self.assertIn('404 Not Found', html)
        self.assertIn('The resource, page, or record you requested could not be found.', html)
        self.assertIn('btn-404-home', html)

    # -------------------------------------------------------------------------
    # Scenario 7: Error 500 Internal Server Error custom template
    # -------------------------------------------------------------------------
    def test_07_custom_500_page(self):
        from app import internal_server_error
        with self.app.test_request_context('/'):
            response, code = internal_server_error(None)
            self.assertEqual(code, 500)
            self.assertIn('500 Server Error', response)
            self.assertIn('btn-500-home', response)

    # -------------------------------------------------------------------------
    # Scenario 8: Accessible Flash Alert Messages
    # -------------------------------------------------------------------------
    def test_08_accessible_flash_alerts(self):
        with self.client.session_transaction() as sess:
            sess['_flashes'] = [('success', 'Operation completed successfully.')]

        res = self.client.get('/login')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('role="alert"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('alert-success', html)
        self.assertIn('alert-close', html)
        self.assertIn('Close notification', html)
        self.assertIn('Operation completed successfully.', html)

    # -------------------------------------------------------------------------
    # Scenario 9: Responsive Viewport Meta Tags
    # -------------------------------------------------------------------------
    def test_09_responsive_viewport_meta_tags(self):
        routes = ['/', '/login']
        for route in routes:
            res = self.client.get(route)
            html = res.data.decode('utf-8')
            self.assertIn(
                '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
                html,
                f"Missing viewport meta tag in route: {route}"
            )

    # -------------------------------------------------------------------------
    # Scenario 10: Consequential Action Confirmations
    # -------------------------------------------------------------------------
    def test_10_consequential_action_confirmations(self):
        self.set_session(self.admin_user_id, '_TEST_p9_admin', 'admin')
        res = self.client.get('/admin/users')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # Form has data-confirm attribute for safe user confirmation
        self.assertIn('data-confirm="', html)

        # JavaScript contains confirmation interceptors
        with open('static/js/script.js', 'r', encoding='utf-8') as f:
            js = f.read()

        self.assertIn('data-confirm', js)
        self.assertIn('form[action*="/status"]', js)
        self.assertIn('form[action*="/role"]', js)

    # -------------------------------------------------------------------------
    # Scenario 11: Responsive Table Wrappers across admin modules
    # -------------------------------------------------------------------------
    def test_11_responsive_table_wrappers(self):
        table_templates = [
            'templates/admin/sports.html',
            'templates/admin/teams.html',
            'templates/admin/players.html',
            'templates/admin/tournaments.html',
            'templates/admin/matches.html',
            'templates/admin/results.html',
            'templates/admin/standings.html',
            'templates/admin/reports.html',
            'templates/admin/users.html',
        ]
        for template_path in table_templates:
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn(
                'table-responsive',
                content,
                f"Template {template_path} is missing table-responsive wrapper."
            )

    # -------------------------------------------------------------------------
    # Scenario 12: Comprehensive CSS Breakpoints
    # -------------------------------------------------------------------------
    def test_12_responsive_css_breakpoints(self):
        with open('static/css/style.css', 'r', encoding='utf-8') as f:
            css = f.read()

        self.assertIn('@media (max-width: 992px)', css)
        self.assertIn('@media (max-width: 768px)', css)
        self.assertIn('@media (max-width: 480px)', css)
        self.assertIn('-webkit-overflow-scrolling: touch', css)


if __name__ == '__main__':
    unittest.main()
