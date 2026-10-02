import re
import unittest
from app import app
from database import get_db_connection
from werkzeug.security import generate_password_hash, check_password_hash


class PlayerRegistrationTestCase(unittest.TestCase):
    """
    Test suite for public player registration, role enforcement,
    login redirection, profile linking, and authorization boundaries.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = cls.app.test_client()
        cls.client.testing = True

        cls.cleanup_test_data()

        # Seed isolated test sport, team, admin user, and athlete profile
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)

            # 1. Sport
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_REG_Cricket', 'Test Sport for Registration')
            )
            cls.sport_id = cursor.lastrowid

            # 2. Team
            cursor.execute(
                "INSERT INTO teams (name, sport_id) VALUES (%s, %s)",
                ('_TEST_REG_Warriors', cls.sport_id)
            )
            cls.team_id = cursor.lastrowid

            # 3. Admin user
            pwd_hash = generate_password_hash('TestAdminPass123!')
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'admin', 1)
                """,
                ('_TEST_reg_admin', '_test_reg_admin@example.com', pwd_hash)
            )
            cls.admin_user_id = cursor.lastrowid

            # 4. Existing Player user for session tests
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 1)
                """,
                ('_TEST_reg_player_exist', '_test_reg_exist@example.com', pwd_hash)
            )
            cls.player_user_id = cursor.lastrowid

            # 5. Athlete profile
            cursor.execute(
                """
                INSERT INTO players (full_name, date_of_birth, gender, sport_id, team_id, jersey_number)
                VALUES (%s, '2000-01-01', 'male', %s, %s, 18)
                """,
                ('_TEST_Athlete_Virat', cls.sport_id, cls.team_id)
            )
            cls.athlete_profile_id = cursor.lastrowid

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
            sess['username'] = '_TEST_reg_admin'
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

    # =========================================================================
    # 1. Registration Page Rendering & Session Redirects
    # =========================================================================
    def test_01_registration_page_loads(self):
        self.clear_session()
        response = self.client.get('/register')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('Create Player Account', html)
        self.assertIn('register-form', html)
        self.assertIn('csrf_token', html)

    def test_02_authenticated_admin_visiting_register_redirects(self):
        self.set_admin_session()
        response = self.client.get('/register')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/dashboard', response.headers.get('Location', ''))
        response.close()

    def test_03_authenticated_player_visiting_register_redirects(self):
        self.set_player_session(self.player_user_id, '_TEST_reg_player_exist')
        response = self.client.get('/register')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/player/dashboard', response.headers.get('Location', ''))
        response.close()

    # =========================================================================
    # 2. Form Validation & CSRF Protection
    # =========================================================================
    def test_04_registration_missing_fields_validation(self):
        self.clear_session()
        csrf_token = self.extract_csrf_token('/register')

        # Missing username
        response = self.client.post('/register', data={
            'csrf_token': csrf_token,
            'username': '',
            'email': '_test_valid@example.com',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        }, follow_redirects=True)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('Username is required', html)

        # Missing email
        response = self.client.post('/register', data={
            'csrf_token': csrf_token,
            'username': '_TEST_usr1',
            'email': '',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        }, follow_redirects=True)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('Email address is required', html)

        # Invalid email format
        response = self.client.post('/register', data={
            'csrf_token': csrf_token,
            'username': '_TEST_usr2',
            'email': 'not-an-email',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        }, follow_redirects=True)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('Please enter a valid email address', html)

        # Short password (< 8 chars)
        response = self.client.post('/register', data={
            'csrf_token': csrf_token,
            'username': '_TEST_usr3',
            'email': '_test_usr3@example.com',
            'password': 'short',
            'confirm_password': 'short'
        }, follow_redirects=True)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('Password must be at least 8 characters long', html)

        # Password mismatch
        response = self.client.post('/register', data={
            'csrf_token': csrf_token,
            'username': '_TEST_usr4',
            'email': '_test_usr4@example.com',
            'password': 'Password123!',
            'confirm_password': 'DifferentPassword123!'
        }, follow_redirects=True)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('Passwords do not match', html)

    def test_05_csrf_protection_enforced_on_registration(self):
        self.app.config['WTF_CSRF_ENABLED'] = True
        self.clear_session()
        # Post with no CSRF token
        response = self.client.post('/register', data={
            'username': '_TEST_no_csrf',
            'email': '_test_nocsrf@example.com',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        })
        self.assertEqual(response.status_code, 400)
        response.close()

    # =========================================================================
    # 3. Successful Registration & Role Enforcement (Never Admin)
    # =========================================================================
    def test_06_valid_registration_creates_player_account(self):
        self.clear_session()
        csrf_token = self.extract_csrf_token('/register')

        response = self.client.post('/register', data={
            'csrf_token': csrf_token,
            'username': '_TEST_reg_player1',
            'email': '_test_player1@example.com',
            'password': 'PlayerPassword123!',
            'confirm_password': 'PlayerPassword123!'
        }, follow_redirects=False)

        # Expect 302 redirect to /login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers.get('Location', ''))
        response.close()

        # Check flash message on /login
        res_login = self.client.get('/login')
        html_login = res_login.data.decode('utf-8')
        res_login.close()
        self.assertIn('Registration successful', html_login)

        # Verify in database: password is a secure hash, role is strictly 'player'
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, username, email, password_hash, role, is_active FROM users WHERE username = %s",
            ('_TEST_reg_player1',)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        self.assertIsNotNone(user)
        self.assertEqual(user['role'], 'player')
        self.assertEqual(user['is_active'], 1)
        self.assertNotEqual(user['password_hash'], 'PlayerPassword123!')
        self.assertTrue(check_password_hash(user['password_hash'], 'PlayerPassword123!'))

        PlayerRegistrationTestCase.registered_player_id = user['id']

    def test_07_tamper_attempt_cannot_create_admin(self):
        """Even if malicious actor injects role='admin' in POST, it MUST be 'player'."""
        self.clear_session()
        csrf_token = self.extract_csrf_token('/register')

        response = self.client.post('/register', data={
            'csrf_token': csrf_token,
            'username': '_TEST_reg_hacker',
            'email': '_test_hacker@example.com',
            'password': 'HackerPassword123!',
            'confirm_password': 'HackerPassword123!',
            'role': 'admin'  # Attempted privilege escalation
        }, follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        response.close()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT role FROM users WHERE username = %s", ('_TEST_reg_hacker',))
        hacker_user = cursor.fetchone()
        cursor.close()
        conn.close()

        self.assertIsNotNone(hacker_user)
        self.assertEqual(hacker_user['role'], 'player', "Privilege escalation occurred: role was not 'player'!")

    def test_08_duplicate_username_and_email_rejected(self):
        self.clear_session()
        csrf_token = self.extract_csrf_token('/register')

        # Duplicate username
        response = self.client.post('/register', data={
            'csrf_token': csrf_token,
            'username': '_TEST_reg_player1',  # Already exists from test_06
            'email': '_test_different@example.com',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        }, follow_redirects=True)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('already taken', html)

        # Duplicate email
        response2 = self.client.post('/register', data={
            'csrf_token': csrf_token,
            'username': '_TEST_different_user',
            'email': '_test_player1@example.com',  # Already exists from test_06
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        }, follow_redirects=True)
        html2 = response2.data.decode('utf-8')
        response2.close()
        self.assertIn('already registered', html2)

    # =========================================================================
    # 4. Player Login & Dashboard Access
    # =========================================================================
    def test_09_player_login_redirects_to_player_dashboard(self):
        self.clear_session()
        csrf_token = self.extract_csrf_token('/login')

        response = self.client.post('/login', data={
            'csrf_token': csrf_token,
            'username': '_TEST_reg_player1',
            'password': 'PlayerPassword123!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/player/dashboard', response.headers.get('Location', ''))
        response.close()

    def test_10_unlinked_registered_player_sees_unlinked_message(self):
        self.set_player_session(self.registered_player_id, '_TEST_reg_player1')
        response = self.client.get('/player/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('Athletic Profile Unlinked', html)
        self.assertIn('administrator has not yet linked', html)

    # =========================================================================
    # 5. Admin Linking & Linked Dashboard Verification
    # =========================================================================
    def test_11_admin_links_player_and_player_sees_profile(self):
        # 1. Admin links the profile
        self.set_admin_session()
        edit_url = f"/admin/players/{self.athlete_profile_id}/edit"
        csrf_token = self.extract_csrf_token(edit_url)

        res_edit = self.client.post(edit_url, data={
            'csrf_token': csrf_token,
            'full_name': '_TEST_Athlete_Virat',
            'sport_id': str(self.sport_id),
            'team_id': str(self.team_id),
            'date_of_birth': '2000-01-01',
            'gender': 'male',
            'jersey_number': '18',
            'user_id': str(self.registered_player_id)
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)
        res_edit.close()

        # 2. Player logs in and views dashboard
        self.set_player_session(self.registered_player_id, '_TEST_reg_player1')
        response = self.client.get('/player/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()

        self.assertIn('Player Portal', html)
        self.assertIn('_TEST_Athlete_Virat', html)
        self.assertIn('_TEST_REG_Cricket', html)
        self.assertIn('_TEST_REG_Warriors', html)
        self.assertIn('#18', html)

    # =========================================================================
    # 6. Authorization Boundaries
    # =========================================================================
    def test_12_player_cannot_access_admin_portal(self):
        self.set_player_session(self.registered_player_id, '_TEST_reg_player1')
        for admin_route in ['/admin/dashboard', '/admin/users', '/admin/users/create', '/admin/sports/new']:
            response = self.client.get(admin_route)
            self.assertEqual(response.status_code, 403, f"Player could access {admin_route}!")
            response.close()

    def test_13_admin_cannot_access_player_portal(self):
        self.set_admin_session()
        response = self.client.get('/player/dashboard')
        self.assertEqual(response.status_code, 403)
        response.close()


if __name__ == '__main__':
    unittest.main()
