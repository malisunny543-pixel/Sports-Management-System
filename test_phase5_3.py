import re
import unittest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from app import app
from database import get_db_connection
from mysql.connector import Error as MySQLError


class Phase53PlayersTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = cls.app.test_client()
        cls.client.testing = True

        # Clean up any potential leftover test data
        cls.cleanup_test_data()

        # Seed isolated test sports, teams, and a player user account
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            # Create two test sports
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_SPORT_Soccer', 'Test Soccer Sport')
            )
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_SPORT_Tennis', 'Test Tennis Sport')
            )
            conn.commit()

            cursor.execute("SELECT id, name FROM sports WHERE name LIKE '_TEST_SPORT_%'")
            sports = cursor.fetchall()
            cls.test_sports = {s['name']: s['id'] for s in sports}

            # Create test teams under the test sports
            cursor.execute(
                "INSERT INTO teams (name, sport_id) VALUES (%s, %s)",
                ('_TEST_TEAM_SoccerLions', cls.test_sports['_TEST_SPORT_Soccer'])
            )
            cursor.execute(
                "INSERT INTO teams (name, sport_id) VALUES (%s, %s)",
                ('_TEST_TEAM_TennisAces', cls.test_sports['_TEST_SPORT_Tennis'])
            )

            # Create an isolated test player user
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 1)
                """,
                ('_test_player_linkable', '_test_player_linkable@example.com', 'scrypt:32768:8:1$dummyhash')
            )
            conn.commit()

            cursor.execute("SELECT id, name, sport_id FROM teams WHERE name LIKE '_TEST_TEAM_%'")
            teams = cursor.fetchall()
            cls.test_teams = {t['name']: t['id'] for t in teams}

            cursor.execute("SELECT id FROM users WHERE username = '_test_player_linkable'")
            user = cursor.fetchone()
            cls.test_linkable_user_id = user['id'] if user else None

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
            # Clean up test players, teams, sports, and users
            cursor.execute("DELETE FROM players WHERE full_name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM teams WHERE name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM sports WHERE name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM users WHERE username LIKE '_test_%'")
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
    # Scenario 1: Admin can open /admin/players
    # -------------------------------------------------------------------------
    def test_01_admin_can_access_players_page(self):
        self.set_admin_session()
        res = self.client.get('/admin/players')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Player Management', res.data)
        self.assertIn(b'Add Player', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 2: Unauthenticated visitors are redirected to /login
    # -------------------------------------------------------------------------
    def test_02_unauthenticated_visitor_redirected(self):
        self.clear_session()
        res = self.client.get('/admin/players', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res.headers['Location'].endswith('/login'))

    # -------------------------------------------------------------------------
    # Scenario 3: Authenticated players receive HTTP 403
    # -------------------------------------------------------------------------
    @patch('auth.get_current_user')
    def test_03_authenticated_player_received_403(self, mock_user):
        mock_user.return_value = {
            'id': 999, 'username': 'test_player', 'email': 'player@test.com', 'role': 'player', 'is_active': 1
        }
        self.set_player_session()
        res = self.client.get('/admin/players')
        self.assertEqual(res.status_code, 403)
        self.assertIn(b'403 Forbidden', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 4: Admin can create a valid player
    # -------------------------------------------------------------------------
    def test_04_admin_can_create_valid_player(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/players/new')
        sport_id = self.test_sports['_TEST_SPORT_Soccer']
        team_id = self.test_teams['_TEST_TEAM_SoccerLions']

        payload = {
            'csrf_token': token,
            'full_name': '_TEST_Lionel_Messi',
            'sport_id': str(sport_id),
            'team_id': str(team_id),
            'date_of_birth': '1987-06-24',
            'gender': 'male',
            'jersey_number': '10',
            'user_id': str(self.test_linkable_user_id)
        }

        res = self.client.post('/admin/players/new', data=payload, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'registered successfully', res.data)
        self.assertIn(b'_TEST_Lionel_Messi', res.data)

        # Confirm in DB
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM players WHERE full_name = '_TEST_Lionel_Messi'")
        p = cursor.fetchone()
        self.assertIsNotNone(p)
        self.assertEqual(p['sport_id'], sport_id)
        self.assertEqual(p['team_id'], team_id)
        self.assertEqual(p['jersey_number'], 10)
        self.assertEqual(p['gender'], 'male')
        self.assertEqual(p['user_id'], self.test_linkable_user_id)
        cursor.close()
        conn.close()
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 5: Empty and whitespace-only names are rejected
    # -------------------------------------------------------------------------
    def test_05_empty_and_whitespace_names_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/players/new')
        sport_id = self.test_sports['_TEST_SPORT_Soccer']

        for invalid_name in ['', '   ', '\t\n']:
            res = self.client.post(
                '/admin/players/new',
                data={'csrf_token': token, 'full_name': invalid_name, 'sport_id': str(sport_id)},
                follow_redirects=True
            )
            self.assertEqual(res.status_code, 200)
            self.assertIn(b'Full name is required and cannot be blank.', res.data)

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 6: Invalid and nonexistent sport IDs are rejected
    # -------------------------------------------------------------------------
    def test_06_invalid_and_nonexistent_sport_ids_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/players/new')

        # Empty sport_id
        res = self.client.post(
            '/admin/players/new',
            data={'csrf_token': token, 'full_name': '_TEST_Invalid_Sport1', 'sport_id': ''},
            follow_redirects=True
        )
        self.assertIn(b'Please select a valid sport discipline.', res.data)

        # Non-integer sport_id
        res = self.client.post(
            '/admin/players/new',
            data={'csrf_token': token, 'full_name': '_TEST_Invalid_Sport2', 'sport_id': 'abc'},
            follow_redirects=True
        )
        self.assertIn(b'Invalid sport discipline selected.', res.data)

        # Nonexistent sport_id
        res = self.client.post(
            '/admin/players/new',
            data={'csrf_token': token, 'full_name': '_TEST_Invalid_Sport3', 'sport_id': '999999'},
            follow_redirects=True
        )
        self.assertIn(b'The selected sport discipline does not exist in the system.', res.data)

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 7: Invalid and nonexistent team IDs are rejected
    # -------------------------------------------------------------------------
    def test_07_invalid_and_nonexistent_team_ids_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/players/new')
        sport_id = self.test_sports['_TEST_SPORT_Soccer']

        # Non-integer team_id
        res = self.client.post(
            '/admin/players/new',
            data={'csrf_token': token, 'full_name': '_TEST_Invalid_Team1', 'sport_id': str(sport_id), 'team_id': 'xyz'},
            follow_redirects=True
        )
        self.assertIn(b'Invalid team selected.', res.data)

        # Nonexistent team_id
        res = self.client.post(
            '/admin/players/new',
            data={'csrf_token': token, 'full_name': '_TEST_Invalid_Team2', 'sport_id': str(sport_id), 'team_id': '888888'},
            follow_redirects=True
        )
        self.assertIn(b'The selected team does not exist in the system.', res.data)

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 8: Team belonging to another sport cannot be assigned
    # -------------------------------------------------------------------------
    def test_08_team_sport_mismatch_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/players/new')
        soccer_sport_id = self.test_sports['_TEST_SPORT_Soccer']
        tennis_team_id = self.test_teams['_TEST_TEAM_TennisAces']

        # Attempting to assign Soccer player to Tennis team
        res = self.client.post(
            '/admin/players/new',
            data={
                'csrf_token': token,
                'full_name': '_TEST_Cross_Sport_Player',
                'sport_id': str(soccer_sport_id),
                'team_id': str(tennis_team_id)
            },
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'does not compete in', res.data)

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 9: Optional unassigned teams work where permitted
    # -------------------------------------------------------------------------
    def test_09_optional_unassigned_team_allowed(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/players/new')
        sport_id = self.test_sports['_TEST_SPORT_Soccer']

        payload = {
            'csrf_token': token,
            'full_name': '_TEST_Free_Agent',
            'sport_id': str(sport_id),
            'team_id': ''  # Unassigned
        }

        res = self.client.post('/admin/players/new', data=payload, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'registered successfully', res.data)

        # Confirm in DB that team_id is NULL
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM players WHERE full_name = '_TEST_Free_Agent'")
        p = cursor.fetchone()
        self.assertIsNotNone(p)
        self.assertIsNone(p['team_id'])
        cursor.close()
        conn.close()

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 10: Invalid dates and future dates of birth are rejected
    # -------------------------------------------------------------------------
    def test_10_invalid_and_future_dates_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/players/new')
        sport_id = self.test_sports['_TEST_SPORT_Soccer']

        # Future date
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        res = self.client.post(
            '/admin/players/new',
            data={'csrf_token': token, 'full_name': '_TEST_Future_Boy', 'sport_id': str(sport_id), 'date_of_birth': tomorrow},
            follow_redirects=True
        )
        self.assertIn(b'Date of birth cannot be in the future.', res.data)

        # Malformed date
        res = self.client.post(
            '/admin/players/new',
            data={'csrf_token': token, 'full_name': '_TEST_Malformed_Date', 'sport_id': str(sport_id), 'date_of_birth': '1999-13-45'},
            follow_redirects=True
        )
        self.assertIn(b'Invalid date of birth format.', res.data)

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 11: Invalid gender values are rejected
    # -------------------------------------------------------------------------
    def test_11_invalid_gender_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/players/new')
        sport_id = self.test_sports['_TEST_SPORT_Soccer']

        res = self.client.post(
            '/admin/players/new',
            data={'csrf_token': token, 'full_name': '_TEST_Invalid_Gender', 'sport_id': str(sport_id), 'gender': 'alien'},
            follow_redirects=True
        )
        self.assertIn(b"Gender must be", res.data)
        self.assertIn(b"male", res.data)

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 12: Jersey-number validation follows the actual schema (0-255)
    # -------------------------------------------------------------------------
    def test_12_jersey_number_validation(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/players/new')
        sport_id = self.test_sports['_TEST_SPORT_Soccer']

        # Non-integer
        res = self.client.post(
            '/admin/players/new',
            data={'csrf_token': token, 'full_name': '_TEST_Bad_Jersey1', 'sport_id': str(sport_id), 'jersey_number': 'ten'},
            follow_redirects=True
        )
        self.assertIn(b'Jersey number must be a valid integer.', res.data)

        # Negative
        res = self.client.post(
            '/admin/players/new',
            data={'csrf_token': token, 'full_name': '_TEST_Bad_Jersey2', 'sport_id': str(sport_id), 'jersey_number': '-5'},
            follow_redirects=True
        )
        self.assertIn(b'Jersey number must be between 0 and 255.', res.data)

        # Out of unsigned tinyint range (>255)
        res = self.client.post(
            '/admin/players/new',
            data={'csrf_token': token, 'full_name': '_TEST_Bad_Jersey3', 'sport_id': str(sport_id), 'jersey_number': '300'},
            follow_redirects=True
        )
        self.assertIn(b'Jersey number must be between 0 and 255.', res.data)

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 13: Admin can edit an existing player
    # -------------------------------------------------------------------------
    def test_13_admin_can_edit_existing_player(self):
        self.set_admin_session()
        # Find player created in scenario 4 or insert a dedicated one
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM players WHERE full_name = '_TEST_Lionel_Messi'")
        p = cursor.fetchone()
        player_id = p['id']
        cursor.close()
        conn.close()

        token = self.get_csrf_token(f'/admin/players/{player_id}/edit')
        tennis_sport_id = self.test_sports['_TEST_SPORT_Tennis']
        tennis_team_id = self.test_teams['_TEST_TEAM_TennisAces']

        payload = {
            'csrf_token': token,
            'full_name': '_TEST_Lionel_Messi_Edited',
            'sport_id': str(tennis_sport_id),
            'team_id': str(tennis_team_id),
            'date_of_birth': '1987-06-24',
            'gender': 'male',
            'jersey_number': '30',
            'user_id': ''
        }

        res = self.client.post(f'/admin/players/{player_id}/edit', data=payload, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'updated successfully', res.data)
        self.assertIn(b'_TEST_Lionel_Messi_Edited', res.data)

        # Confirm update in DB
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM players WHERE id = %s", (player_id,))
        updated_p = cursor.fetchone()
        self.assertEqual(updated_p['full_name'], '_TEST_Lionel_Messi_Edited')
        self.assertEqual(updated_p['sport_id'], tennis_sport_id)
        self.assertEqual(updated_p['team_id'], tennis_team_id)
        self.assertEqual(updated_p['jersey_number'], 30)
        self.assertIsNone(updated_p['user_id'])
        cursor.close()
        conn.close()

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 14: Editing a nonexistent player returns HTTP 404
    # -------------------------------------------------------------------------
    def test_14_edit_nonexistent_player_returns_404(self):
        self.set_admin_session()
        res_get = self.client.get('/admin/players/999999/edit')
        self.assertEqual(res_get.status_code, 404)

        token = self.get_csrf_token('/admin/players')
        res_post = self.client.post('/admin/players/999999/edit', data={'csrf_token': token, 'full_name': 'Ghost'})
        self.assertEqual(res_post.status_code, 404)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 15: GET requests cannot create, edit, or delete players
    # -------------------------------------------------------------------------
    def test_15_get_cannot_modify_players(self):
        self.set_admin_session()
        # GET on delete must return 405 Method Not Allowed
        res_delete_get = self.client.get('/admin/players/1/delete')
        self.assertEqual(res_delete_get.status_code, 405)

        # GET on new only renders form (no records created)
        res_new_get = self.client.get('/admin/players/new')
        self.assertEqual(res_new_get.status_code, 200)
        self.assertIn(b'Register New Player', res_new_get.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 16: POST requests without valid CSRF tokens are rejected
    # -------------------------------------------------------------------------
    def test_16_post_without_csrf_rejected(self):
        self.set_admin_session()
        # Create without token
        res_create = self.client.post('/admin/players/new', data={'full_name': 'No_CSRF'})
        self.assertEqual(res_create.status_code, 400)

        # Delete without token
        res_delete = self.client.post('/admin/players/1/delete', data={})
        self.assertEqual(res_delete.status_code, 400)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 17: Deleting a nonexistent player returns HTTP 404
    # -------------------------------------------------------------------------
    def test_17_delete_nonexistent_player_returns_404(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/players')
        res = self.client.post('/admin/players/999999/delete', data={'csrf_token': token})
        self.assertEqual(res.status_code, 404)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 18: Deletion respects match-statistics foreign-key behavior
    # -------------------------------------------------------------------------
    def test_18_deletion_blocks_if_match_stats_exist(self):
        self.set_admin_session()
        # Mock cursor fetchone to simulate stats_count > 0
        with patch('app.get_db_connection') as mock_get_conn:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor

            # player exists, stats_count = 5
            mock_cursor.fetchone.side_effect = [
                {'id': 77, 'full_name': '_TEST_Player_With_Stats', 'user_id': None},
                {'stats_count': 5}
            ]

            token = self.get_csrf_token('/admin/players')
            res = self.client.post('/admin/players/77/delete', data={'csrf_token': token}, follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            self.assertIn(b'Cannot delete player', res.data)
            self.assertIn(b'recorded match performance statistic(s)', res.data)

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 19: Deleting a player does not delete their linked user account
    # -------------------------------------------------------------------------
    def test_19_deleting_player_does_not_delete_user_account(self):
        self.set_admin_session()
        # Insert a player explicitly linked to cls.test_linkable_user_id
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sport_id = self.test_sports['_TEST_SPORT_Soccer']
        cursor.execute(
            """
            INSERT INTO players (full_name, sport_id, user_id)
            VALUES (%s, %s, %s)
            """,
            ('_TEST_Player_Linked_To_Delete', sport_id, self.test_linkable_user_id)
        )
        conn.commit()
        player_id = cursor.lastrowid
        cursor.close()
        conn.close()

        # Delete the player
        token = self.get_csrf_token('/admin/players')
        res = self.client.post(f'/admin/players/{player_id}/delete', data={'csrf_token': token}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'deleted successfully', res.data)

        # Confirm player is gone
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM players WHERE id = %s", (player_id,))
        self.assertIsNone(cursor.fetchone())

        # CRITICAL: Confirm user account still exists in users table!
        cursor.execute("SELECT id, username FROM users WHERE id = %s", (self.test_linkable_user_id,))
        user_record = cursor.fetchone()
        self.assertIsNotNone(user_record)
        self.assertEqual(user_record['username'], '_test_player_linkable')
        cursor.close()
        conn.close()

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 20: SQL injection-style input is handled safely
    # -------------------------------------------------------------------------
    def test_20_sql_injection_handled_safely(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/players/new')
        sport_id = self.test_sports['_TEST_SPORT_Soccer']
        injection_name = "_TEST_' OR '1'='1"

        res = self.client.post(
            '/admin/players/new',
            data={'csrf_token': token, 'full_name': injection_name, 'sport_id': str(sport_id)},
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'registered successfully', res.data)

        # Confirm literal name in DB
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM players WHERE full_name = %s", (injection_name,))
        player = cursor.fetchone()
        self.assertIsNotNone(player)
        self.assertEqual(player['full_name'], injection_name)
        cursor.close()
        conn.close()

        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 21: Search and filters work (UI elements and script verification)
    # -------------------------------------------------------------------------
    def test_21_search_and_filters_elements(self):
        self.set_admin_session()
        res = self.client.get('/admin/players')
        html = res.data.decode('utf-8')

        self.assertIn('id="players-search"', html)
        self.assertIn('id="player-sport-filter"', html)
        self.assertIn('id="player-team-filter"', html)
        self.assertIn('id="players-table"', html)

        # Check script.js includes players filtering logic
        js_res = self.client.get('/static/js/script.js')
        js_code = js_res.data.decode('utf-8')
        js_res.close()
        self.assertIn('players-search', js_code)
        self.assertIn('player-sport-filter', js_code)
        self.assertIn('player-team-filter', js_code)
        self.assertIn('delete-player-form', js_code)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 22: Existing Sports Management and Teams Management still work
    # -------------------------------------------------------------------------
    def test_22_regression_sports_and_teams_management(self):
        self.set_admin_session()
        # Sports page
        res_sports = self.client.get('/admin/sports')
        self.assertEqual(res_sports.status_code, 200)
        self.assertIn(b'Sports Management', res_sports.data)

        # Teams page
        res_teams = self.client.get('/admin/teams')
        self.assertEqual(res_teams.status_code, 200)
        self.assertIn(b'Teams Management', res_teams.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 23: Existing login, logout, homepage, and auth behavior works
    # -------------------------------------------------------------------------
    def test_23_regression_auth_and_homepage(self):
        # Homepage
        res_home = self.client.get('/')
        self.assertEqual(res_home.status_code, 200)

        # Dashboard
        self.set_admin_session()
        res_dash = self.client.get('/admin/dashboard')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b'/admin/players', res_dash.data)
        self.assertIn(b'/admin/teams', res_dash.data)
        self.assertIn(b'btn-manage-players', res_dash.data)

        # Logout with CSRF
        token = self.get_csrf_token('/admin/players')
        res_logout = self.client.post('/logout', data={'csrf_token': token}, follow_redirects=True)
        self.assertEqual(res_logout.status_code, 200)
        self.assertIn(b'You have been signed out', res_logout.data)
        self.clear_session()


if __name__ == '__main__':
    unittest.main()
