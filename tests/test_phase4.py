import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import re
import unittest
from unittest.mock import patch
from app import app


class Phase4AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        self.client.testing = True

    def get_csrf_token(self, path='/login'):
        response = self.client.get(path)
        html = response.data.decode('utf-8')
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
        if not match:
            match = re.search(r'value="([^"]+)"\s+name="csrf_token"', html)
        self.assertIsNotNone(match, f"CSRF token not found in response from {path}")
        return match.group(1)

    def test_01_homepage_renders_and_has_login(self):
        """Verify homepage loads (200 OK) with Sign In button."""
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Sign In', res.data)
        self.assertIn(b'SportsPro', res.data)

    def test_02_db_connection_test_route(self):
        """Verify /health returns 200 with status ok (replaces /db-test)."""
        res = self.client.get('/health')
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertEqual(json_data.get('status'), 'ok')

    def test_03_login_page_renders_with_csrf(self):
        """Verify GET /login returns 200 with valid CSRF token."""
        res = self.client.get('/login')
        self.assertEqual(res.status_code, 200)
        token = self.get_csrf_token('/login')
        self.assertTrue(len(token) > 20)

    def test_04_logout_get_method_not_allowed(self):
        """Verify GET /logout returns 405 Method Not Allowed."""
        res = self.client.get('/logout')
        self.assertEqual(res.status_code, 405)

    def test_05_csrf_protection_on_post_routes(self):
        """Verify POST requests without CSRF token return 400 Bad Request."""
        res_login = self.client.post('/login', data={'username': 'admin', 'password': 'pw'})
        self.assertEqual(res_login.status_code, 400)

        res_logout = self.client.post('/logout')
        self.assertEqual(res_logout.status_code, 400)

    def test_06_unauthenticated_protected_routes_redirect(self):
        """Verify unauthenticated access to protected routes redirects to /login."""
        res_admin = self.client.get('/admin/dashboard')
        self.assertEqual(res_admin.status_code, 302)
        self.assertTrue(res_admin.headers['Location'].endswith('/login'))

        res_player = self.client.get('/player/dashboard')
        self.assertEqual(res_player.status_code, 302)
        self.assertTrue(res_player.headers['Location'].endswith('/login'))

    def test_07_invalid_credentials_generic_message(self):
        """Verify invalid credentials return the generic error message without disclosing user existence."""
        token = self.get_csrf_token('/login')
        res = self.client.post(
            '/login',
            data={
                'csrf_token': token,
                'username': 'non_existent_user_987654',
                'password': 'any_password'
            },
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Invalid username or password. Please try again.', res.data)

    def test_08_empty_fields_validation(self):
        """Verify empty username or password returns input validation message."""
        token = self.get_csrf_token('/login')
        res = self.client.post(
            '/login',
            data={
                'csrf_token': token,
                'username': '',
                'password': ''
            },
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Please enter both username and password.', res.data)

    @patch('auth.get_current_user')
    def test_09_admin_dashboard_access_by_admin(self, mock_get_user):
        """Verify authenticated admin can access /admin/dashboard."""
        mock_get_user.return_value = {
            'id': 1,
            'username': 'superadmin',
            'email': 'admin@example.com',
            'role': 'admin',
            'is_active': 1
        }
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'superadmin'
            sess['role'] = 'admin'

        res = self.client.get('/admin/dashboard')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Welcome, superadmin', res.data)
        self.assertIn(b'Administrator Console', res.data)

    @patch('auth.get_current_user')
    def test_10_player_accessing_admin_dashboard_returns_403(self, mock_get_user):
        """Verify authenticated player accessing /admin/dashboard receives 403 Forbidden."""
        mock_get_user.return_value = {
            'id': 2,
            'username': 'striker09',
            'email': 'striker@example.com',
            'role': 'player',
            'is_active': 1
        }
        with self.client.session_transaction() as sess:
            sess['user_id'] = 2
            sess['username'] = 'striker09'
            sess['role'] = 'player'

        res = self.client.get('/admin/dashboard')
        self.assertEqual(res.status_code, 403)
        self.assertIn(b'403 Forbidden', res.data)
        self.assertIn(b'You do not have administrative privileges', res.data)

    @patch('auth.get_current_user')
    def test_11_player_accessing_player_dashboard(self, mock_get_user):
        """Verify authenticated player can access /player/dashboard."""
        mock_get_user.return_value = {
            'id': 2,
            'username': 'striker09',
            'email': 'striker@example.com',
            'role': 'player',
            'is_active': 1
        }
        with self.client.session_transaction() as sess:
            sess['user_id'] = 2
            sess['username'] = 'striker09'
            sess['role'] = 'player'

        res = self.client.get('/player/dashboard')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Welcome, striker09', res.data)
        self.assertIn(b'Player Portal', res.data)

    @patch('auth.get_current_user')
    def test_12_deactivated_account_mid_session_revocation(self, mock_get_user):
        """Verify that if is_active becomes 0 mid-session, access is revoked immediately."""
        # Database verification returns None because account was disabled or deleted
        mock_get_user.return_value = None

        with self.client.session_transaction() as sess:
            sess['user_id'] = 3
            sess['username'] = 'disabled_user'
            sess['role'] = 'admin'

        res = self.client.get('/admin/dashboard', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Your session has expired. Please log in again.', res.data)

    def test_13_post_logout_clears_session_and_redirects(self):
        """Verify POST /logout with CSRF token clears session and redirects to /login."""
        token = self.get_csrf_token('/login')
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'

        res = self.client.post('/logout', data={'csrf_token': token}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'You have been signed out.', res.data)
        # Verify session is empty
        with self.client.session_transaction() as sess:
            self.assertNotIn('user_id', sess)


if __name__ == '__main__':
    unittest.main()
