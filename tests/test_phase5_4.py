import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import re
import unittest
from unittest.mock import patch, MagicMock
from app import app
from database import get_db_connection
from mysql.connector import Error as MySQLError


class Phase54TournamentsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = cls.app.test_client()
        cls.client.testing = True

        # Clean up any potential leftover test data
        cls.cleanup_test_data()

        # Seed isolated test sports
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_SPORT_T_Football', 'Test Football for Tournaments')
            )
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_SPORT_T_Cricket', 'Test Cricket for Tournaments')
            )
            conn.commit()

            cursor.execute("SELECT id, name FROM sports WHERE name LIKE '_TEST_SPORT_T_%'")
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
            cursor.execute("DELETE FROM tournaments WHERE name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM sports WHERE name LIKE '_TEST_SPORT_T_%'")
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
    # Scenario 1: Admin can open the listing page
    # -------------------------------------------------------------------------
    def test_01_admin_can_access_tournaments_page(self):
        self.set_admin_session()
        res = self.client.get('/admin/tournaments')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Tournament Management', res.data)
        self.assertIn(b'Add Tournament', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 2: Unauthenticated access follows the existing login flow
    # -------------------------------------------------------------------------
    def test_02_unauthenticated_visitor_redirected(self):
        self.clear_session()
        res = self.client.get('/admin/tournaments', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res.headers['Location'].endswith('/login'))

    # -------------------------------------------------------------------------
    # Scenario 3: A player account receives HTTP 403
    # -------------------------------------------------------------------------
    @patch('auth.get_current_user')
    def test_03_authenticated_player_received_403(self, mock_user):
        mock_user.return_value = {
            'id': 999, 'username': 'test_player', 'email': 'player@test.com', 'role': 'player', 'is_active': 1
        }
        self.set_player_session()
        res = self.client.get('/admin/tournaments')
        self.assertEqual(res.status_code, 403)
        self.assertIn(b'403 Forbidden', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 4: A valid tournament can be created
    # -------------------------------------------------------------------------
    def test_04_admin_can_create_valid_tournament(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/tournaments/new')
        sport_id = self.test_sports['_TEST_SPORT_T_Football']

        payload = {
            'csrf_token': token,
            'name': '_TEST_Premier_League_2026',
            'sport_id': str(sport_id),
            'start_date': '2026-11-01',
            'end_date': '2026-12-15',
            'status': 'upcoming',
            'description': 'Annual championship football tournament'
        }

        res = self.client.post('/admin/tournaments/new', data=payload, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'created successfully', res.data)
        self.assertIn(b'_TEST_Premier_League_2026', res.data)

        # Confirm in DB
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM tournaments WHERE name = '_TEST_Premier_League_2026'")
        t = cursor.fetchone()
        self.assertIsNotNone(t)
        self.assertEqual(t['sport_id'], sport_id)
        self.assertEqual(t['status'], 'upcoming')
        self.assertEqual(str(t['start_date']), '2026-11-01')
        self.assertEqual(str(t['end_date']), '2026-12-15')
        cursor.close()
        conn.close()
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 5: Empty or whitespace-only names are rejected
    # -------------------------------------------------------------------------
    def test_05_empty_and_whitespace_names_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/tournaments/new')
        sport_id = self.test_sports['_TEST_SPORT_T_Football']

        for invalid_name in ['', '   ', '\t\n']:
            res = self.client.post(
                '/admin/tournaments/new',
                data={
                    'csrf_token': token,
                    'name': invalid_name,
                    'sport_id': str(sport_id),
                    'start_date': '2026-11-01',
                    'end_date': '2026-11-10'
                },
                follow_redirects=True
            )
            self.assertEqual(res.status_code, 200)
            self.assertIn(b'Tournament name is required and cannot be blank.', res.data)

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 6: Invalid sport IDs are rejected
    # -------------------------------------------------------------------------
    def test_06_invalid_and_nonexistent_sport_ids_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/tournaments/new')

        # Empty sport_id
        res = self.client.post(
            '/admin/tournaments/new',
            data={
                'csrf_token': token,
                'name': '_TEST_Invalid_Sport1',
                'sport_id': '',
                'start_date': '2026-11-01',
                'end_date': '2026-11-10'
            },
            follow_redirects=True
        )
        self.assertIn(b'Please select a valid sport category.', res.data)

        # Non-integer sport_id
        res = self.client.post(
            '/admin/tournaments/new',
            data={
                'csrf_token': token,
                'name': '_TEST_Invalid_Sport2',
                'sport_id': 'invalid',
                'start_date': '2026-11-01',
                'end_date': '2026-11-10'
            },
            follow_redirects=True
        )
        self.assertIn(b'Invalid sport category selected.', res.data)

        # Nonexistent sport_id
        res = self.client.post(
            '/admin/tournaments/new',
            data={
                'csrf_token': token,
                'name': '_TEST_Invalid_Sport3',
                'sport_id': '999999',
                'start_date': '2026-11-01',
                'end_date': '2026-11-10'
            },
            follow_redirects=True
        )
        self.assertIn(b'The selected sport category does not exist in the system.', res.data)

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 7: Invalid date formats are rejected
    # -------------------------------------------------------------------------
    def test_07_invalid_date_formats_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/tournaments/new')
        sport_id = self.test_sports['_TEST_SPORT_T_Football']

        # Missing start date
        res = self.client.post(
            '/admin/tournaments/new',
            data={
                'csrf_token': token,
                'name': '_TEST_Bad_Date1',
                'sport_id': str(sport_id),
                'start_date': '',
                'end_date': '2026-11-10'
            },
            follow_redirects=True
        )
        self.assertIn(b'Start date is required.', res.data)

        # Malformed start date
        res = self.client.post(
            '/admin/tournaments/new',
            data={
                'csrf_token': token,
                'name': '_TEST_Bad_Date2',
                'sport_id': str(sport_id),
                'start_date': '11-01-2026',
                'end_date': '2026-11-10'
            },
            follow_redirects=True
        )
        self.assertIn(b'Invalid start date format.', res.data)

        # Missing end date
        res = self.client.post(
            '/admin/tournaments/new',
            data={
                'csrf_token': token,
                'name': '_TEST_Bad_Date3',
                'sport_id': str(sport_id),
                'start_date': '2026-11-01',
                'end_date': ''
            },
            follow_redirects=True
        )
        self.assertIn(b'End date is required.', res.data)

        # Malformed end date
        res = self.client.post(
            '/admin/tournaments/new',
            data={
                'csrf_token': token,
                'name': '_TEST_Bad_Date4',
                'sport_id': str(sport_id),
                'start_date': '2026-11-01',
                'end_date': '2026-13-40'
            },
            follow_redirects=True
        )
        self.assertIn(b'Invalid end date format.', res.data)

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 8: An end date earlier than the start date is rejected
    # -------------------------------------------------------------------------
    def test_08_end_date_earlier_than_start_date_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/tournaments/new')
        sport_id = self.test_sports['_TEST_SPORT_T_Football']

        res = self.client.post(
            '/admin/tournaments/new',
            data={
                'csrf_token': token,
                'name': '_TEST_Inverted_Dates',
                'sport_id': str(sport_id),
                'start_date': '2026-12-01',
                'end_date': '2026-11-01'  # 1 month before start date
            },
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'End date cannot be earlier than start date.', res.data)

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 9: Invalid status values are rejected
    # -------------------------------------------------------------------------
    def test_09_invalid_status_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/tournaments/new')
        sport_id = self.test_sports['_TEST_SPORT_T_Football']

        res = self.client.post(
            '/admin/tournaments/new',
            data={
                'csrf_token': token,
                'name': '_TEST_Bad_Status',
                'sport_id': str(sport_id),
                'start_date': '2026-11-01',
                'end_date': '2026-11-10',
                'status': 'archived_postponed'
            },
            follow_redirects=True
        )
        self.assertIn(b'Status must be one of', res.data)

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 10: Existing tournaments can be edited
    # -------------------------------------------------------------------------
    def test_10_admin_can_edit_existing_tournament(self):
        self.set_admin_session()
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM tournaments WHERE name = '_TEST_Premier_League_2026'")
        t = cursor.fetchone()
        tournament_id = t['id']
        cursor.close()
        conn.close()

        token = self.get_csrf_token(f'/admin/tournaments/{tournament_id}/edit')
        cricket_sport_id = self.test_sports['_TEST_SPORT_T_Cricket']

        payload = {
            'csrf_token': token,
            'name': '_TEST_Premier_League_Updated',
            'sport_id': str(cricket_sport_id),
            'start_date': '2026-11-05',
            'end_date': '2026-12-20',
            'status': 'ongoing',
            'description': 'Updated tournament description'
        }

        res = self.client.post(f'/admin/tournaments/{tournament_id}/edit', data=payload, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'updated successfully', res.data)
        self.assertIn(b'_TEST_Premier_League_Updated', res.data)

        # Confirm update in DB
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM tournaments WHERE id = %s", (tournament_id,))
        updated_t = cursor.fetchone()
        self.assertEqual(updated_t['name'], '_TEST_Premier_League_Updated')
        self.assertEqual(updated_t['sport_id'], cricket_sport_id)
        self.assertEqual(updated_t['status'], 'ongoing')
        self.assertEqual(str(updated_t['start_date']), '2026-11-05')
        self.assertEqual(str(updated_t['end_date']), '2026-12-20')
        cursor.close()
        conn.close()

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 11: Editing a nonexistent tournament returns HTTP 404
    # -------------------------------------------------------------------------
    def test_11_edit_nonexistent_tournament_returns_404(self):
        self.set_admin_session()
        res_get = self.client.get('/admin/tournaments/999999/edit')
        self.assertEqual(res_get.status_code, 404)

        token = self.get_csrf_token('/admin/tournaments')
        res_post = self.client.post(
            '/admin/tournaments/999999/edit',
            data={'csrf_token': token, 'name': 'Ghost Tournament'}
        )
        self.assertEqual(res_post.status_code, 404)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 12: GET requests cannot create, edit, or delete tournaments
    # -------------------------------------------------------------------------
    def test_12_get_cannot_modify_tournaments(self):
        self.set_admin_session()
        # GET on delete must return 405 Method Not Allowed
        res_delete_get = self.client.get('/admin/tournaments/1/delete')
        self.assertEqual(res_delete_get.status_code, 405)

        # GET on new only renders form
        res_new_get = self.client.get('/admin/tournaments/new')
        self.assertEqual(res_new_get.status_code, 200)
        self.assertIn(b'Create New Tournament', res_new_get.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 13: POST requests without valid CSRF tokens are rejected
    # -------------------------------------------------------------------------
    def test_13_post_without_csrf_rejected(self):
        self.set_admin_session()
        # Create without token
        res_create = self.client.post('/admin/tournaments/new', data={'name': 'No_CSRF'})
        self.assertEqual(res_create.status_code, 400)

        # Delete without token
        res_delete = self.client.post('/admin/tournaments/1/delete', data={})
        self.assertEqual(res_delete.status_code, 400)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 14: Deleting a nonexistent tournament returns HTTP 404
    # -------------------------------------------------------------------------
    def test_14_delete_nonexistent_tournament_returns_404(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/tournaments')
        res = self.client.post('/admin/tournaments/999999/delete', data={'csrf_token': token})
        self.assertEqual(res.status_code, 404)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 15: Tournament deletion respects the matches foreign key
    # -------------------------------------------------------------------------
    def test_15_deletion_respects_matches_foreign_key(self):
        self.set_admin_session()
        # Mock cursor fetchone to simulate match_count > 0
        with patch('app.get_db_connection') as mock_get_conn:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor

            # tournament exists, match_count = 4
            mock_cursor.fetchone.side_effect = [
                {'id': 50, 'name': '_TEST_Tournament_With_Matches'},
                {'match_count': 4}
            ]

            token = self.get_csrf_token('/admin/tournaments')
            res = self.client.post('/admin/tournaments/50/delete', data={'csrf_token': token}, follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            self.assertIn(b'Cannot delete tournament', res.data)
            self.assertIn(b'scheduled or recorded match(es)', res.data)

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 16: Search and sport/status filters work (UI elements and script verification)
    # -------------------------------------------------------------------------
    def test_16_search_and_filters_elements(self):
        self.set_admin_session()
        res = self.client.get('/admin/tournaments')
        html = res.data.decode('utf-8')

        self.assertIn('id="tournaments-search"', html)
        self.assertIn('id="tournament-sport-filter"', html)
        self.assertIn('id="tournament-status-filter"', html)
        self.assertIn('id="tournaments-table"', html)
        self.assertIn('id="tournaments-count-display"', html)

        # Check script.js includes tournaments filtering logic
        js_res = self.client.get('/static/js/script.js')
        js_code = js_res.data.decode('utf-8')
        js_res.close()
        self.assertIn('tournaments-search', js_code)
        self.assertIn('tournament-sport-filter', js_code)
        self.assertIn('tournament-status-filter', js_code)
        self.assertIn('delete-tournament-form', js_code)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 17: Existing sports, teams, and players functionality still works
    # -------------------------------------------------------------------------
    def test_17_regression_sports_teams_players(self):
        self.set_admin_session()
        # Sports page
        res_sports = self.client.get('/admin/sports')
        self.assertEqual(res_sports.status_code, 200)
        self.assertIn(b'Sports Management', res_sports.data)

        # Teams page
        res_teams = self.client.get('/admin/teams')
        self.assertEqual(res_teams.status_code, 200)
        self.assertIn(b'Teams Management', res_teams.data)

        # Players page
        res_players = self.client.get('/admin/players')
        self.assertEqual(res_players.status_code, 200)
        self.assertIn(b'Player Management', res_players.data)

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 18: Existing login, logout, homepage, and auth behavior works
    # -------------------------------------------------------------------------
    def test_18_regression_auth_and_dashboard(self):
        # Homepage
        res_home = self.client.get('/')
        self.assertEqual(res_home.status_code, 200)

        # Dashboard contains Manage Tournaments link
        self.set_admin_session()
        res_dash = self.client.get('/admin/dashboard')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b'/admin/tournaments', res_dash.data)
        self.assertIn(b'btn-manage-tournaments', res_dash.data)

        # Logout with CSRF
        token = self.get_csrf_token('/admin/tournaments')
        res_logout = self.client.post('/logout', data={'csrf_token': token}, follow_redirects=True)
        self.assertEqual(res_logout.status_code, 200)
        self.assertIn(b'You have been signed out', res_logout.data)
        self.clear_session()


if __name__ == '__main__':
    unittest.main()
