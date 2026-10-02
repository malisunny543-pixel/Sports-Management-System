import re
import unittest
from datetime import datetime, date
from unittest.mock import patch, MagicMock
from app import app
from database import get_db_connection
from werkzeug.security import generate_password_hash


class Phase7UserManagementTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = cls.app.test_client()
        cls.client.testing = True

        # Clean up any potential leftover test data
        cls.cleanup_test_data()

        # Seed isolated test records: sport, team, users (2 admins, 2 players), and 1 player profile
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            # 1. Sport & Team
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_SPORT_U_Tennis', 'Tennis for User Management Tests')
            )
            conn.commit()
            cursor.execute("SELECT id FROM sports WHERE name = '_TEST_SPORT_U_Tennis'")
            cls.sport_id = cursor.fetchone()['id']

            cursor.execute("INSERT INTO teams (name, sport_id) VALUES (%s, %s)", ('_TEST_TEAM_U_1', cls.sport_id))
            conn.commit()
            cursor.execute("SELECT id FROM teams WHERE name = '_TEST_TEAM_U_1'")
            cls.team_id = cursor.fetchone()['id']

            # 2. Test Users: Admin 1, Admin 2, Player 1 (linked), Player 2 (unlinked)
            pwd_hash = generate_password_hash('Password123!')

            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'admin', 1)
                """,
                ('_TEST_admin_one', '_test_admin_one@example.com', pwd_hash)
            )
            cls.admin_one_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'admin', 1)
                """,
                ('_TEST_admin_two', '_test_admin_two@example.com', pwd_hash)
            )
            cls.admin_two_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 1)
                """,
                ('_TEST_player_one', '_test_player_one@example.com', pwd_hash)
            )
            cls.player_one_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 1)
                """,
                ('_TEST_player_two', '_test_player_two@example.com', pwd_hash)
            )
            cls.player_two_id = cursor.lastrowid
            conn.commit()

            # 3. Linked Player Profile for Player 1
            cursor.execute(
                """
                INSERT INTO players (full_name, date_of_birth, gender, sport_id, team_id, jersey_number, user_id)
                VALUES (%s, %s, 'male', %s, %s, 11, %s)
                """,
                ('_TEST_Athlete_Linked', '1998-05-15', cls.sport_id, cls.team_id, cls.player_one_id)
            )
            conn.commit()
            cursor.execute("SELECT id FROM players WHERE full_name = '_TEST_Athlete_Linked'")
            cls.player_profile_id = cursor.fetchone()['id']

            cursor.close()
            conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.cleanup_test_data()

    @classmethod
    def cleanup_test_data(cls):
        """Cleans up all isolated test data matching '_TEST_%' prefixes."""
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            # Clean up tables in child-to-parent order
            cursor.execute("DELETE FROM player_match_stats WHERE player_id IN (SELECT id FROM players WHERE full_name LIKE '_TEST_%')")
            cursor.execute("DELETE FROM results WHERE match_id IN (SELECT id FROM matches WHERE venue LIKE '_TEST_%')")
            cursor.execute("DELETE FROM matches WHERE venue LIKE '_TEST_%'")
            cursor.execute("DELETE FROM tournaments WHERE name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM players WHERE full_name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM teams WHERE name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM sports WHERE name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM users WHERE username LIKE '_TEST_%'")
            conn.commit()
            cursor.close()
            conn.close()

    def set_admin_session(self, user_id=None, username='_TEST_admin_one'):
        target_id = user_id or self.admin_one_id
        with self.client.session_transaction() as sess:
            sess['user_id'] = target_id
            sess['username'] = username
            sess['role'] = 'admin'

    def set_player_session(self, user_id=None, username='_TEST_player_one'):
        target_id = user_id or self.player_one_id
        with self.client.session_transaction() as sess:
            sess['user_id'] = target_id
            sess['username'] = username
            sess['role'] = 'player'

    def clear_session(self):
        with self.client.session_transaction() as sess:
            sess.clear()

    def get_csrf_token(self, path='/admin/users'):
        res = self.client.get(path)
        html = res.data.decode('utf-8')
        match = re.search(r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']', html)
        if match:
            return match.group(1)
        match_hidden = re.search(r'value=["\']([^"\']+)["\']\s+name=["\']csrf_token["\']', html)
        if match_hidden:
            return match_hidden.group(1)
        return ''

    # -------------------------------------------------------------------------
    # Scenario 1: Unauthenticated access redirects to /login
    # -------------------------------------------------------------------------
    def test_01_unauthenticated_access_redirects_to_login(self):
        self.clear_session()

        # GET /admin/users
        res = self.client.get('/admin/users')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

        # POST /admin/users/1/status (with CSRF token from /login)
        token = self.get_csrf_token('/login')
        res_post1 = self.client.post('/admin/users/1/status', data={'csrf_token': token})
        self.assertEqual(res_post1.status_code, 302)
        self.assertIn('/login', res_post1.headers.get('Location', ''))

        # POST /admin/users/1/role (with CSRF token from /login)
        res_post2 = self.client.post('/admin/users/1/role', data={'csrf_token': token, 'role': 'player'})
        self.assertEqual(res_post2.status_code, 302)
        self.assertIn('/login', res_post2.headers.get('Location', ''))

    # -------------------------------------------------------------------------
    # Scenario 2: Player role cannot access user management (403 Forbidden)
    # -------------------------------------------------------------------------
    def test_02_player_cannot_access_user_management(self):
        self.set_player_session()

        # GET /admin/users -> 403
        res = self.client.get('/admin/users')
        self.assertEqual(res.status_code, 403)

        # POST /admin/users/status -> 403
        csrf_token = self.get_csrf_token('/player/dashboard')
        res_post1 = self.client.post(
            f'/admin/users/{self.player_two_id}/status',
            data={'csrf_token': csrf_token}
        )
        self.assertEqual(res_post1.status_code, 403)

        # POST /admin/users/role -> 403
        res_post2 = self.client.post(
            f'/admin/users/{self.player_two_id}/role',
            data={'csrf_token': csrf_token, 'role': 'admin'}
        )
        self.assertEqual(res_post2.status_code, 403)

    # -------------------------------------------------------------------------
    # Scenario 3: Admin can access user management; password hashes never exposed
    # -------------------------------------------------------------------------
    def test_03_admin_can_access_user_management(self):
        self.set_admin_session()
        res = self.client.get('/admin/users')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        self.assertIn('User Management', html)
        self.assertIn('_TEST_admin_one', html)
        self.assertIn('_test_admin_one@example.com', html)
        self.assertIn('_TEST_player_one', html)
        self.assertIn('_test_player_one@example.com', html)
        self.assertIn('_TEST_Athlete_Linked', html)

        # Verify password hashes are NEVER exposed
        self.assertNotIn('pbkdf2', html.lower())
        self.assertNotIn('$2b$', html)
        self.assertNotIn('scrypt', html.lower())

    # -------------------------------------------------------------------------
    # Scenario 4: User search by username and email
    # -------------------------------------------------------------------------
    def test_04_user_search_by_username_and_email(self):
        self.set_admin_session()

        # Search by username
        res_user = self.client.get('/admin/users?search=_TEST_player_one')
        self.assertEqual(res_user.status_code, 200)
        html_user = res_user.data.decode('utf-8')
        self.assertIn('_TEST_player_one', html_user)
        self.assertNotIn('_TEST_player_two', html_user)

        # Search by email
        res_email = self.client.get('/admin/users?search=_test_player_two@example.com')
        self.assertEqual(res_email.status_code, 200)
        html_email = res_email.data.decode('utf-8')
        self.assertIn('_TEST_player_two', html_email)
        self.assertNotIn('_TEST_player_one', html_email)

    # -------------------------------------------------------------------------
    # Scenario 5: User filtering by role (admin / player)
    # -------------------------------------------------------------------------
    def test_05_user_filtering_by_role(self):
        self.set_admin_session()

        # Filter by admin
        res_admin = self.client.get('/admin/users?role=admin')
        self.assertEqual(res_admin.status_code, 200)
        html_admin = res_admin.data.decode('utf-8')
        self.assertIn('_TEST_admin_one', html_admin)
        self.assertNotIn('_TEST_player_one', html_admin)

        # Filter by player
        res_player = self.client.get('/admin/users?role=player')
        self.assertEqual(res_player.status_code, 200)
        html_player = res_player.data.decode('utf-8')
        self.assertIn(f'id="user-row-{self.player_one_id}"', html_player)
        self.assertNotIn(f'id="user-row-{self.admin_one_id}"', html_player)

    # -------------------------------------------------------------------------
    # Scenario 6: User filtering by status (active / inactive)
    # -------------------------------------------------------------------------
    def test_06_user_filtering_by_status(self):
        self.set_admin_session()

        # Temporarily deactivate player_two
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET is_active = 0 WHERE id = %s", (self.player_two_id,))
        conn.commit()
        c.close()
        conn.close()

        # Filter active
        res_active = self.client.get('/admin/users?status=active')
        self.assertEqual(res_active.status_code, 200)
        html_active = res_active.data.decode('utf-8')
        self.assertIn('_TEST_player_one', html_active)
        self.assertNotIn('_TEST_player_two', html_active)

        # Filter inactive
        res_inactive = self.client.get('/admin/users?status=inactive')
        self.assertEqual(res_inactive.status_code, 200)
        html_inactive = res_inactive.data.decode('utf-8')
        self.assertIn('_TEST_player_two', html_inactive)
        self.assertNotIn('_TEST_player_one', html_inactive)

        # Restore player_two to active
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET is_active = 1 WHERE id = %s", (self.player_two_id,))
        conn.commit()
        c.close()
        conn.close()

    # -------------------------------------------------------------------------
    # Scenario 7: Admin can deactivate and activate user accounts
    # -------------------------------------------------------------------------
    def test_07_admin_can_deactivate_and_activate_user(self):
        self.set_admin_session()
        token = self.get_csrf_token()

        # Deactivate player_two
        res_deact = self.client.post(
            f'/admin/users/{self.player_two_id}/status',
            data={'csrf_token': token, 'status': 'deactivate'}
        )
        self.assertEqual(res_deact.status_code, 302)

        # Verify DB is_active = 0
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)
        c.execute("SELECT is_active FROM users WHERE id = %s", (self.player_two_id,))
        user_row = c.fetchone()
        self.assertEqual(user_row['is_active'], 0)
        c.close()
        conn.close()

        # Reactivate player_two via toggle-status endpoint
        token2 = self.get_csrf_token()
        res_act = self.client.post(
            f'/admin/users/{self.player_two_id}/toggle-status',
            data={'csrf_token': token2, 'status': 'activate'}
        )
        self.assertEqual(res_act.status_code, 302)

        # Verify DB is_active = 1
        conn2 = get_db_connection()
        c2 = conn2.cursor(dictionary=True)
        c2.execute("SELECT is_active FROM users WHERE id = %s", (self.player_two_id,))
        user_row2 = c2.fetchone()
        self.assertEqual(user_row2['is_active'], 1)
        c2.close()
        conn2.close()

    # -------------------------------------------------------------------------
    # Scenario 8: Admin cannot deactivate their own account
    # -------------------------------------------------------------------------
    def test_08_admin_cannot_deactivate_self(self):
        self.set_admin_session(self.admin_one_id, '_TEST_admin_one')
        token = self.get_csrf_token()

        res = self.client.post(
            f'/admin/users/{self.admin_one_id}/status',
            data={'csrf_token': token, 'status': 'deactivate'},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('You cannot deactivate your own administrator account', html)

        # Verify DB is_active is still 1
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)
        c.execute("SELECT is_active FROM users WHERE id = %s", (self.admin_one_id,))
        self.assertEqual(c.fetchone()['is_active'], 1)
        c.close()
        conn.close()

    # -------------------------------------------------------------------------
    # Scenario 9: Last active administrator cannot be deactivated
    # -------------------------------------------------------------------------
    def test_09_last_active_admin_protection_deactivation(self):
        self.set_admin_session(self.admin_one_id, '_TEST_admin_one')
        token = self.get_csrf_token()

        # Temporarily deactivate Admin Two and all other admins except roshan_admin
        # We test deactivating Admin Two when simulated as the only other admin
        # Or mock the active admin count to be 1 to test the safeguard
        with patch('app.get_db_connection') as mock_conn_fn:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn_fn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor

            # fetchone sequence: target_user dict, then active_admins count = 1
            mock_cursor.fetchone.side_effect = [
                {'id': self.admin_two_id, 'username': '_TEST_admin_two', 'email': '_test_admin_two@example.com', 'role': 'admin', 'is_active': 1},
                {'active_admins': 1}
            ]

            res = self.client.post(
                f'/admin/users/{self.admin_two_id}/status',
                data={'csrf_token': token, 'status': 'deactivate'},
                follow_redirects=True
            )
            self.assertEqual(res.status_code, 200)
            html = res.data.decode('utf-8')
            self.assertIn('Cannot deactivate the last active administrator', html)

    # -------------------------------------------------------------------------
    # Scenario 10: Admin cannot remove their own admin role
    # -------------------------------------------------------------------------
    def test_10_admin_cannot_demote_self(self):
        self.set_admin_session(self.admin_one_id, '_TEST_admin_one')
        token = self.get_csrf_token()

        res = self.client.post(
            f'/admin/users/{self.admin_one_id}/role',
            data={'csrf_token': token, 'role': 'player'},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('You cannot remove your own administrator role', html)

        # Verify DB role is still admin
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)
        c.execute("SELECT role FROM users WHERE id = %s", (self.admin_one_id,))
        self.assertEqual(c.fetchone()['role'], 'admin')
        c.close()
        conn.close()

    # -------------------------------------------------------------------------
    # Scenario 11: Last active administrator cannot be demoted
    # -------------------------------------------------------------------------
    def test_11_last_active_admin_protection_demotion(self):
        self.set_admin_session(self.admin_one_id, '_TEST_admin_one')
        token = self.get_csrf_token()

        with patch('app.get_db_connection') as mock_conn_fn:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn_fn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor

            # fetchone: target user is admin_two, active admins count is 1
            mock_cursor.fetchone.side_effect = [
                {'id': self.admin_two_id, 'username': '_TEST_admin_two', 'email': '_test_admin_two@example.com', 'role': 'admin', 'is_active': 1},
                {'active_admins': 1}
            ]

            res = self.client.post(
                f'/admin/users/{self.admin_two_id}/role',
                data={'csrf_token': token, 'role': 'player'},
                follow_redirects=True
            )
            self.assertEqual(res.status_code, 200)
            html = res.data.decode('utf-8')
            self.assertIn('Cannot remove admin role from the last active administrator', html)

    # -------------------------------------------------------------------------
    # Scenario 12: Role change enforces account linking compatibility
    # -------------------------------------------------------------------------
    def test_12_role_change_account_linking_compatibility(self):
        self.set_admin_session()
        token = self.get_csrf_token()

        # Player 1 is linked to _TEST_Athlete_Linked -> Attempting to make Admin MUST be blocked
        res_blocked = self.client.post(
            f'/admin/users/{self.player_one_id}/role',
            data={'csrf_token': token, 'role': 'admin'},
            follow_redirects=True
        )
        self.assertEqual(res_blocked.status_code, 200)
        html_blocked = res_blocked.data.decode('utf-8')
        self.assertIn('Cannot change role to &#39;admin&#39; while user is linked to player profile', html_blocked)

        # Verify DB role remained player
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)
        c.execute("SELECT role FROM users WHERE id = %s", (self.player_one_id,))
        self.assertEqual(c.fetchone()['role'], 'player')
        c.close()
        conn.close()

        # Player 2 is unlinked -> Can safely be promoted to admin
        token2 = self.get_csrf_token()
        res_promoted = self.client.post(
            f'/admin/users/{self.player_two_id}/role',
            data={'csrf_token': token2, 'role': 'admin'},
            follow_redirects=True
        )
        self.assertEqual(res_promoted.status_code, 200)
        html_promoted = res_promoted.data.decode('utf-8')
        self.assertIn('updated to &#39;admin&#39;', html_promoted)

        # Verify DB role is now admin with fresh connection
        conn2 = get_db_connection()
        c2 = conn2.cursor(dictionary=True)
        c2.execute("SELECT role FROM users WHERE id = %s", (self.player_two_id,))
        self.assertEqual(c2.fetchone()['role'], 'admin')
        c2.close()
        conn2.close()

        # Demote Player 2 back to player
        token3 = self.get_csrf_token()
        res_demoted = self.client.post(
            f'/admin/users/{self.player_two_id}/role',
            data={'csrf_token': token3, 'role': 'player'},
            follow_redirects=True
        )
        self.assertEqual(res_demoted.status_code, 200)

        conn3 = get_db_connection()
        c3 = conn3.cursor(dictionary=True)
        c3.execute("SELECT role FROM users WHERE id = %s", (self.player_two_id,))
        self.assertEqual(c3.fetchone()['role'], 'player')
        c3.close()
        conn3.close()

    # -------------------------------------------------------------------------
    # Scenario 13: Invalid user ID and invalid role values rejected
    # -------------------------------------------------------------------------
    def test_13_invalid_user_id_and_role_values(self):
        self.set_admin_session()
        token = self.get_csrf_token()

        # Non-existent user ID -> 404
        res_404_status = self.client.post('/admin/users/999999/status', data={'csrf_token': token})
        self.assertEqual(res_404_status.status_code, 404)

        res_404_role = self.client.post('/admin/users/999999/role', data={'csrf_token': token, 'role': 'player'})
        self.assertEqual(res_404_role.status_code, 404)

        # Invalid role value -> Rejected with validation error
        token2 = self.get_csrf_token()
        res_invalid_role = self.client.post(
            f'/admin/users/{self.player_two_id}/role',
            data={'csrf_token': token2, 'role': 'super_manager'},
            follow_redirects=True
        )
        self.assertEqual(res_invalid_role.status_code, 200)
        html_invalid = res_invalid_role.data.decode('utf-8')
        self.assertIn('Invalid role specified', html_invalid)

    # -------------------------------------------------------------------------
    # Scenario 14: Deactivated user immediately loses session access
    # -------------------------------------------------------------------------
    def test_14_deactivated_user_immediate_session_revocation(self):
        # 1. Establish player session while account is active
        self.set_player_session(self.player_one_id, '_TEST_player_one')
        res_active = self.client.get('/player/dashboard')
        self.assertEqual(res_active.status_code, 200)

        # 2. Deactivate player_one directly in DB (simulating admin action)
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET is_active = 0 WHERE id = %s", (self.player_one_id,))
        conn.commit()
        c.close()
        conn.close()

        # 3. Next request with existing session cookie is immediately rejected and redirected to /login
        res_ejected = self.client.get('/player/dashboard')
        self.assertEqual(res_ejected.status_code, 302)
        self.assertIn('/login', res_ejected.headers.get('Location', ''))

        # 4. Session should be cleared
        with self.client.session_transaction() as sess:
            self.assertNotIn('user_id', sess)

        # Restore player_one to active
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET is_active = 1 WHERE id = %s", (self.player_one_id,))
        conn.commit()
        c.close()
        conn.close()

    # -------------------------------------------------------------------------
    # Scenario 15: State-changing POST without CSRF token is rejected with 400
    # -------------------------------------------------------------------------
    def test_15_post_without_csrf_rejected(self):
        self.set_admin_session()

        # POST /status without CSRF token
        res_status = self.client.post(
            f'/admin/users/{self.player_two_id}/status',
            data={'status': 'deactivate'}
        )
        self.assertEqual(res_status.status_code, 400)

        # POST /role without CSRF token
        res_role = self.client.post(
            f'/admin/users/{self.player_two_id}/role',
            data={'role': 'admin'}
        )
        self.assertEqual(res_role.status_code, 400)

    # -------------------------------------------------------------------------
    # Scenario 16: Users cannot tamper with role or account status via profile
    # -------------------------------------------------------------------------
    def test_16_player_profile_cannot_modify_role_or_status(self):
        self.set_player_session(self.player_one_id, '_TEST_player_one')
        csrf_token = self.get_csrf_token('/player/profile')

        # Attempt to escalate role to admin and change is_active to 0
        res = self.client.post('/player/profile', data={
            'csrf_token': csrf_token,
            'full_name': '_TEST_Athlete_Linked',
            'email': '_test_player_one@example.com',
            'role': 'admin',
            'is_active': 0
        })
        self.assertEqual(res.status_code, 302)

        # Verify DB values were unaffected
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)
        c.execute("SELECT role, is_active FROM users WHERE id = %s", (self.player_one_id,))
        row = c.fetchone()
        self.assertEqual(row['role'], 'player')
        self.assertEqual(row['is_active'], 1)
        c.close()
        conn.close()


if __name__ == '__main__':
    unittest.main()
