import re
import unittest
from app import app
from database import get_db_connection
from werkzeug.security import generate_password_hash, check_password_hash


class Phase95PlayerRegistrationWorkflowTestCase(unittest.TestCase):
    """
    Phase 9.5: Complete Verification Suite
    Testing the full workflow:
    Public Homepage -> Player Sign Up -> Player Login -> Player Dashboard -> Admin-Verified Linking
    Covers all 16 required test scenarios.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.cleanup_test_data()

        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)

            # 1. Test Sport
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_P95_Football', 'Test sport for Phase 9.5 verification')
            )
            cls.sport_id = cursor.lastrowid

            # 2. Test Team
            cursor.execute(
                "INSERT INTO teams (name, sport_id) VALUES (%s, %s)",
                ('_TEST_P95_Arsenal', cls.sport_id)
            )
            cls.team_id = cursor.lastrowid

            # 3. Test Admin User
            admin_pwd = generate_password_hash('AdminPass123!')
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'admin', 1)
                """,
                ('_TEST_p95_admin', '_test_p95_admin@example.com', admin_pwd)
            )
            cls.admin_user_id = cursor.lastrowid

            # 4. Existing Player User for redirect & isolation tests
            player_pwd = generate_password_hash('PlayerPass123!')
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 1)
                """,
                ('_TEST_p95_existing_p', '_test_p95_existing_p@example.com', player_pwd)
            )
            cls.existing_player_user_id = cursor.lastrowid

            # 5. Inactive Player User for auth testing
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 0)
                """,
                ('_TEST_p95_inactive_p', '_test_p95_inactive@example.com', player_pwd)
            )
            cls.inactive_player_user_id = cursor.lastrowid

            # 6. Athlete Profile 1 (to be linked during tests)
            cursor.execute(
                """
                INSERT INTO players (full_name, date_of_birth, gender, sport_id, team_id, jersey_number)
                VALUES (%s, '2001-07-14', 'male', %s, %s, 14)
                """,
                ('_TEST_Athlete_Thierry', cls.sport_id, cls.team_id)
            )
            cls.athlete_1_id = cursor.lastrowid

            # 7. Athlete Profile 2 (linked to existing player)
            cursor.execute(
                """
                INSERT INTO players (full_name, date_of_birth, gender, sport_id, team_id, jersey_number, user_id)
                VALUES (%s, '2002-08-20', 'male', %s, %s, 7, %s)
                """,
                ('_TEST_Athlete_Bukayo', cls.sport_id, cls.team_id, cls.existing_player_user_id)
            )
            cls.athlete_2_id = cursor.lastrowid

            conn.commit()
            cursor.close()
            conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.cleanup_test_data()

    @classmethod
    def cleanup_test_data(cls):
        """Removes all test-created entities and restores configuration."""
        cls.app.config['WTF_CSRF_ENABLED'] = True
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
            sess['username'] = '_TEST_p95_admin'
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
    # 1. Registration page loads successfully
    # -------------------------------------------------------------------------
    def test_01_registration_page_loads_successfully(self):
        self.clear_session()
        response = self.client.get('/register')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()

        self.assertIn('Create Player Account', html)
        self.assertIn('id="username"', html)
        self.assertIn('id="email"', html)
        self.assertIn('id="password"', html)
        self.assertIn('id="confirm_password"', html)
        self.assertIn('id="btn-register-submit"', html)
        self.assertIn('id="link-to-login"', html)

    # -------------------------------------------------------------------------
    # 2. Valid registration creates a player account
    # -------------------------------------------------------------------------
    def test_02_valid_registration_creates_player_account(self):
        self.clear_session()
        csrf_token = self.extract_csrf_token('/register')

        response = self.client.post('/register', data={
            'csrf_token': csrf_token,
            'username': '_TEST_p95_reg_user',
            'email': '_test_p95_reg@example.com',
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!'
        }, follow_redirects=False)

        # 302 Redirect to /login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers.get('Location', ''))
        response.close()

        # Verify flash on login page
        res_login = self.client.get('/login')
        self.assertIn('Registration successful', res_login.data.decode('utf-8'))
        res_login.close()

        # Verify account in MySQL
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, username, email, role, is_active FROM users WHERE username = %s", ('_TEST_p95_reg_user',))
        user_row = cursor.fetchone()
        cursor.close()
        conn.close()

        self.assertIsNotNone(user_row)
        self.assertEqual(user_row['username'], '_TEST_p95_reg_user')
        self.assertEqual(user_row['email'], '_test_p95_reg@example.com')
        Phase95PlayerRegistrationWorkflowTestCase.newly_registered_user_id = user_row['id']

    # -------------------------------------------------------------------------
    # 3. The assigned role is always 'player'
    # -------------------------------------------------------------------------
    def test_03_assigned_role_is_always_player(self):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT role FROM users WHERE username = %s", ('_TEST_p95_reg_user',))
        user_row = cursor.fetchone()
        cursor.close()
        conn.close()

        self.assertIsNotNone(user_row)
        self.assertEqual(user_row['role'], 'player')

    # -------------------------------------------------------------------------
    # 4. Passwords are stored as hashes (never plaintext)
    # -------------------------------------------------------------------------
    def test_04_passwords_are_stored_as_hashes_not_plaintext(self):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT password_hash FROM users WHERE username = %s", ('_TEST_p95_reg_user',))
        user_row = cursor.fetchone()
        cursor.close()
        conn.close()

        self.assertIsNotNone(user_row)
        self.assertNotEqual(user_row['password_hash'], 'StrongPassword123!')
        self.assertTrue(user_row['password_hash'].startswith('scrypt:'))
        self.assertTrue(check_password_hash(user_row['password_hash'], 'StrongPassword123!'))

    # -------------------------------------------------------------------------
    # 5. Duplicate usernames and emails are rejected
    # -------------------------------------------------------------------------
    def test_05_duplicate_usernames_and_emails_rejected(self):
        self.clear_session()
        csrf_token = self.extract_csrf_token('/register')

        # Duplicate username
        res_dup_u = self.client.post('/register', data={
            'csrf_token': csrf_token,
            'username': '_TEST_p95_reg_user',
            'email': '_test_unique_email@example.com',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        }, follow_redirects=True)
        self.assertIn('already taken', res_dup_u.data.decode('utf-8'))
        res_dup_u.close()

        # Duplicate email
        res_dup_e = self.client.post('/register', data={
            'csrf_token': csrf_token,
            'username': '_TEST_unique_u2',
            'email': '_test_p95_reg@example.com',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        }, follow_redirects=True)
        self.assertIn('already registered', res_dup_e.data.decode('utf-8'))
        res_dup_e.close()

    # -------------------------------------------------------------------------
    # 6. Invalid input and mismatched passwords are rejected
    # -------------------------------------------------------------------------
    def test_06_invalid_input_and_mismatched_passwords_rejected(self):
        self.clear_session()
        csrf_token = self.extract_csrf_token('/register')

        # Empty fields
        res_empty = self.client.post('/register', data={
            'csrf_token': csrf_token,
            'username': '',
            'email': '',
            'password': '',
            'confirm_password': ''
        }, follow_redirects=True)
        self.assertIn('Username is required', res_empty.data.decode('utf-8'))
        res_empty.close()

        # Short password (< 8 chars)
        res_short = self.client.post('/register', data={
            'csrf_token': csrf_token,
            'username': '_TEST_usr_short',
            'email': '_test_short@example.com',
            'password': 'short',
            'confirm_password': 'short'
        }, follow_redirects=True)
        self.assertIn('Password must be at least 8 characters', res_short.data.decode('utf-8'))
        res_short.close()

        # Mismatched passwords
        res_mismatch = self.client.post('/register', data={
            'csrf_token': csrf_token,
            'username': '_TEST_usr_mismatch',
            'email': '_test_mismatch@example.com',
            'password': 'Password123!',
            'confirm_password': 'DifferentPassword123!'
        }, follow_redirects=True)
        self.assertIn('Passwords do not match', res_mismatch.data.decode('utf-8'))
        res_mismatch.close()

    # -------------------------------------------------------------------------
    # 7. Public attempts to create an admin account fail safely
    # -------------------------------------------------------------------------
    def test_07_public_attempts_to_create_admin_account_fail_safely(self):
        self.clear_session()
        csrf_token = self.extract_csrf_token('/register')

        res_tamper = self.client.post('/register', data={
            'csrf_token': csrf_token,
            'username': '_TEST_p95_attacker',
            'email': '_test_p95_attacker@example.com',
            'password': 'AttackerPassword123!',
            'confirm_password': 'AttackerPassword123!',
            'role': 'admin'  # Attempted privilege escalation
        }, follow_redirects=False)
        self.assertEqual(res_tamper.status_code, 302)
        res_tamper.close()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT role FROM users WHERE username = %s", ('_TEST_p95_attacker',))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row['role'], 'player', "Privilege escalation vulnerability: public register created non-player!")

    # -------------------------------------------------------------------------
    # 8. CSRF protection follows existing application conventions
    # -------------------------------------------------------------------------
    def test_08_csrf_protection_follows_existing_conventions(self):
        self.app.config['WTF_CSRF_ENABLED'] = True
        self.clear_session()

        # POST without CSRF token must return 400 Bad Request
        res_no_csrf = self.client.post('/register', data={
            'username': '_TEST_p95_no_csrf',
            'email': '_test_p95_nocsrf@example.com',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        })
        self.assertEqual(res_no_csrf.status_code, 400)
        res_no_csrf.close()

    # -------------------------------------------------------------------------
    # 9. Player login redirects to /player/dashboard
    # -------------------------------------------------------------------------
    def test_09_player_login_redirects_to_player_dashboard(self):
        self.clear_session()
        csrf_token = self.extract_csrf_token('/login')

        response = self.client.post('/login', data={
            'csrf_token': csrf_token,
            'username': '_TEST_p95_reg_user',
            'password': 'StrongPassword123!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/player/dashboard', response.headers.get('Location', ''))
        response.close()

    # -------------------------------------------------------------------------
    # 10. Admin login redirects to /admin/dashboard
    # -------------------------------------------------------------------------
    def test_10_admin_login_redirects_to_admin_dashboard(self):
        self.clear_session()
        csrf_token = self.extract_csrf_token('/login')

        response = self.client.post('/login', data={
            'csrf_token': csrf_token,
            'username': '_TEST_p95_admin',
            'password': 'AdminPass123!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/dashboard', response.headers.get('Location', ''))
        response.close()

    # -------------------------------------------------------------------------
    # 11. Unlinked players see the correct informational state
    # -------------------------------------------------------------------------
    def test_11_unlinked_players_see_correct_informational_state(self):
        self.set_player_session(self.newly_registered_user_id, '_TEST_p95_reg_user')
        response = self.client.get('/player/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()

        self.assertIn('Athletic Profile Unlinked', html)
        self.assertIn('administrator has not yet linked', html)
        self.assertIn('View Account Profile', html)

    # -------------------------------------------------------------------------
    # 12. Admin linking connects the correct player profile
    # -------------------------------------------------------------------------
    def test_12_admin_linking_connects_correct_player_profile(self):
        self.set_admin_session()
        edit_url = f"/admin/players/{self.athlete_1_id}/edit"

        # Verify new user appears in available_users dropdown
        res_get = self.client.get(edit_url)
        self.assertIn('_TEST_p95_reg_user', res_get.data.decode('utf-8'))
        res_get.close()

        # Link newly registered user to Athlete Thierry
        csrf_token = self.extract_csrf_token(edit_url)
        res_post = self.client.post(edit_url, data={
            'csrf_token': csrf_token,
            'full_name': '_TEST_Athlete_Thierry',
            'sport_id': str(self.sport_id),
            'team_id': str(self.team_id),
            'date_of_birth': '2001-07-14',
            'gender': 'male',
            'jersey_number': '14',
            'user_id': str(self.newly_registered_user_id)
        }, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)
        res_post.close()

        # Verify in database
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id FROM players WHERE id = %s", (self.athlete_1_id,))
        linked_player = cursor.fetchone()
        cursor.close()
        conn.close()

        self.assertEqual(linked_player['user_id'], self.newly_registered_user_id)

    # -------------------------------------------------------------------------
    # 13. Linked players see their own dashboard information
    # -------------------------------------------------------------------------
    def test_13_linked_players_see_their_own_dashboard_information(self):
        self.set_player_session(self.newly_registered_user_id, '_TEST_p95_reg_user')
        response = self.client.get('/player/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()

        self.assertIn('Player Portal', html)
        self.assertIn('_TEST_Athlete_Thierry', html)
        self.assertIn('_TEST_P95_Football', html)
        self.assertIn('_TEST_P95_Arsenal', html)
        self.assertIn('#14', html)

    # -------------------------------------------------------------------------
    # 14. Players cannot access admin-only routes
    # -------------------------------------------------------------------------
    def test_14_players_cannot_access_admin_only_routes(self):
        self.set_player_session(self.newly_registered_user_id, '_TEST_p95_reg_user')
        admin_endpoints = [
            '/admin/dashboard',
            '/admin/users',
            '/admin/users/create',
            '/admin/players',
            '/admin/sports',
            '/admin/teams',
            '/admin/tournaments',
            '/admin/matches',
            '/admin/results',
            '/admin/reports'
        ]
        for route in admin_endpoints:
            res = self.client.get(route)
            self.assertEqual(res.status_code, 403, f"Player was able to access admin route: {route}")
            res.close()

    # -------------------------------------------------------------------------
    # 15. Players cannot access another player's private data
    # -------------------------------------------------------------------------
    def test_15_players_cannot_access_another_players_private_data(self):
        # User 1 logged in: must see Thierry (#14), NOT Bukayo (#7)
        self.set_player_session(self.newly_registered_user_id, '_TEST_p95_reg_user')
        res_p1 = self.client.get('/player/dashboard')
        html_p1 = res_p1.data.decode('utf-8')
        res_p1.close()

        self.assertIn('_TEST_Athlete_Thierry', html_p1)
        self.assertNotIn('_TEST_Athlete_Bukayo', html_p1)

        # Profile view also derives identity from session
        res_prof1 = self.client.get('/player/profile')
        html_prof1 = res_prof1.data.decode('utf-8')
        res_prof1.close()
        self.assertIn('_test_p95_reg@example.com', html_prof1)
        self.assertNotIn('_test_p95_existing_p@example.com', html_prof1)

        # User 2 logged in: must see Bukayo (#7), NOT Thierry (#14)
        self.set_player_session(self.existing_player_user_id, '_TEST_p95_existing_p')
        res_p2 = self.client.get('/player/dashboard')
        html_p2 = res_p2.data.decode('utf-8')
        res_p2.close()

        self.assertIn('_TEST_Athlete_Bukayo', html_p2)
        self.assertNotIn('_TEST_Athlete_Thierry', html_p2)

    # -------------------------------------------------------------------------
    # 16. Existing admin and management features continue to work
    # -------------------------------------------------------------------------
    def test_16_existing_admin_and_management_features_continue_to_work(self):
        self.set_admin_session()

        # Admin dashboard
        res_dash = self.client.get('/admin/dashboard')
        self.assertEqual(res_dash.status_code, 200)
        res_dash.close()

        # User management & Create User route
        res_users = self.client.get('/admin/users')
        self.assertEqual(res_users.status_code, 200)
        res_users.close()

        res_create_user = self.client.get('/admin/users/create')
        self.assertEqual(res_create_user.status_code, 200)
        res_create_user.close()

        # Reports
        res_reports = self.client.get('/admin/reports')
        self.assertEqual(res_reports.status_code, 200)
        res_reports.close()


if __name__ == '__main__':
    unittest.main()
