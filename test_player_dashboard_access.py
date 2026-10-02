import re
import unittest
from app import app
from database import get_db_connection
from werkzeug.security import generate_password_hash


class PlayerDashboardAccessTestCase(unittest.TestCase):
    """
    Test suite for investigating and verifying player dashboard access,
    user account creation (/admin/users/create), profile linking,
    role-based redirects, and authorization enforcement.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = cls.app.test_client()
        cls.client.testing = True

        cls.cleanup_test_data()

        # Seed isolated test fixtures: sport, team, admin user, and athlete profile
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)

            # 1. Sport
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_PDA_Basketball', 'Test Sport for Dashboard Access')
            )
            cls.sport_id = cursor.lastrowid

            # 2. Team
            cursor.execute(
                "INSERT INTO teams (name, sport_id) VALUES (%s, %s)",
                ('_TEST_PDA_Lakers', cls.sport_id)
            )
            cls.team_id = cursor.lastrowid

            # 3. Admin user for testing admin actions
            pwd_hash = generate_password_hash('TestAdminPass123!')
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'admin', 1)
                """,
                ('_TEST_pda_admin', '_test_pda_admin@example.com', pwd_hash)
            )
            cls.admin_user_id = cursor.lastrowid

            # 4. Athlete profile (unlinked initially)
            cursor.execute(
                """
                INSERT INTO players (full_name, date_of_birth, gender, sport_id, team_id, jersey_number)
                VALUES (%s, '1998-03-24', 'male', %s, %s, 24)
                """,
                ('_TEST_Athlete_Kobe', cls.sport_id, cls.team_id)
            )
            cls.player_profile_id = cursor.lastrowid

            conn.commit()
            cursor.close()
            conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.cleanup_test_data()

    @classmethod
    def cleanup_test_data(cls):
        """Removes all test-created entities."""
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                # Unlink players first
                cursor.execute("UPDATE players SET user_id = NULL WHERE full_name LIKE '_TEST_%'")
                cursor.execute("DELETE FROM players WHERE full_name LIKE '_TEST_%'")
                cursor.execute("DELETE FROM users WHERE username LIKE '_TEST_%' OR email LIKE '_test_%'")
                cursor.execute("DELETE FROM teams WHERE name LIKE '_TEST_%'")
                cursor.execute("DELETE FROM sports WHERE name LIKE '_TEST_%'")
                conn.commit()
                cursor.close()
            except Exception:
                conn.rollback()
            finally:
                conn.close()

    def setUp(self):
        self.client = self.app.test_client()
        self.client.testing = True

    def set_admin_session(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin_user_id
            sess['username'] = '_TEST_pda_admin'
            sess['role'] = 'admin'

    def set_player_session(self, user_id, username):
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['username'] = username
            sess['role'] = 'player'

    def clear_session(self):
        with self.client.session_transaction() as sess:
            sess.clear()

    def extract_csrf_token(self, path):
        response = self.client.get(path)
        html = response.data.decode('utf-8')
        response.close()
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
        if not match:
            match = re.search(r'value="([^"]+)"\s+name="csrf_token"', html)
        self.assertIsNotNone(match, f"CSRF token not found in response from {path}")
        return match.group(1)

    # -------------------------------------------------------------------------
    # Test 1: Admin can access user create form
    # -------------------------------------------------------------------------
    def test_01_admin_can_access_user_create_form(self):
        self.set_admin_session()
        response = self.client.get('/admin/users/create')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('Create New User Account', html)
        self.assertIn('user-create-form', html)

    # -------------------------------------------------------------------------
    # Test 2: Unauthenticated user accessing /admin/users/create redirects to /login
    # -------------------------------------------------------------------------
    def test_02_unauthenticated_user_create_redirects(self):
        self.clear_session()
        response = self.client.get('/admin/users/create')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers.get('Location', ''))
        response.close()

    # -------------------------------------------------------------------------
    # Test 3: User creation validation errors
    # -------------------------------------------------------------------------
    def test_03_user_create_validation_errors(self):
        self.set_admin_session()
        csrf_token = self.extract_csrf_token('/admin/users/create')

        # Empty fields
        response = self.client.post('/admin/users/create', data={
            'csrf_token': csrf_token,
            'username': '',
            'email': '',
            'role': 'player',
            'password': '',
            'confirm_password': ''
        }, follow_redirects=True)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('Username is required', html)

        # Password mismatch
        response2 = self.client.post('/admin/users/create', data={
            'csrf_token': csrf_token,
            'username': '_TEST_val_user',
            'email': '_test_val@example.com',
            'role': 'player',
            'password': 'Password123!',
            'confirm_password': 'MismatchedPassword!'
        }, follow_redirects=True)
        html2 = response2.data.decode('utf-8')
        response2.close()
        self.assertIn('Passwords do not match', html2)

    # -------------------------------------------------------------------------
    # Test 4: Admin creates a player user account
    # -------------------------------------------------------------------------
    def test_04_admin_creates_player_user_account(self):
        self.set_admin_session()
        csrf_token = self.extract_csrf_token('/admin/users/create')

        response = self.client.post('/admin/users/create', data={
            'csrf_token': csrf_token,
            'username': '_TEST_player_kobe',
            'email': '_test_kobe@example.com',
            'role': 'player',
            'password': 'PlayerPassword123!',
            'confirm_password': 'PlayerPassword123!'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn("created successfully", html)
        self.assertIn('_TEST_player_kobe', html)

        # Verify account in MySQL
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, role, is_active FROM users WHERE username = %s", ('_TEST_player_kobe',))
        user_row = cursor.fetchone()
        cursor.close()
        conn.close()

        self.assertIsNotNone(user_row)
        self.assertEqual(user_row['role'], 'player')
        self.assertEqual(user_row['is_active'], 1)
        PlayerDashboardAccessTestCase.created_player_user_id = user_row['id']

    # -------------------------------------------------------------------------
    # Test 5: Newly created player account appears in Player edit dropdown
    # -------------------------------------------------------------------------
    def test_05_player_appears_in_linking_dropdown(self):
        self.set_admin_session()
        edit_url = f"/admin/players/{self.player_profile_id}/edit"
        response = self.client.get(edit_url)
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('_TEST_player_kobe', html)
        self.assertIn('_test_kobe@example.com', html)

    # -------------------------------------------------------------------------
    # Test 6: Linking player user account to athletic player profile
    # -------------------------------------------------------------------------
    def test_06_link_player_to_athletic_profile(self):
        self.set_admin_session()
        edit_url = f"/admin/players/{self.player_profile_id}/edit"
        csrf_token = self.extract_csrf_token(edit_url)

        response = self.client.post(edit_url, data={
            'csrf_token': csrf_token,
            'full_name': '_TEST_Athlete_Kobe',
            'sport_id': str(self.sport_id),
            'team_id': str(self.team_id),
            'date_of_birth': '1998-03-24',
            'gender': 'male',
            'jersey_number': '24',
            'user_id': str(self.created_player_user_id)
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        response.close()

        # Verify linked in database
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id FROM players WHERE id = %s", (self.player_profile_id,))
        player_row = cursor.fetchone()
        cursor.close()
        conn.close()

        self.assertEqual(player_row['user_id'], self.created_player_user_id)

    # -------------------------------------------------------------------------
    # Test 7: Player login redirects to /player/dashboard
    # -------------------------------------------------------------------------
    def test_07_player_login_redirects_to_player_dashboard(self):
        self.clear_session()
        csrf_token = self.extract_csrf_token('/login')

        response = self.client.post('/login', data={
            'csrf_token': csrf_token,
            'username': '_TEST_player_kobe',
            'password': 'PlayerPassword123!'
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn('/player/dashboard', response.headers.get('Location', ''))
        response.close()

    # -------------------------------------------------------------------------
    # Test 8: Player dashboard renders with linked profile data
    # -------------------------------------------------------------------------
    def test_08_player_dashboard_renders_with_profile_data(self):
        self.set_player_session(self.created_player_user_id, '_TEST_player_kobe')
        response = self.client.get('/player/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()

        self.assertIn('Player Portal', html)
        self.assertIn('_TEST_Athlete_Kobe', html)
        self.assertIn('_TEST_PDA_Basketball', html)
        self.assertIn('_TEST_PDA_Lakers', html)
        self.assertIn('#24', html)

    # -------------------------------------------------------------------------
    # Test 9: Unlinked player account renders graceful informational state
    # -------------------------------------------------------------------------
    def test_09_unlinked_player_renders_graceful_state(self):
        # Create another player user account without linking to an athlete
        conn = get_db_connection()
        cursor = conn.cursor()
        pwd_hash = generate_password_hash('UnlinkedPass123!')
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, role, is_active)
            VALUES (%s, %s, %s, 'player', 1)
            """,
            ('_TEST_unlinked_player', '_test_unlinked_p@example.com', pwd_hash)
        )
        unlinked_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        self.set_player_session(unlinked_id, '_TEST_unlinked_player')
        response = self.client.get('/player/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()

        self.assertIn('Athletic Profile Unlinked', html)
        self.assertIn('administrator has not yet linked', html)

    # -------------------------------------------------------------------------
    # Test 10: Admin accessing player dashboard receives 403 Forbidden
    # -------------------------------------------------------------------------
    def test_10_admin_accessing_player_dashboard_forbidden(self):
        self.set_admin_session()
        response = self.client.get('/player/dashboard')
        self.assertEqual(response.status_code, 403)
        response.close()

    # -------------------------------------------------------------------------
    # Test 11: Unauthenticated visitor accessing player dashboard redirected to /login
    # -------------------------------------------------------------------------
    def test_11_unauthenticated_visitor_redirected(self):
        self.clear_session()
        response = self.client.get('/player/dashboard')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers.get('Location', ''))
        response.close()

    # -------------------------------------------------------------------------
    # Test 12: Player role user cannot access admin routes
    # -------------------------------------------------------------------------
    def test_12_player_cannot_access_admin_routes(self):
        self.set_player_session(self.created_player_user_id, '_TEST_player_kobe')
        response_admin_dash = self.client.get('/admin/dashboard')
        self.assertEqual(response_admin_dash.status_code, 403)
        response_admin_dash.close()

        response_admin_users = self.client.get('/admin/users')
        self.assertEqual(response_admin_users.status_code, 403)
        response_admin_users.close()

        response_create_user = self.client.get('/admin/users/create')
        self.assertEqual(response_create_user.status_code, 403)
        response_create_user.close()


if __name__ == '__main__':
    unittest.main()
