import re
import unittest
from datetime import datetime, date
from unittest.mock import patch, MagicMock
from app import app
from database import get_db_connection
from mysql.connector import Error as MySQLError


class Phase55MatchesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = cls.app.test_client()
        cls.client.testing = True

        # Clean up any potential leftover test data
        cls.cleanup_test_data()

        # Seed isolated test sports, teams, and tournament
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            # Create two test sports
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_SPORT_M_Football', 'Test Football for Matches')
            )
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_SPORT_M_Cricket', 'Test Cricket for Matches')
            )
            conn.commit()

            cursor.execute("SELECT id, name FROM sports WHERE name LIKE '_TEST_SPORT_M_%'")
            sports = cursor.fetchall()
            cls.test_sports = {s['name']: s['id'] for s in sports}

            # Create test tournament under Football
            cursor.execute(
                """
                INSERT INTO tournaments (name, sport_id, start_date, end_date, status, description)
                VALUES (%s, %s, %s, %s, 'upcoming', 'Test match tournament')
                """,
                ('_TEST_Tournament_FBCup', cls.test_sports['_TEST_SPORT_M_Football'], '2026-11-01', '2026-11-30')
            )
            conn.commit()
            cursor.execute("SELECT id FROM tournaments WHERE name = '_TEST_Tournament_FBCup'")
            cls.test_tournament_id = cursor.fetchone()['id']

            # Create two teams in Football
            cursor.execute(
                "INSERT INTO teams (name, sport_id) VALUES (%s, %s)",
                ('_TEST_TEAM_MFB_1', cls.test_sports['_TEST_SPORT_M_Football'])
            )
            cursor.execute(
                "INSERT INTO teams (name, sport_id) VALUES (%s, %s)",
                ('_TEST_TEAM_MFB_2', cls.test_sports['_TEST_SPORT_M_Football'])
            )

            # Create one team in Cricket (cross-sport incompatibility tests)
            cursor.execute(
                "INSERT INTO teams (name, sport_id) VALUES (%s, %s)",
                ('_TEST_TEAM_MCricket_1', cls.test_sports['_TEST_SPORT_M_Cricket'])
            )
            conn.commit()

            cursor.execute("SELECT id, name FROM teams WHERE name LIKE '_TEST_TEAM_M%'")
            teams = cursor.fetchall()
            cls.test_teams = {t['name']: t['id'] for t in teams}

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
            cursor.execute("DELETE FROM results WHERE notes LIKE '_TEST_%'")
            cursor.execute("DELETE FROM matches WHERE venue LIKE '_TEST_%'")
            cursor.execute("DELETE FROM tournaments WHERE name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM teams WHERE name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM sports WHERE name LIKE '_TEST_SPORT_M_%'")
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
    # Scenario 1: Admin can access match listing
    # -------------------------------------------------------------------------
    def test_01_admin_can_access_matches_page(self):
        self.set_admin_session()
        res = self.client.get('/admin/matches')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Matches Management', res.data)
        self.assertIn(b'Add Match', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 2: Unauthenticated access follows the existing login flow
    # -------------------------------------------------------------------------
    def test_02_unauthenticated_visitor_redirected(self):
        self.clear_session()
        res = self.client.get('/admin/matches', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res.headers['Location'].endswith('/login'))

    # -------------------------------------------------------------------------
    # Scenario 3: An authenticated player receives HTTP 403
    # -------------------------------------------------------------------------
    @patch('auth.get_current_user')
    def test_03_authenticated_player_receives_403(self, mock_user):
        mock_user.return_value = {
            'id': 999, 'username': 'test_player', 'email': 'player@test.com', 'role': 'player', 'is_active': 1
        }
        self.set_player_session()
        res = self.client.get('/admin/matches')
        self.assertEqual(res.status_code, 403)
        self.assertIn(b'403 Forbidden', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 4: A valid match can be created
    # -------------------------------------------------------------------------
    def test_04_admin_can_create_valid_match(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/matches/new')
        tourney_id = self.test_tournament_id
        team1_id = self.test_teams['_TEST_TEAM_MFB_1']
        team2_id = self.test_teams['_TEST_TEAM_MFB_2']

        payload = {
            'csrf_token': token,
            'tournament_id': str(tourney_id),
            'team1_id': str(team1_id),
            'team2_id': str(team2_id),
            'match_datetime': '2026-11-15T18:30',
            'venue': '_TEST_Wembley_Arena',
            'status': 'scheduled'
        }

        res = self.client.post('/admin/matches/new', data=payload, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'scheduled successfully', res.data)
        self.assertIn(b'_TEST_TEAM_MFB_1', res.data)
        self.assertIn(b'_TEST_TEAM_MFB_2', res.data)

        # Confirm in DB
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM matches WHERE venue = '_TEST_Wembley_Arena'")
        m = cursor.fetchone()
        self.assertIsNotNone(m)
        self.assertEqual(m['tournament_id'], tourney_id)
        self.assertEqual(m['team1_id'], team1_id)
        self.assertEqual(m['team2_id'], team2_id)
        self.assertEqual(m['status'], 'scheduled')
        cursor.close()
        conn.close()
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 5: A nonexistent tournament is rejected
    # -------------------------------------------------------------------------
    def test_05_nonexistent_tournament_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/matches/new')
        team1_id = self.test_teams['_TEST_TEAM_MFB_1']
        team2_id = self.test_teams['_TEST_TEAM_MFB_2']

        res = self.client.post(
            '/admin/matches/new',
            data={
                'csrf_token': token,
                'tournament_id': '999999',
                'team1_id': str(team1_id),
                'team2_id': str(team2_id),
                'match_datetime': '2026-11-15T18:30',
                'venue': '_TEST_Invalid_Tourney'
            },
            follow_redirects=True
        )
        self.assertIn(b'The selected tournament does not exist in the system.', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 6: Nonexistent team IDs are rejected
    # -------------------------------------------------------------------------
    def test_06_nonexistent_team_ids_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/matches/new')
        tourney_id = self.test_tournament_id
        valid_team_id = self.test_teams['_TEST_TEAM_MFB_1']

        # Nonexistent Team 1
        res = self.client.post(
            '/admin/matches/new',
            data={
                'csrf_token': token,
                'tournament_id': str(tourney_id),
                'team1_id': '999999',
                'team2_id': str(valid_team_id),
                'match_datetime': '2026-11-15T18:30',
                'venue': '_TEST_Bad_Team'
            },
            follow_redirects=True
        )
        self.assertIn(b'One or both of the selected teams do not exist in the system.', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 7: Selecting the same team twice is rejected
    # -------------------------------------------------------------------------
    def test_07_same_team_twice_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/matches/new')
        tourney_id = self.test_tournament_id
        team1_id = self.test_teams['_TEST_TEAM_MFB_1']

        res = self.client.post(
            '/admin/matches/new',
            data={
                'csrf_token': token,
                'tournament_id': str(tourney_id),
                'team1_id': str(team1_id),
                'team2_id': str(team1_id),  # Identical team
                'match_datetime': '2026-11-15T18:30',
                'venue': '_TEST_Same_Team'
            },
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Team 1 and Team 2 must be different teams.', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 8: Teams from different sports are rejected
    # -------------------------------------------------------------------------
    def test_08_teams_from_different_sports_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/matches/new')
        tourney_id = self.test_tournament_id  # Football tournament
        fb_team_id = self.test_teams['_TEST_TEAM_MFB_1']  # Football team
        cricket_team_id = self.test_teams['_TEST_TEAM_MCricket_1']  # Cricket team

        res = self.client.post(
            '/admin/matches/new',
            data={
                'csrf_token': token,
                'tournament_id': str(tourney_id),
                'team1_id': str(fb_team_id),
                'team2_id': str(cricket_team_id),
                'match_datetime': '2026-11-15T18:30',
                'venue': '_TEST_Diff_Sport_Teams'
            },
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Both competing teams must belong to the same sport discipline as the tournament.', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 9: A team incompatible with the tournament sport is rejected
    # -------------------------------------------------------------------------
    def test_09_team_incompatible_with_tournament_sport_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/matches/new')
        tourney_id = self.test_tournament_id  # Football tournament
        fb_team_id = self.test_teams['_TEST_TEAM_MFB_2']  # Football team
        cricket_team_id = self.test_teams['_TEST_TEAM_MCricket_1']  # Cricket team

        # Team 1 is cricket (incompatible with football tournament)
        res = self.client.post(
            '/admin/matches/new',
            data={
                'csrf_token': token,
                'tournament_id': str(tourney_id),
                'team1_id': str(cricket_team_id),
                'team2_id': str(fb_team_id),
                'match_datetime': '2026-11-15T18:30',
                'venue': '_TEST_Incompatible_Tourney_Sport'
            },
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Both competing teams must belong to the same sport discipline as the tournament.', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 10: Invalid date/time input is rejected
    # -------------------------------------------------------------------------
    def test_10_invalid_datetime_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/matches/new')
        tourney_id = self.test_tournament_id
        team1_id = self.test_teams['_TEST_TEAM_MFB_1']
        team2_id = self.test_teams['_TEST_TEAM_MFB_2']

        # Missing date
        res_empty = self.client.post(
            '/admin/matches/new',
            data={
                'csrf_token': token,
                'tournament_id': str(tourney_id),
                'team1_id': str(team1_id),
                'team2_id': str(team2_id),
                'match_datetime': '',
                'venue': '_TEST_No_Date'
            },
            follow_redirects=True
        )
        self.assertIn(b'Match date and time is required.', res_empty.data)

        # Malformed date
        res_bad = self.client.post(
            '/admin/matches/new',
            data={
                'csrf_token': token,
                'tournament_id': str(tourney_id),
                'team1_id': str(team1_id),
                'team2_id': str(team2_id),
                'match_datetime': 'invalid-date-string',
                'venue': '_TEST_Bad_Date'
            },
            follow_redirects=True
        )
        self.assertIn(b'Invalid match date and time format.', res_bad.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 11: Invalid match status is rejected
    # -------------------------------------------------------------------------
    def test_11_invalid_status_rejected(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/matches/new')
        tourney_id = self.test_tournament_id
        team1_id = self.test_teams['_TEST_TEAM_MFB_1']
        team2_id = self.test_teams['_TEST_TEAM_MFB_2']

        res = self.client.post(
            '/admin/matches/new',
            data={
                'csrf_token': token,
                'tournament_id': str(tourney_id),
                'team1_id': str(team1_id),
                'team2_id': str(team2_id),
                'match_datetime': '2026-11-15T18:30',
                'venue': '_TEST_Bad_Status',
                'status': 'forfeited_suspended'
            },
            follow_redirects=True
        )
        self.assertIn(b'Status must be one of', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 12: A valid match can be edited
    # -------------------------------------------------------------------------
    def test_12_admin_can_edit_existing_match(self):
        self.set_admin_session()
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM matches WHERE venue = '_TEST_Wembley_Arena'")
        m = cursor.fetchone()
        match_id = m['id']
        cursor.close()
        conn.close()

        token = self.get_csrf_token(f'/admin/matches/{match_id}/edit')
        tourney_id = self.test_tournament_id
        team1_id = self.test_teams['_TEST_TEAM_MFB_1']
        team2_id = self.test_teams['_TEST_TEAM_MFB_2']

        payload = {
            'csrf_token': token,
            'tournament_id': str(tourney_id),
            'team1_id': str(team2_id),  # Invert home / away
            'team2_id': str(team1_id),
            'match_datetime': '2026-11-20T20:00',
            'venue': '_TEST_Camp_Nou_Edited',
            'status': 'ongoing'
        }

        res = self.client.post(f'/admin/matches/{match_id}/edit', data=payload, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'updated successfully', res.data)

        # Confirm update in DB
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM matches WHERE id = %s", (match_id,))
        updated_m = cursor.fetchone()
        self.assertEqual(updated_m['venue'], '_TEST_Camp_Nou_Edited')
        self.assertEqual(updated_m['team1_id'], team2_id)
        self.assertEqual(updated_m['team2_id'], team1_id)
        self.assertEqual(updated_m['status'], 'ongoing')
        cursor.close()
        conn.close()
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 13: Editing a nonexistent match returns HTTP 404
    # -------------------------------------------------------------------------
    def test_13_edit_nonexistent_match_returns_404(self):
        self.set_admin_session()
        res_get = self.client.get('/admin/matches/999999/edit')
        self.assertEqual(res_get.status_code, 404)

        token = self.get_csrf_token('/admin/matches')
        res_post = self.client.post(
            '/admin/matches/999999/edit',
            data={'csrf_token': token, 'venue': '_TEST_Ghost'}
        )
        self.assertEqual(res_post.status_code, 404)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 14: Match details display the correct related entities
    # -------------------------------------------------------------------------
    def test_14_match_details_display_related_entities(self):
        self.set_admin_session()
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM matches WHERE venue = '_TEST_Camp_Nou_Edited'")
        match_id = cursor.fetchone()['id']
        cursor.close()
        conn.close()

        res = self.client.get(f'/admin/matches/{match_id}')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'_TEST_Tournament_FBCup', res.data)
        self.assertIn(b'_TEST_SPORT_M_Football', res.data)
        self.assertIn(b'_TEST_TEAM_MFB_1', res.data)
        self.assertIn(b'_TEST_TEAM_MFB_2', res.data)
        self.assertIn(b'_TEST_Camp_Nou_Edited', res.data)
        self.assertIn(b'No result recorded yet', res.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 15: Existing result details are displayed without modifying results
    # -------------------------------------------------------------------------
    def test_15_existing_result_details_displayed(self):
        self.set_admin_session()
        # Insert a match and a result record directly for test
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        tourney_id = self.test_tournament_id
        team1_id = self.test_teams['_TEST_TEAM_MFB_1']
        team2_id = self.test_teams['_TEST_TEAM_MFB_2']

        cursor.execute(
            """
            INSERT INTO matches (tournament_id, team1_id, team2_id, match_datetime, venue, status)
            VALUES (%s, %s, %s, %s, %s, 'completed')
            """,
            (tourney_id, team1_id, team2_id, '2026-11-10 16:00:00', '_TEST_Venue_With_Result')
        )
        match_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO results (match_id, team1_score, team2_score, winner_team_id, notes)
            VALUES (%s, 3, 1, %s, '_TEST_Remarkable_Hat_Trick')
            """,
            (match_id, team1_id)
        )
        conn.commit()
        cursor.close()
        conn.close()

        # Query match details view
        res = self.client.get(f'/admin/matches/{match_id}')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'3', res.data)
        self.assertIn(b'1', res.data)
        self.assertIn(b'_TEST_Remarkable_Hat_Trick', res.data)
        self.assertIn(b'Winner:', res.data)

        # Verify results record in DB remains completely unchanged
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM results WHERE match_id = %s", (match_id,))
        res_row = cursor.fetchone()
        self.assertIsNotNone(res_row)
        self.assertEqual(res_row['team1_score'], 3)
        self.assertEqual(res_row['team2_score'], 1)
        self.assertEqual(res_row['notes'], '_TEST_Remarkable_Hat_Trick')
        cursor.close()
        conn.close()
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 16: GET requests cannot create, edit, or delete matches
    # -------------------------------------------------------------------------
    def test_16_get_cannot_modify_matches(self):
        self.set_admin_session()
        # GET on delete returns 405 Method Not Allowed
        res_delete_get = self.client.get('/admin/matches/1/delete')
        self.assertEqual(res_delete_get.status_code, 405)

        # GET on new only renders form
        res_new_get = self.client.get('/admin/matches/new')
        self.assertEqual(res_new_get.status_code, 200)
        self.assertIn(b'Schedule New Match', res_new_get.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 17: POST requests without valid CSRF tokens are rejected
    # -------------------------------------------------------------------------
    def test_17_post_without_csrf_rejected(self):
        self.set_admin_session()
        res_create = self.client.post('/admin/matches/new', data={'venue': 'No_CSRF'})
        self.assertEqual(res_create.status_code, 400)

        res_delete = self.client.post('/admin/matches/1/delete', data={})
        self.assertEqual(res_delete.status_code, 400)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 18: Deletion of a nonexistent match returns HTTP 404
    # -------------------------------------------------------------------------
    def test_18_delete_nonexistent_match_returns_404(self):
        self.set_admin_session()
        token = self.get_csrf_token('/admin/matches')
        res = self.client.post('/admin/matches/999999/delete', data={'csrf_token': token})
        self.assertEqual(res.status_code, 404)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 19: Deletion is blocked when related results exist
    # -------------------------------------------------------------------------
    def test_19_deletion_blocked_when_results_exist(self):
        self.set_admin_session()
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM matches WHERE venue = '_TEST_Venue_With_Result'")
        m = cursor.fetchone()
        match_id = m['id']
        cursor.close()
        conn.close()

        token = self.get_csrf_token('/admin/matches')
        res = self.client.post(f'/admin/matches/{match_id}/delete', data={'csrf_token': token}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Cannot delete Match', res.data)
        self.assertIn(b'recorded result', res.data)

        # Confirm match is STILL in database
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM matches WHERE id = %s", (match_id,))
        self.assertIsNotNone(cursor.fetchone())
        cursor.close()
        conn.close()
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 20: Search and filters work correctly
    # -------------------------------------------------------------------------
    def test_20_search_and_filters_elements(self):
        self.set_admin_session()
        res = self.client.get('/admin/matches')
        html = res.data.decode('utf-8')

        self.assertIn('id="matches-search"', html)
        self.assertIn('id="match-tournament-filter"', html)
        self.assertIn('id="match-sport-filter"', html)
        self.assertIn('id="match-status-filter"', html)
        self.assertIn('id="matches-table"', html)
        self.assertIn('id="matches-count-display"', html)

        # Check script.js includes matches filtering logic
        js_res = self.client.get('/static/js/script.js')
        js_code = js_res.data.decode('utf-8')
        js_res.close()
        self.assertIn('matches-search', js_code)
        self.assertIn('match-tournament-filter', js_code)
        self.assertIn('match-sport-filter', js_code)
        self.assertIn('delete-match-form', js_code)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 21: Existing tournament management remains functional
    # -------------------------------------------------------------------------
    def test_21_regression_tournament_management(self):
        self.set_admin_session()
        res_tourneys = self.client.get('/admin/tournaments')
        self.assertEqual(res_tourneys.status_code, 200)
        self.assertIn(b'Tournament Management', res_tourneys.data)
        self.assertIn(b'Add Tournament', res_tourneys.data)
        self.clear_session()

    # -------------------------------------------------------------------------
    # Scenario 22: Existing sports, teams, players, login, logout, and auth pass
    # -------------------------------------------------------------------------
    def test_22_regression_existing_modules_and_auth(self):
        # Homepage
        res_home = self.client.get('/')
        self.assertEqual(res_home.status_code, 200)

        # Dashboard contains both Tournament and Match links
        self.set_admin_session()
        res_dash = self.client.get('/admin/dashboard')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b'/admin/tournaments', res_dash.data)
        self.assertIn(b'/admin/matches', res_dash.data)

        # Sports, Teams, Players listings
        self.assertEqual(self.client.get('/admin/sports').status_code, 200)
        self.assertEqual(self.client.get('/admin/teams').status_code, 200)
        self.assertEqual(self.client.get('/admin/players').status_code, 200)

        # Logout with CSRF
        token = self.get_csrf_token('/admin/matches')
        res_logout = self.client.post('/logout', data={'csrf_token': token}, follow_redirects=True)
        self.assertEqual(res_logout.status_code, 200)
        self.assertIn(b'You have been signed out', res_logout.data)
        self.clear_session()


if __name__ == '__main__':
    unittest.main()
