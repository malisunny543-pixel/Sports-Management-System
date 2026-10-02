import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import re
import unittest
from datetime import datetime, date
from unittest.mock import patch, MagicMock
from app import app, validate_match_result
from database import get_db_connection
from mysql.connector import Error as MySQLError


class Phase56ResultsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = cls.app.test_client()
        cls.client.testing = True

        # Clean up any potential leftover test data
        cls.cleanup_test_data()

        # Seed isolated test sport, tournament, and teams
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            # Create isolated sport
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_SPORT_R_Football', 'Test Football for Results')
            )
            conn.commit()

            cursor.execute("SELECT id FROM sports WHERE name = '_TEST_SPORT_R_Football'")
            cls.test_sport_id = cursor.fetchone()['id']

            # Create isolated tournament
            cursor.execute(
                """
                INSERT INTO tournaments (name, sport_id, start_date, end_date, status, description)
                VALUES (%s, %s, %s, %s, 'ongoing', 'Test results tournament')
                """,
                ('_TEST_Tournament_RCup', cls.test_sport_id, '2026-11-01', '2026-11-30')
            )
            conn.commit()
            cursor.execute("SELECT id FROM tournaments WHERE name = '_TEST_Tournament_RCup'")
            cls.test_tournament_id = cursor.fetchone()['id']

            # Create three isolated teams: Team 1, Team 2, and Team Outside
            cursor.execute(
                "INSERT INTO teams (name, sport_id) VALUES (%s, %s)",
                ('_TEST_TEAM_R_1', cls.test_sport_id)
            )
            cursor.execute(
                "INSERT INTO teams (name, sport_id) VALUES (%s, %s)",
                ('_TEST_TEAM_R_2', cls.test_sport_id)
            )
            cursor.execute(
                "INSERT INTO teams (name, sport_id) VALUES (%s, %s)",
                ('_TEST_TEAM_R_Outside', cls.test_sport_id)
            )
            conn.commit()

            cursor.execute("SELECT id, name FROM teams WHERE name LIKE '_TEST_TEAM_R_%'")
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
            cursor.execute("DELETE r FROM results r JOIN matches m ON r.match_id = m.id WHERE m.venue LIKE '_TEST_%' OR r.notes LIKE '_TEST_%'")
            cursor.execute("DELETE FROM results WHERE notes LIKE '_TEST_%'")
            cursor.execute("DELETE FROM matches WHERE venue LIKE '_TEST_%'")
            cursor.execute("DELETE FROM tournaments WHERE name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM teams WHERE name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM sports WHERE name LIKE '_TEST_SPORT_R_%'")
            conn.commit()
            cursor.close()
            conn.close()

    def setUp(self):
        self.clear_session()

    def tearDown(self):
        self.clear_session()

    def get_csrf_token(self, path='/'):
        response = self.client.get(path)
        html = response.data.decode('utf-8')
        response.close()
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

    def create_test_match(self, status='scheduled', venue='_TEST_Venue_Result'):
        conn = get_db_connection()
        self.assertIsNotNone(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            INSERT INTO matches (tournament_id, team1_id, team2_id, match_datetime, venue, status)
            VALUES (%s, %s, %s, '2026-11-15 15:00:00', %s, %s)
            """,
            (
                self.test_tournament_id,
                self.test_teams['_TEST_TEAM_R_1'],
                self.test_teams['_TEST_TEAM_R_2'],
                venue,
                status
            )
        )
        conn.commit()
        match_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return match_id

    def delete_test_match(self, match_id):
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM results WHERE match_id = %s", (match_id,))
            cursor.execute("DELETE FROM matches WHERE id = %s", (match_id,))
            conn.commit()
            cursor.close()
            conn.close()

    # -------------------------------------------------------------------------
    # Scenario 1: Admin can access the results listing
    # -------------------------------------------------------------------------
    def test_01_admin_can_access_results_listing(self):
        self.set_admin_session()
        response = self.client.get('/admin/results')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('Results &amp; Score Management', html)
        self.assertIn('Search by tournament, team name, or venue...', html)

    # -------------------------------------------------------------------------
    # Scenario 2: Unauthenticated visitor is redirected to login
    # -------------------------------------------------------------------------
    def test_02_unauthenticated_visitor_redirected(self):
        self.clear_session()
        response = self.client.get('/admin/results')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers.get('Location', ''))
        response.close()

        response2 = self.client.get('/admin/results/1/edit')
        self.assertEqual(response2.status_code, 302)
        self.assertIn('/login', response2.headers.get('Location', ''))
        response2.close()

    # -------------------------------------------------------------------------
    # Scenario 3: Authenticated player receives 403
    # -------------------------------------------------------------------------
    @patch('auth.get_current_user')
    def test_03_authenticated_player_forbidden(self, mock_user):
        mock_user.return_value = {
            'id': 999, 'username': 'test_player', 'email': 'player@test.com', 'role': 'player', 'is_active': 1
        }
        self.set_player_session()
        response = self.client.get('/admin/results')
        self.assertEqual(response.status_code, 403)
        response.close()

        response2 = self.client.get('/admin/results/1/edit')
        self.assertEqual(response2.status_code, 403)
        response2.close()

    # -------------------------------------------------------------------------
    # Scenario 4: Missing match returns 404
    # -------------------------------------------------------------------------
    def test_04_missing_match_returns_404(self):
        self.set_admin_session()
        response = self.client.get('/admin/results/999999/edit')
        self.assertEqual(response.status_code, 404)
        response.close()

        csrf_token = self.get_csrf_token('/')
        response_post = self.client.post('/admin/results/999999/edit', data={
            'csrf_token': csrf_token,
            'team1_score': '2',
            'team2_score': '1'
        })
        self.assertEqual(response_post.status_code, 404)
        response_post.close()

    # -------------------------------------------------------------------------
    # Scenario 5: Admin can create a valid Team 1 win
    # -------------------------------------------------------------------------
    def test_05_admin_create_valid_team1_win(self):
        match_id = self.create_test_match()
        try:
            self.set_admin_session()
            csrf_token = self.get_csrf_token(f'/admin/results/{match_id}/edit')
            response = self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': csrf_token,
                'team1_score': '3',
                'team2_score': '1',
                'notes': '_TEST_ Team 1 dominant performance'
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            response.close()

            # Verify in DB
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM results WHERE match_id = %s", (match_id,))
            res = cursor.fetchone()
            self.assertIsNotNone(res)
            self.assertEqual(res['team1_score'], 3)
            self.assertEqual(res['team2_score'], 1)
            self.assertEqual(res['winner_team_id'], self.test_teams['_TEST_TEAM_R_1'])
            self.assertEqual(res['notes'], '_TEST_ Team 1 dominant performance')

            # Verify match status set to completed
            cursor.execute("SELECT status FROM matches WHERE id = %s", (match_id,))
            m = cursor.fetchone()
            self.assertEqual(m['status'], 'completed')
            cursor.close()
            conn.close()
        finally:
            self.delete_test_match(match_id)

    # -------------------------------------------------------------------------
    # Scenario 6: Admin can create a valid Team 2 win
    # -------------------------------------------------------------------------
    def test_06_admin_create_valid_team2_win(self):
        match_id = self.create_test_match()
        try:
            self.set_admin_session()
            csrf_token = self.get_csrf_token(f'/admin/results/{match_id}/edit')
            response = self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': csrf_token,
                'team1_score': '0',
                'team2_score': '4',
                'notes': '_TEST_ Team 2 clean sheet'
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            response.close()

            # Verify in DB
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM results WHERE match_id = %s", (match_id,))
            res = cursor.fetchone()
            self.assertIsNotNone(res)
            self.assertEqual(res['team1_score'], 0)
            self.assertEqual(res['team2_score'], 4)
            self.assertEqual(res['winner_team_id'], self.test_teams['_TEST_TEAM_R_2'])

            cursor.execute("SELECT status FROM matches WHERE id = %s", (match_id,))
            m = cursor.fetchone()
            self.assertEqual(m['status'], 'completed')
            cursor.close()
            conn.close()
        finally:
            self.delete_test_match(match_id)

    # -------------------------------------------------------------------------
    # Scenario 7: Equal scores create a draw with NULL winner
    # -------------------------------------------------------------------------
    def test_07_equal_scores_create_draw_null_winner(self):
        match_id = self.create_test_match()
        try:
            self.set_admin_session()
            csrf_token = self.get_csrf_token(f'/admin/results/{match_id}/edit')
            response = self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': csrf_token,
                'team1_score': '2',
                'team2_score': '2',
                'tie_breaker_winner': '',
                'notes': ''
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            response.close()

            # Verify in DB
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM results WHERE match_id = %s", (match_id,))
            res = cursor.fetchone()
            self.assertIsNotNone(res)
            self.assertEqual(res['team1_score'], 2)
            self.assertEqual(res['team2_score'], 2)
            self.assertIsNone(res['winner_team_id'])

            cursor.execute("SELECT status FROM matches WHERE id = %s", (match_id,))
            m = cursor.fetchone()
            self.assertEqual(m['status'], 'completed')
            cursor.close()
            conn.close()
        finally:
            self.delete_test_match(match_id)

    # -------------------------------------------------------------------------
    # Scenario 8: Tie-break without notes is rejected
    # -------------------------------------------------------------------------
    def test_08_tie_break_without_notes_rejected(self):
        match_id = self.create_test_match()
        try:
            self.set_admin_session()
            csrf_token = self.get_csrf_token(f'/admin/results/{match_id}/edit')
            response = self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': csrf_token,
                'team1_score': '1',
                'team2_score': '1',
                'tie_breaker_winner': str(self.test_teams['_TEST_TEAM_R_1']),
                'notes': '   '  # empty notes
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            html = response.data.decode('utf-8')
            response.close()
            self.assertIn('tie-break winner requires non-empty explanatory notes', html.lower())

            # Verify no result in DB and status unchanged
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM results WHERE match_id = %s", (match_id,))
            res = cursor.fetchone()
            self.assertIsNone(res)

            cursor.execute("SELECT status FROM matches WHERE id = %s", (match_id,))
            m = cursor.fetchone()
            self.assertEqual(m['status'], 'scheduled')
            cursor.close()
            conn.close()
        finally:
            self.delete_test_match(match_id)

    # -------------------------------------------------------------------------
    # Scenario 9: Valid tie-break with notes records selected match team as winner
    # -------------------------------------------------------------------------
    def test_09_valid_tie_break_with_notes_records_winner(self):
        match_id = self.create_test_match()
        try:
            self.set_admin_session()
            csrf_token = self.get_csrf_token(f'/admin/results/{match_id}/edit')
            response = self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': csrf_token,
                'team1_score': '2',
                'team2_score': '2',
                'tie_breaker_winner': str(self.test_teams['_TEST_TEAM_R_2']),
                'notes': '_TEST_ Team 2 won 5-4 on penalty shootouts after 2-2 draw'
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            response.close()

            # Verify in DB
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM results WHERE match_id = %s", (match_id,))
            res = cursor.fetchone()
            self.assertIsNotNone(res)
            self.assertEqual(res['team1_score'], 2)
            self.assertEqual(res['team2_score'], 2)
            self.assertEqual(res['winner_team_id'], self.test_teams['_TEST_TEAM_R_2'])
            self.assertEqual(res['notes'], '_TEST_ Team 2 won 5-4 on penalty shootouts after 2-2 draw')

            cursor.execute("SELECT status FROM matches WHERE id = %s", (match_id,))
            m = cursor.fetchone()
            self.assertEqual(m['status'], 'completed')
            cursor.close()
            conn.close()
        finally:
            self.delete_test_match(match_id)

    # -------------------------------------------------------------------------
    # Scenario 10: Invalid winner choice is rejected
    # -------------------------------------------------------------------------
    def test_10_invalid_winner_choice_rejected(self):
        match_id = self.create_test_match()
        try:
            self.set_admin_session()
            csrf_token = self.get_csrf_token(f'/admin/results/{match_id}/edit')
            # Attempt to select a team not competing in this match
            response = self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': csrf_token,
                'team1_score': '1',
                'team2_score': '1',
                'tie_breaker_winner': str(self.test_teams['_TEST_TEAM_R_Outside']),
                'notes': '_TEST_ Illegitimate outside winner'
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            html = response.data.decode('utf-8')
            response.close()
            self.assertIn('must be one of the two competing teams', html.lower())

            # Verify no result in DB
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM results WHERE match_id = %s", (match_id,))
            self.assertIsNone(cursor.fetchone())
            cursor.close()
            conn.close()
        finally:
            self.delete_test_match(match_id)

    # -------------------------------------------------------------------------
    # Scenario 11: Negative scores are rejected
    # -------------------------------------------------------------------------
    def test_11_negative_scores_rejected(self):
        match_id = self.create_test_match()
        try:
            self.set_admin_session()
            csrf_token = self.get_csrf_token(f'/admin/results/{match_id}/edit')
            response = self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': csrf_token,
                'team1_score': '-5',
                'team2_score': '2'
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            html = response.data.decode('utf-8')
            response.close()
            self.assertIn('negative', html.lower())

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM results WHERE match_id = %s", (match_id,))
            self.assertIsNone(cursor.fetchone())
            cursor.close()
            conn.close()
        finally:
            self.delete_test_match(match_id)

    # -------------------------------------------------------------------------
    # Scenario 12: Non-integer and out-of-range scores are rejected
    # -------------------------------------------------------------------------
    def test_12_non_integer_and_out_of_range_scores_rejected(self):
        match_id = self.create_test_match()
        try:
            self.set_admin_session()
            csrf_token = self.get_csrf_token(f'/admin/results/{match_id}/edit')

            # Non-integer
            response1 = self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': csrf_token,
                'team1_score': 'abc',
                'team2_score': '2'
            }, follow_redirects=True)
            self.assertEqual(response1.status_code, 200)
            html1 = response1.data.decode('utf-8')
            response1.close()
            self.assertIn('whole numbers', html1.lower())

            # Out of range (> 65535)
            response2 = self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': csrf_token,
                'team1_score': '70000',
                'team2_score': '1'
            }, follow_redirects=True)
            self.assertEqual(response2.status_code, 200)
            html2 = response2.data.decode('utf-8')
            response2.close()
            self.assertIn('65,535', html2.lower())

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM results WHERE match_id = %s", (match_id,))
            self.assertIsNone(cursor.fetchone())
            cursor.close()
            conn.close()
        finally:
            self.delete_test_match(match_id)

    # -------------------------------------------------------------------------
    # Scenario 13: Editing an existing result updates the same row without duplicates
    # -------------------------------------------------------------------------
    def test_13_editing_updates_same_row(self):
        match_id = self.create_test_match()
        try:
            self.set_admin_session()
            # Step 1: Initial record
            csrf_token1 = self.get_csrf_token(f'/admin/results/{match_id}/edit')
            self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': csrf_token1,
                'team1_score': '1',
                'team2_score': '0',
                'notes': '_TEST_ Initial result'
            }, follow_redirects=True).close()

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, team1_score, team2_score FROM results WHERE match_id = %s", (match_id,))
            initial_result = cursor.fetchone()
            initial_result_id = initial_result['id']
            cursor.close()
            conn.close()

            # Step 2: Edit result to 2-3
            csrf_token2 = self.get_csrf_token(f'/admin/results/{match_id}/edit')
            res_edit = self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': csrf_token2,
                'team1_score': '2',
                'team2_score': '3',
                'notes': '_TEST_ Updated result'
            }, follow_redirects=True)
            self.assertEqual(res_edit.status_code, 200)
            res_edit.close()

            # Verify same row updated
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM results WHERE match_id = %s", (match_id,))
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 1)
            updated = rows[0]
            self.assertEqual(updated['id'], initial_result_id)
            self.assertEqual(updated['team1_score'], 2)
            self.assertEqual(updated['team2_score'], 3)
            self.assertEqual(updated['winner_team_id'], self.test_teams['_TEST_TEAM_R_2'])
            self.assertEqual(updated['notes'], '_TEST_ Updated result')
            cursor.close()
            conn.close()
        finally:
            self.delete_test_match(match_id)

    # -------------------------------------------------------------------------
    # Scenario 14: Invalid input leaves existing results and match status unchanged
    # -------------------------------------------------------------------------
    def test_14_invalid_input_leaves_existing_result_unchanged(self):
        match_id = self.create_test_match()
        try:
            self.set_admin_session()
            # Initial valid result
            csrf1 = self.get_csrf_token(f'/admin/results/{match_id}/edit')
            self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': csrf1,
                'team1_score': '4',
                'team2_score': '1',
                'notes': '_TEST_ Valid 4-1'
            }, follow_redirects=True).close()

            # Attempt invalid update: negative score
            csrf2 = self.get_csrf_token(f'/admin/results/{match_id}/edit')
            res = self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': csrf2,
                'team1_score': '-9',
                'team2_score': '1'
            }, follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            res.close()

            # Check DB is unchanged
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT team1_score, team2_score, winner_team_id FROM results WHERE match_id = %s", (match_id,))
            res_row = cursor.fetchone()
            self.assertEqual(res_row['team1_score'], 4)
            self.assertEqual(res_row['team2_score'], 1)
            self.assertEqual(res_row['winner_team_id'], self.test_teams['_TEST_TEAM_R_1'])
            cursor.close()
            conn.close()
        finally:
            self.delete_test_match(match_id)

    # -------------------------------------------------------------------------
    # Scenario 15: Cancelled matches cannot receive results
    # -------------------------------------------------------------------------
    def test_15_cancelled_matches_cannot_receive_results(self):
        match_id = self.create_test_match(status='cancelled')
        try:
            self.set_admin_session()
            # GET form should redirect with warning
            res_get = self.client.get(f'/admin/results/{match_id}/edit', follow_redirects=True)
            html_get = res_get.data.decode('utf-8')
            res_get.close()
            self.assertIn('match has been cancelled', html_get.lower())

            # POST result should also reject and redirect
            csrf = self.get_csrf_token('/')
            res_post = self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': csrf,
                'team1_score': '1',
                'team2_score': '0'
            }, follow_redirects=True)
            html_post = res_post.data.decode('utf-8')
            res_post.close()
            self.assertIn('match has been cancelled', html_post.lower())

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM results WHERE match_id = %s", (match_id,))
            self.assertIsNone(cursor.fetchone())
            cursor.close()
            conn.close()
        finally:
            self.delete_test_match(match_id)

    # -------------------------------------------------------------------------
    # Scenario 16: Successful result recording sets match to completed
    # -------------------------------------------------------------------------
    def test_16_successful_result_sets_match_completed(self):
        match_id = self.create_test_match(status='ongoing')
        try:
            self.set_admin_session()
            csrf = self.get_csrf_token(f'/admin/results/{match_id}/edit')
            res = self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': csrf,
                'team1_score': '2',
                'team2_score': '0'
            }, follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            res.close()

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT status FROM matches WHERE id = %s", (match_id,))
            m = cursor.fetchone()
            self.assertEqual(m['status'], 'completed')
            cursor.close()
            conn.close()
        finally:
            self.delete_test_match(match_id)

    # -------------------------------------------------------------------------
    # Scenario 17: Database failure rolls back transaction
    # -------------------------------------------------------------------------
    def test_17_database_failure_rolls_back_transaction(self):
        match_id = self.create_test_match(status='scheduled')
        try:
            self.set_admin_session()
            csrf = self.get_csrf_token(f'/admin/results/{match_id}/edit')

            # We simulate a failure on the matches update query within results_edit
            real_conn = get_db_connection()
            real_cursor = real_conn.cursor(dictionary=True)
            original_execute = real_cursor.execute

            def side_effect_execute(sql, *args, **kwargs):
                if "UPDATE matches SET status" in sql:
                    raise MySQLError(1064, "Simulated database syntax error during transaction")
                return original_execute(sql, *args, **kwargs)

            real_cursor.execute = MagicMock(side_effect=side_effect_execute)
            real_conn.cursor = MagicMock(return_value=real_cursor)

            with patch('app.get_db_connection', return_value=real_conn):
                res = self.client.post(f'/admin/results/{match_id}/edit', data={
                    'csrf_token': csrf,
                    'team1_score': '3',
                    'team2_score': '2'
                }, follow_redirects=True)
                html = res.data.decode('utf-8')
                res.close()
                self.assertIn('database error occurred', html.lower())

            # Real connection verify transaction rolled back:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM results WHERE match_id = %s", (match_id,))
            self.assertIsNone(cursor.fetchone(), "Results row should have rolled back")
            cursor.execute("SELECT status FROM matches WHERE id = %s", (match_id,))
            m = cursor.fetchone()
            self.assertEqual(m['status'], 'scheduled', "Match status should have remained 'scheduled'")
            cursor.close()
            conn.close()
        finally:
            self.delete_test_match(match_id)

    # -------------------------------------------------------------------------
    # Scenario 18: GET requests cannot modify results
    # -------------------------------------------------------------------------
    def test_18_get_requests_cannot_modify_results(self):
        match_id = self.create_test_match()
        try:
            self.set_admin_session()
            response = self.client.get(f'/admin/results/{match_id}/edit?team1_score=9&team2_score=0')
            self.assertEqual(response.status_code, 200)
            response.close()

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM results WHERE match_id = %s", (match_id,))
            self.assertIsNone(cursor.fetchone())
            cursor.close()
            conn.close()
        finally:
            self.delete_test_match(match_id)

    # -------------------------------------------------------------------------
    # Scenario 19: POST without valid CSRF token is rejected
    # -------------------------------------------------------------------------
    def test_19_post_without_csrf_token_rejected(self):
        match_id = self.create_test_match()
        try:
            self.set_admin_session()
            # Missing CSRF
            response = self.client.post(f'/admin/results/{match_id}/edit', data={
                'team1_score': '1',
                'team2_score': '0'
            })
            self.assertEqual(response.status_code, 400)
            response.close()

            # Invalid CSRF
            response2 = self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': 'tampered_invalid_token',
                'team1_score': '1',
                'team2_score': '0'
            })
            self.assertEqual(response2.status_code, 400)
            response2.close()
        finally:
            self.delete_test_match(match_id)

    # -------------------------------------------------------------------------
    # Scenario 20: Result listing shows recorded and pending results correctly
    # -------------------------------------------------------------------------
    def test_20_result_listing_shows_recorded_and_pending(self):
        match1 = self.create_test_match(venue='_TEST_Venue_Pending')
        match2 = self.create_test_match(venue='_TEST_Venue_Recorded')

        try:
            self.set_admin_session()
            # Record result for match2
            csrf = self.get_csrf_token(f'/admin/results/{match2}/edit')
            self.client.post(f'/admin/results/{match2}/edit', data={
                'csrf_token': csrf,
                'team1_score': '5',
                'team2_score': '1',
                'notes': '_TEST_ High scoring match'
            }, follow_redirects=True).close()

            response = self.client.get('/admin/results')
            self.assertEqual(response.status_code, 200)
            html = response.data.decode('utf-8')
            response.close()

            self.assertIn('_TEST_Venue_Pending', html)
            self.assertIn('_TEST_Venue_Recorded', html)
            self.assertIn('Pending', html)
            self.assertIn('5 &ndash; 1', html)
        finally:
            self.delete_test_match(match1)
            self.delete_test_match(match2)

    # -------------------------------------------------------------------------
    # Scenario 21: Match details display result, winner/draw, and notes correctly
    # -------------------------------------------------------------------------
    def test_21_match_details_display_result_and_pending(self):
        match_id = self.create_test_match()
        try:
            self.set_admin_session()
            # Before recording result: shows pending state
            res_before = self.client.get(f'/admin/matches/{match_id}')
            self.assertEqual(res_before.status_code, 200)
            html_before = res_before.data.decode('utf-8')
            res_before.close()
            self.assertIn('No result recorded yet', html_before)
            self.assertIn('Record Result', html_before)

            # Record result
            csrf = self.get_csrf_token(f'/admin/results/{match_id}/edit')
            self.client.post(f'/admin/results/{match_id}/edit', data={
                'csrf_token': csrf,
                'team1_score': '3',
                'team2_score': '0',
                'notes': '_TEST_ Comprehensive victory'
            }, follow_redirects=True).close()

            # After recording result: shows score, winner, notes, and Edit Result button
            res_after = self.client.get(f'/admin/matches/{match_id}')
            self.assertEqual(res_after.status_code, 200)
            html_after = res_after.data.decode('utf-8')
            res_after.close()

            self.assertIn('3 &mdash; 0', html_after)
            self.assertIn('Winner: _TEST_TEAM_R_1', html_after)
            self.assertIn('_TEST_ Comprehensive victory', html_after)
            self.assertIn('Edit Result &rarr;', html_after)
        finally:
            self.delete_test_match(match_id)

    # -------------------------------------------------------------------------
    # Scenario 22: Pure Python helper validation unit test
    # -------------------------------------------------------------------------
    def test_22_validate_match_result_helper(self):
        # Unequal scores server-side winner derivation
        ok, err, t1, t2, w, notes = validate_match_result(10, 20, '4', '1', '', '')
        self.assertTrue(ok)
        self.assertEqual(w, 10)
        self.assertEqual(t1, 4)
        self.assertEqual(t2, 1)

        ok, err, t1, t2, w, notes = validate_match_result(10, 20, '1', '5', '', '')
        self.assertTrue(ok)
        self.assertEqual(w, 20)

        # Equal scores ordinary draw
        ok, err, t1, t2, w, notes = validate_match_result(10, 20, '2', '2', '', '')
        self.assertTrue(ok)
        self.assertIsNone(w)

        # Equal scores tie-break with notes
        ok, err, t1, t2, w, notes = validate_match_result(10, 20, '2', '2', '20', 'Penalties 4-3')
        self.assertTrue(ok)
        self.assertEqual(w, 20)
        self.assertEqual(notes, 'Penalties 4-3')

        # Equal scores tie-break WITHOUT notes -> rejected
        ok, err, t1, t2, w, notes = validate_match_result(10, 20, '2', '2', '20', '')
        self.assertFalse(ok)
        self.assertIn('explanatory notes', err)

        # Invalid tie break winner team
        ok, err, t1, t2, w, notes = validate_match_result(10, 20, '2', '2', '99', 'Note')
        self.assertFalse(ok)
        self.assertIn('must be one of the two competing teams', err)

        # Negative scores
        ok, err, t1, t2, w, notes = validate_match_result(10, 20, '-1', '2', '', '')
        self.assertFalse(ok)
        self.assertIn('negative', err.lower())

        # Empty score
        ok, err, t1, t2, w, notes = validate_match_result(10, 20, '', '2', '', '')
        self.assertFalse(ok)
        self.assertIn('scores are required', err.lower())

        # Out of bounds score
        ok, err, t1, t2, w, notes = validate_match_result(10, 20, '70000', '2', '', '')
        self.assertFalse(ok)
        self.assertIn('65,535', err)

    # -------------------------------------------------------------------------
    # Scenario 23: Regression testing for core admin module endpoints
    # -------------------------------------------------------------------------
    def test_23_regression_core_admin_endpoints(self):
        self.set_admin_session()
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/admin/dashboard').status_code, 200)
        self.assertEqual(self.client.get('/admin/sports').status_code, 200)
        self.assertEqual(self.client.get('/admin/teams').status_code, 200)
        self.assertEqual(self.client.get('/admin/players').status_code, 200)
        self.assertEqual(self.client.get('/admin/tournaments').status_code, 200)
        self.assertEqual(self.client.get('/admin/matches').status_code, 200)
        self.assertEqual(self.client.get('/admin/results').status_code, 200)


if __name__ == '__main__':
    unittest.main()
