import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import re
import unittest
from unittest.mock import patch, MagicMock
from app import app
from database import get_db_connection
from mysql.connector import Error as MySQLError


class Phase52TeamsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = cls.app.test_client()
        cls.client.testing = True

        # Clean up any potential leftover test data
        cls.cleanup_test_data()

        # Seed two isolated test sports for team testing
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_SPORT_Football', 'Test sport 1')
            )
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_SPORT_Cricket', 'Test sport 2')
            )
            conn.commit()

            cursor.execute("SELECT id, name FROM sports WHERE name LIKE '_TEST_SPORT_%'")
            sports = cursor.fetchall()
            cls.test_sports = {s['name']: s['id'] for s in sports}
            cursor.close()
            conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.cleanup_test_data()

    @classmethod
    def cleanup_test_data(cls):
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM teams WHERE name LIKE '_TEST_%'")
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
    # Scenario 1: Admin can open /admin/teams
    # -------------------------------------------------------------------------
    def test_01_admin_can_access_teams_page(self):
        self.set_admin_session()
        res = self.client.get('/admin/teams')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Teams Management', res.data)
        self.assertIn(b'Add Team', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 2: Unauthenticated users are redirected through the existing login flow
    # -------------------------------------------------------------------------
    def test_02_unauthenticated_visitor_redirected(self):
        self.clear_session()
        res = self.client.get('/admin/teams', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res.headers['Location'].endswith('/login'))

    # -------------------------------------------------------------------------
    # Scenario 3: Authenticated players receive HTTP 403
    # -------------------------------------------------------------------------
    @patch('auth.get_current_user')
    def test_03_authenticated_player_receives_403(self, mock_user):
        mock_user.return_value = {
            'id': 999, 'username': 'test_player', 'email': 'player@test.com', 'role': 'player', 'is_active': 1
        }
        self.set_player_session()
        res = self.client.get('/admin/teams')
        self.assertEqual(res.status_code, 403)
        self.assertIn(b'403 Forbidden', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 4: Admin can create a valid team associated with an existing sport
    # -------------------------------------------------------------------------
    def test_04_admin_can_create_valid_team(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/teams/new')
        sport_id = self.test_sports['_TEST_SPORT_Football']
        team_name = "_TEST_Red_Dragons"

        res = self.client.post(
            '/admin/teams/new',
            data={'csrf_token': token, 'name': f"  {team_name}  ", 'sport_id': str(sport_id)},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'registered successfully', res.data)
        self.assertIn(team_name.encode('utf-8'), res.data)

        # Verify in DB
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM teams WHERE name = %s AND sport_id = %s", (team_name, sport_id))
        team = cursor.fetchone()
        self.assertIsNotNone(team)
        self.assertEqual(team['name'], team_name)
        self.assertEqual(team['sport_id'], sport_id)
        cursor.close()
        conn.close()
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 5: Empty or whitespace-only team names are rejected
    # -------------------------------------------------------------------------
    def test_05_empty_or_whitespace_names_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/teams/new')
        sport_id = self.test_sports['_TEST_SPORT_Football']

        # Empty name
        res1 = self.client.post(
            '/admin/teams/new',
            data={'csrf_token': token, 'name': '', 'sport_id': str(sport_id)},
            follow_redirects=True
        )
        self.assertEqual(res1.status_code, 200)
        self.assertIn(b'Team name is required and cannot be blank', res1.data)

        # Whitespace-only name
        res2 = self.client.post(
            '/admin/teams/new',
            data={'csrf_token': token, 'name': '    \t   ', 'sport_id': str(sport_id)},
            follow_redirects=True
        )
        self.assertEqual(res2.status_code, 200)
        self.assertIn(b'Team name is required and cannot be blank', res2.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 6: Names exceeding 100 characters are rejected
    # -------------------------------------------------------------------------
    def test_06_names_exceeding_100_chars_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/teams/new')
        sport_id = self.test_sports['_TEST_SPORT_Football']
        long_name = "T" * 101

        res = self.client.post(
            '/admin/teams/new',
            data={'csrf_token': token, 'name': long_name, 'sport_id': str(sport_id)},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Team name cannot exceed 100 characters', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 7: Missing or invalid sport selection is rejected
    # -------------------------------------------------------------------------
    def test_07_missing_or_invalid_sport_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/teams/new')

        # Empty sport_id
        res1 = self.client.post(
            '/admin/teams/new',
            data={'csrf_token': token, 'name': '_TEST_Invalid_Sport_1', 'sport_id': ''},
            follow_redirects=True
        )
        self.assertEqual(res1.status_code, 200)
        self.assertIn(b'Please select a valid sport category', res1.data)

        # Non-numeric sport_id
        res2 = self.client.post(
            '/admin/teams/new',
            data={'csrf_token': token, 'name': '_TEST_Invalid_Sport_2', 'sport_id': 'abc'},
            follow_redirects=True
        )
        self.assertEqual(res2.status_code, 200)
        self.assertIn(b'Invalid sport category selected', res2.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 8: Nonexistent sport ID is rejected
    # -------------------------------------------------------------------------
    def test_08_nonexistent_sport_id_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/teams/new')

        res = self.client.post(
            '/admin/teams/new',
            data={'csrf_token': token, 'name': '_TEST_Ghost_Sport_Team', 'sport_id': '999999'},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'The selected sport does not exist in the system', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 9: Duplicate team names within the same sport are handled gracefully
    # -------------------------------------------------------------------------
    def test_09_duplicate_team_name_in_same_sport_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/teams/new')
        sport_id = self.test_sports['_TEST_SPORT_Football']

        # Attempt to insert "_test_red_dragons" (case-insensitive duplicate of "_TEST_Red_Dragons")
        res = self.client.post(
            '/admin/teams/new',
            data={'csrf_token': token, 'name': '_test_red_dragons', 'sport_id': str(sport_id)},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'already exists in', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 10: Same team name allowed for a different sport
    # -------------------------------------------------------------------------
    def test_10_same_team_name_in_different_sport_allowed(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/teams/new')
        cricket_sport_id = self.test_sports['_TEST_SPORT_Cricket']
        team_name = "_TEST_Red_Dragons"  # Same name, different sport!

        res = self.client.post(
            '/admin/teams/new',
            data={'csrf_token': token, 'name': team_name, 'sport_id': str(cricket_sport_id)},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'registered successfully', res.data)

        # Verify both records exist in DB
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, sport_id FROM teams WHERE name = %s", (team_name,))
        rows = cursor.fetchall()
        self.assertEqual(len(rows), 2)
        cursor.close()
        conn.close()
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 11: Admin can edit an existing team
    # -------------------------------------------------------------------------
    def test_11_admin_can_edit_existing_team(self):
        self.set_admin_session()
        football_id = self.test_sports['_TEST_SPORT_Football']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM teams WHERE name = '_TEST_Red_Dragons' AND sport_id = %s", (football_id,))
        team = cursor.fetchone()
        team_id = team['id']
        cursor.close()
        conn.close()

        token = self.get_csrf_token(f'/admin/teams/{team_id}/edit')
        updated_name = "_TEST_Crimson_Dragons"
        res = self.client.post(
            f'/admin/teams/{team_id}/edit',
            data={'csrf_token': token, 'name': updated_name, 'sport_id': str(football_id)},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'updated successfully', res.data)

        # Verify update in DB
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT name FROM teams WHERE id = %s", (team_id,))
        row = cursor.fetchone()
        self.assertEqual(row['name'], updated_name)
        cursor.close()
        conn.close()
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 12: Editing a nonexistent team returns HTTP 404
    # -------------------------------------------------------------------------
    def test_12_editing_nonexistent_team_returns_404(self):
        self.set_admin_session()
        res_get = self.client.get('/admin/teams/999999/edit')
        self.assertEqual(res_get.status_code, 404)

        token = self.get_csrf_token('/admin/teams')
        res_post = self.client.post(
            '/admin/teams/999999/edit',
            data={'csrf_token': token, 'name': '_TEST_Ghost', 'sport_id': '1'},
            follow_redirects=True
        )
        self.assertEqual(res_post.status_code, 404)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 13: Duplicate-name validation excludes current team when editing
    # -------------------------------------------------------------------------
    def test_13_duplicate_check_excludes_current_team(self):
        self.set_admin_session()
        football_id = self.test_sports['_TEST_SPORT_Football']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM teams WHERE name = '_TEST_Crimson_Dragons' AND sport_id = %s", (football_id,))
        team = cursor.fetchone()
        team_id = team['id']
        cursor.close()
        conn.close()

        # Submit same name and same sport_id for the same team -> should succeed without duplicate error!
        token = self.get_csrf_token(f'/admin/teams/{team_id}/edit')
        res = self.client.post(
            f'/admin/teams/{team_id}/edit',
            data={'csrf_token': token, 'name': '_TEST_Crimson_Dragons', 'sport_id': str(football_id)},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'updated successfully', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 14: GET requests cannot create, update, or delete teams
    # -------------------------------------------------------------------------
    def test_14_get_cannot_modify_teams(self):
        self.set_admin_session()
        # GET on delete route should return 405 Method Not Allowed
        res_del = self.client.get('/admin/teams/1/delete')
        self.assertEqual(res_del.status_code, 405)

        # Count teams before GET /new
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as cnt FROM teams")
        cnt_before = cursor.fetchone()['cnt']
        cursor.close()
        conn.close()

        res_new = self.client.get('/admin/teams/new')
        self.assertEqual(res_new.status_code, 200)

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as cnt FROM teams")
        cnt_after = cursor.fetchone()['cnt']
        cursor.close()
        conn.close()

        self.assertEqual(cnt_before, cnt_after)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 15: POST requests without valid CSRF token are rejected
    # -------------------------------------------------------------------------
    def test_15_post_without_csrf_rejected(self):
        self.set_admin_session()
        res_create = self.client.post('/admin/teams/new', data={'name': '_TEST_NoCSRF', 'sport_id': '1'})
        self.assertEqual(res_create.status_code, 400)

        res_edit = self.client.post('/admin/teams/1/edit', data={'name': '_TEST_NoCSRF', 'sport_id': '1'})
        self.assertEqual(res_edit.status_code, 400)

        res_delete = self.client.post('/admin/teams/1/delete')
        self.assertEqual(res_delete.status_code, 400)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 16: Deleting a nonexistent team returns HTTP 404
    # -------------------------------------------------------------------------
    def test_16_deleting_nonexistent_team_returns_404(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/teams')
        res = self.client.post(
            '/admin/teams/999999/delete',
            data={'csrf_token': token},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 404)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 17: Deleting a team with dependent players is blocked gracefully
    # -------------------------------------------------------------------------
    @patch('app.get_db_connection')
    def test_17_deleting_team_with_players_blocked(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # First query: fetch team -> exists
        # Second query: counts -> players_count=11, matches_count=0, results_count=0
        mock_cursor.fetchone.side_effect = [
            {'id': 200, 'name': 'Dragons FC'},
            {'players_count': 11, 'matches_count': 0, 'results_count': 0}
        ]

        self.set_admin_session()
        token = self.get_csrf_token('/admin/teams')
        res = self.client.post('/admin/teams/200/delete', data={'csrf_token': token}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Cannot delete team', res.data)
        self.assertIn(b'assigned player(s)', res.data)

        # Confirm DELETE was never called
        for call in mock_cursor.execute.call_args_list:
            sql = call[0][0]
            self.assertNotIn("DELETE FROM teams", sql)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 18: Deleting a team referenced by matches or results is blocked safely
    # -------------------------------------------------------------------------
    @patch('app.get_db_connection')
    def test_18_deleting_team_with_matches_blocked(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Counts: players_count=0, matches_count=3, results_count=1
        mock_cursor.fetchone.side_effect = [
            {'id': 300, 'name': 'Warriors'},
            {'players_count': 0, 'matches_count': 3, 'results_count': 1}
        ]

        self.set_admin_session()
        token = self.get_csrf_token('/admin/teams')
        res = self.client.post('/admin/teams/300/delete', data={'csrf_token': token}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Cannot delete team', res.data)
        self.assertIn(b'scheduled match(es)', res.data)
        self.assertIn(b'match result(s)', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 19: SQL injection-style input is handled safely via parameterized queries
    # -------------------------------------------------------------------------
    def test_19_sql_injection_handled_safely(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/teams/new')
        sport_id = self.test_sports['_TEST_SPORT_Football']
        injection_name = "_TEST_' OR '1'='1"

        res = self.client.post(
            '/admin/teams/new',
            data={'csrf_token': token, 'name': injection_name, 'sport_id': str(sport_id)},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'registered successfully', res.data)

        # Confirm literal value in DB
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM teams WHERE name = %s AND sport_id = %s", (injection_name, sport_id))
        team = cursor.fetchone()
        self.assertIsNotNone(team)
        self.assertEqual(team['name'], injection_name)
        cursor.close()
        conn.close()
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 20: Search and sport filtering elements exist in UI
    # -------------------------------------------------------------------------
    def test_20_search_and_sport_filtering_ui(self):
        self.set_admin_session()
        res = self.client.get('/admin/teams')
        html = res.data.decode('utf-8')

        self.assertIn('id="teams-search"', html)
        self.assertIn('id="sport-filter"', html)
        self.assertIn('id="teams-table"', html)

        # Check script.js has the team filtering and delete confirmation functions
        js_res = self.client.get('/static/js/script.js')
        js_code = js_res.data.decode('utf-8')
        self.assertIn('teams-search', js_code)
        self.assertIn('sport-filter', js_code)
        self.assertIn('delete-team-form', js_code)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 21: Dashboard Teams & Rosters link points to /admin/teams
    # -------------------------------------------------------------------------
    def test_21_dashboard_teams_card_link(self):
        self.set_admin_session()
        res = self.client.get('/admin/dashboard')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'/admin/teams', res.data)
        self.assertIn(b'Manage Teams', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 22: Regression - existing homepage, login, logout, sports management work
    # -------------------------------------------------------------------------
    def test_22_regression_existing_modules(self):
        # Homepage
        res_home = self.client.get('/')
        self.assertEqual(res_home.status_code, 200)

        # Sports listing
        self.set_admin_session()
        res_sports = self.client.get('/admin/sports')
        self.assertEqual(res_sports.status_code, 200)
        self.assertIn(b'Sports Management', res_sports.data)

        # Logout with CSRF
        token = self.get_csrf_token('/admin/sports')
        res_logout = self.client.post('/logout', data={'csrf_token': token}, follow_redirects=True)
        self.assertEqual(res_logout.status_code, 200)
        self.assertIn(b'You have been signed out', res_logout.data)
        self.clear_session()


if __name__ == '__main__':
    unittest.main()
