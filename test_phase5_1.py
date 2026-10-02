import re
import unittest
from unittest.mock import patch, MagicMock
from app import app
from database import get_db_connection
from mysql.connector import Error as MySQLError


class Phase51SportsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = cls.app.test_client()
        cls.client.testing = True

        # Ensure no leftover test sports exist
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sports WHERE name LIKE '_TEST_%'")
            conn.commit()
            cursor.close()
            conn.close()

    @classmethod
    def tearDownClass(cls):
        # Cleanup any test sports created during test execution
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sports WHERE name LIKE '_TEST_%'")
            conn.commit()
            cursor.close()
            conn.close()

    def get_csrf_token(self, path='/'):
        response = self.client.get(path)
        html = response.data.decode('utf-8')
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
        if not match:
            match = re.search(r'value="([^"]+)"\s+name="csrf_token"', html)
        self.assertIsNotNone(match, f"CSRF token not found in response from {path}")
        return match.group(1)

    def set_admin_session(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'roshan_admin'
            sess['role'] = 'admin'

    def set_player_session(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 999
            sess['username'] = 'test_player'
            sess['role'] = 'player'

    def clear_session(self):
        with self.client.session_transaction() as sess:
            sess.clear()

    # -------------------------------------------------------------------------
    # Scenario 1: Administrator can open /admin/sports
    # -------------------------------------------------------------------------
    def test_01_admin_can_access_sports_page(self):
        self.set_admin_session()
        res = self.client.get('/admin/sports')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Sports Management', res.data)
        self.assertIn(b'Add Sport', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 2: Unauthenticated visitor cannot access /admin/sports
    # -------------------------------------------------------------------------
    def test_02_unauthenticated_visitor_redirected(self):
        self.clear_session()
        res = self.client.get('/admin/sports', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res.headers['Location'].endswith('/login'))

    # -------------------------------------------------------------------------
    # Scenario 3: Authenticated player receives HTTP 403
    # -------------------------------------------------------------------------
    @patch('auth.get_current_user')
    def test_03_authenticated_player_receives_403(self, mock_user):
        mock_user.return_value = {
            'id': 999, 'username': 'test_player', 'email': 'player@test.com', 'role': 'player', 'is_active': 1
        }
        self.set_player_session()
        res = self.client.get('/admin/sports')
        self.assertEqual(res.status_code, 403)
        self.assertIn(b'403 Forbidden', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 4: Administrator can add a valid sport
    # -------------------------------------------------------------------------
    def test_04_admin_can_add_valid_sport(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/sports/new')
        sport_name = "_TEST_Basketball"
        sport_desc = "Fast-paced team sport played on a court."

        res = self.client.post(
            '/admin/sports/new',
            data={'csrf_token': token, 'name': f"  {sport_name}  ", 'description': f"  {sport_desc}  "},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'registered successfully', res.data)
        self.assertIn(sport_name.encode('utf-8'), res.data)

        # Verify record in DB (trimmed)
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM sports WHERE name = %s", (sport_name,))
        sport = cursor.fetchone()
        self.assertIsNotNone(sport)
        self.assertEqual(sport['name'], sport_name)
        self.assertEqual(sport['description'], sport_desc)
        cursor.close()
        conn.close()
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 5: Empty and whitespace-only names are rejected
    # -------------------------------------------------------------------------
    def test_05_empty_and_whitespace_names_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/sports/new')

        # Empty string
        res1 = self.client.post(
            '/admin/sports/new',
            data={'csrf_token': token, 'name': '', 'description': 'Some description'},
            follow_redirects=True
        )
        self.assertEqual(res1.status_code, 200)
        self.assertIn(b'Sport name is required and cannot be blank', res1.data)

        # Whitespace-only string
        res2 = self.client.post(
            '/admin/sports/new',
            data={'csrf_token': token, 'name': '    \t   ', 'description': 'Some description'},
            follow_redirects=True
        )
        self.assertEqual(res2.status_code, 200)
        self.assertIn(b'Sport name is required and cannot be blank', res2.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 6: Duplicate sport names are handled gracefully (case-insensitive)
    # -------------------------------------------------------------------------
    def test_06_duplicate_sport_names_handled_gracefully(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/sports/new')
        # _TEST_Basketball was added in test_04; attempt duplicate with different casing
        res = self.client.post(
            '/admin/sports/new',
            data={'csrf_token': token, 'name': '_test_basketball', 'description': 'Duplicate attempt'},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'already exists', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 7: Administrator can edit an existing sport
    # -------------------------------------------------------------------------
    def test_07_admin_can_edit_existing_sport(self):
        self.set_admin_session()
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM sports WHERE name = '_TEST_Basketball'")
        sport = cursor.fetchone()
        sport_id = sport['id']
        cursor.close()
        conn.close()

        token = self.get_csrf_token(f'/admin/sports/{sport_id}/edit')
        updated_desc = "Updated description for basketball."
        res = self.client.post(
            f'/admin/sports/{sport_id}/edit',
            data={'csrf_token': token, 'name': '_TEST_Basketball', 'description': updated_desc},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'updated successfully', res.data)

        # Verify update in DB
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT description FROM sports WHERE id = %s", (sport_id,))
        updated_row = cursor.fetchone()
        self.assertEqual(updated_row['description'], updated_desc)
        cursor.close()
        conn.close()
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 8: Editing a nonexistent sport returns HTTP 404
    # -------------------------------------------------------------------------
    def test_08_editing_nonexistent_sport_returns_404(self):
        self.set_admin_session()
        res_get = self.client.get('/admin/sports/999999/edit')
        self.assertEqual(res_get.status_code, 404)

        token = self.get_csrf_token('/admin/sports')
        res_post = self.client.post(
            '/admin/sports/999999/edit',
            data={'csrf_token': token, 'name': '_TEST_NonExistent'},
            follow_redirects=True
        )
        self.assertEqual(res_post.status_code, 404)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 9: Administrator can delete an unreferenced sport
    # -------------------------------------------------------------------------
    def test_09_admin_can_delete_unreferenced_sport(self):
        self.set_admin_session()
        # Create a sport to delete
        token = self.get_csrf_token('/admin/sports/new')
        self.client.post(
            '/admin/sports/new',
            data={'csrf_token': token, 'name': '_TEST_To_Delete', 'description': 'Will be deleted'},
            follow_redirects=True
        )

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM sports WHERE name = '_TEST_To_Delete'")
        sport = cursor.fetchone()
        sport_id = sport['id']
        cursor.close()
        conn.close()

        del_token = self.get_csrf_token('/admin/sports')
        res = self.client.post(
            f'/admin/sports/{sport_id}/delete',
            data={'csrf_token': del_token},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'deleted successfully', res.data)

        # Confirm deleted from DB
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM sports WHERE id = %s", (sport_id,))
        self.assertIsNone(cursor.fetchone())
        cursor.close()
        conn.close()
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 10: Deleting a sport referenced by dependent records is blocked gracefully
    # -------------------------------------------------------------------------
    @patch('app.get_db_connection')
    def test_10_deleting_referenced_sport_is_blocked_gracefully(self, mock_get_conn):
        """Simulate dependent team/player/tournament records referencing a sport."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # First query: fetch sport details -> exists
        # Second query: fetch counts -> teams_count=2, players_count=15, tournaments_count=1
        mock_cursor.fetchone.side_effect = [
            {'id': 101, 'name': 'Football'},
            {'teams_count': 2, 'players_count': 15, 'tournaments_count': 1}
        ]

        self.set_admin_session()
        del_token = self.get_csrf_token('/admin/sports')
        res = self.client.post(
            '/admin/sports/101/delete',
            data={'csrf_token': del_token},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Cannot delete sport', res.data)
        self.assertIn(b'referenced by', res.data)
        # Verify DELETE statement was NEVER executed
        for call in mock_cursor.execute.call_args_list:
            sql = call[0][0]
            self.assertNotIn("DELETE FROM sports", sql)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 11: GET requests cannot perform create, update, or delete operations
    # -------------------------------------------------------------------------
    def test_11_get_cannot_modify_data(self):
        self.set_admin_session()
        # GET on delete route should return 405 Method Not Allowed
        res_del = self.client.get('/admin/sports/1/delete')
        self.assertEqual(res_del.status_code, 405)

        # GET on create only renders form, does not insert
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as cnt FROM sports")
        count_before = cursor.fetchone()['cnt']
        cursor.close()
        conn.close()

        res_new = self.client.get('/admin/sports/new')
        self.assertEqual(res_new.status_code, 200)

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as cnt FROM sports")
        count_after = cursor.fetchone()['cnt']
        cursor.close()
        conn.close()

        self.assertEqual(count_before, count_after)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 12: POST requests without valid CSRF token are rejected
    # -------------------------------------------------------------------------
    def test_12_post_without_csrf_rejected(self):
        self.set_admin_session()
        res_create = self.client.post(
            '/admin/sports/new',
            data={'name': '_TEST_No_CSRF', 'description': 'No token'}
        )
        self.assertEqual(res_create.status_code, 400)

        res_delete = self.client.post('/admin/sports/1/delete')
        self.assertEqual(res_delete.status_code, 400)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 13: SQL injection-style input is handled safely via parameterized queries
    # -------------------------------------------------------------------------
    def test_13_sql_injection_handled_safely(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/sports/new')
        injection_name = "_TEST_' OR '1'='1"
        injection_desc = "'); DROP TABLE sports; --"

        res = self.client.post(
            '/admin/sports/new',
            data={'csrf_token': token, 'name': injection_name, 'description': injection_desc},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'registered successfully', res.data)

        # Verify that the sports table still exists and literal strings were stored safely
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM sports WHERE name = %s", (injection_name,))
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['description'], injection_desc)

        # Clean up
        cursor.execute("DELETE FROM sports WHERE id = %s", (row['id'],))
        conn.commit()
        cursor.close()
        conn.close()
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 14: Search filtering elements exist and structure is correct
    # -------------------------------------------------------------------------
    def test_14_search_filtering_ui_and_script(self):
        self.set_admin_session()
        res = self.client.get('/admin/sports')
        html = res.data.decode('utf-8')

        # Check search input element and ID
        self.assertIn('id="sports-search"', html)
        self.assertIn('id="sports-table"', html)

        # Check JavaScript contains search input event listener
        js_res = self.client.get('/static/js/script.js')
        js_code = js_res.data.decode('utf-8')
        self.assertIn('sports-search', js_code)
        self.assertIn('data-sport-name', js_code)
        self.assertIn('delete-sport-form', js_code)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 15: Existing homepage, login, logout, db-test, and dashboard work
    # -------------------------------------------------------------------------
    def test_15_regression_existing_features(self):
        # Homepage
        res_home = self.client.get('/')
        self.assertEqual(res_home.status_code, 200)
        self.assertIn(b'SportsPro', res_home.data)

        # Health endpoint (replaces /db-test, exposes no config data)
        res_db = self.client.get('/health')
        self.assertEqual(res_db.status_code, 200)
        self.assertEqual(res_db.get_json()['status'], 'ok')

        # Admin dashboard contains link to sports management
        self.set_admin_session()
        res_dash = self.client.get('/admin/dashboard')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b'/admin/sports', res_dash.data)
        self.assertIn(b'Manage Sports', res_dash.data)

        # Logout with CSRF
        token = self.get_csrf_token('/admin/dashboard')
        res_logout = self.client.post('/logout', data={'csrf_token': token}, follow_redirects=True)
        self.assertEqual(res_logout.status_code, 200)
        self.assertIn(b'You have been signed out', res_logout.data)
        self.clear_session()


if __name__ == '__main__':
    unittest.main()
