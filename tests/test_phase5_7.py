import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import re
import unittest
from datetime import datetime, date
from unittest.mock import patch
from app import app, calculate_tournament_standings
from database import get_db_connection


class Phase57StandingsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = cls.app.test_client()
        cls.client.testing = True

        # Clean up any potential leftover test data
        cls.cleanup_test_data()

        # Seed isolated test sports, tournaments, teams, and players
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            # 1. Test Sport: Football
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_SPORT_S_Football', 'Test Football for Standings')
            )
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_SPORT_S_Basketball', 'Test Basketball for Standings')
            )
            conn.commit()

            cursor.execute("SELECT id, name FROM sports WHERE name LIKE '_TEST_SPORT_S_%'")
            sports = {s['name']: s['id'] for s in cursor.fetchall()}
            cls.football_sport_id = sports['_TEST_SPORT_S_Football']
            cls.basketball_sport_id = sports['_TEST_SPORT_S_Basketball']

            # 2. Test Tournaments
            cursor.execute(
                """
                INSERT INTO tournaments (name, sport_id, start_date, end_date, status, description)
                VALUES (%s, %s, %s, %s, 'ongoing', 'Test football tournament')
                """,
                ('_TEST_Tourn_Football_Cup', cls.football_sport_id, '2026-11-01', '2026-11-30')
            )
            cursor.execute(
                """
                INSERT INTO tournaments (name, sport_id, start_date, end_date, status, description)
                VALUES (%s, %s, %s, %s, 'ongoing', 'Test basketball league')
                """,
                ('_TEST_Tourn_Basketball_League', cls.basketball_sport_id, '2026-11-01', '2026-11-30')
            )
            cursor.execute(
                """
                INSERT INTO tournaments (name, sport_id, start_date, end_date, status, description)
                VALUES (%s, %s, %s, %s, 'upcoming', 'Empty tournament without matches')
                """,
                ('_TEST_Tourn_Empty', cls.football_sport_id, '2026-12-01', '2026-12-31')
            )
            conn.commit()

            cursor.execute("SELECT id, name FROM tournaments WHERE name LIKE '_TEST_Tourn_%'")
            tournaments = {t['name']: t['id'] for t in cursor.fetchall()}
            cls.football_tourn_id = tournaments['_TEST_Tourn_Football_Cup']
            cls.basketball_tourn_id = tournaments['_TEST_Tourn_Basketball_League']
            cls.empty_tourn_id = tournaments['_TEST_Tourn_Empty']

            # 3. Test Teams in Football (Teams A, B, C, and D)
            cursor.execute("INSERT INTO teams (name, sport_id) VALUES (%s, %s)", ('_TEST_TEAM_A', cls.football_sport_id))
            cursor.execute("INSERT INTO teams (name, sport_id) VALUES (%s, %s)", ('_TEST_TEAM_B', cls.football_sport_id))
            cursor.execute("INSERT INTO teams (name, sport_id) VALUES (%s, %s)", ('_TEST_TEAM_C', cls.football_sport_id))
            cursor.execute("INSERT INTO teams (name, sport_id) VALUES (%s, %s)", ('_TEST_TEAM_D_NoPlay', cls.football_sport_id))

            # Basketball Teams (X and Y)
            cursor.execute("INSERT INTO teams (name, sport_id) VALUES (%s, %s)", ('_TEST_TEAM_BB_X', cls.basketball_sport_id))
            cursor.execute("INSERT INTO teams (name, sport_id) VALUES (%s, %s)", ('_TEST_TEAM_BB_Y', cls.basketball_sport_id))
            conn.commit()

            cursor.execute("SELECT id, name FROM teams WHERE name LIKE '_TEST_TEAM_%'")
            cls.test_teams = {t['name']: t['id'] for t in cursor.fetchall()}

            # 4. Test Players
            cursor.execute(
                """
                INSERT INTO players (full_name, sport_id, team_id, jersey_number, date_of_birth, gender)
                VALUES (%s, %s, %s, %s, '2000-01-01', 'male')
                """,
                ('_TEST_Player_Striker', cls.football_sport_id, cls.test_teams['_TEST_TEAM_A'], 9)
            )
            cursor.execute(
                """
                INSERT INTO players (full_name, sport_id, team_id, jersey_number, date_of_birth, gender)
                VALUES (%s, %s, %s, %s, '2001-02-02', 'male')
                """,
                ('_TEST_Player_Playmaker', cls.football_sport_id, cls.test_teams['_TEST_TEAM_A'], 10)
            )
            conn.commit()

            cursor.execute("SELECT id, full_name FROM players WHERE full_name LIKE '_TEST_Player_%'")
            cls.test_players = {p['full_name']: p['id'] for p in cursor.fetchall()}

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
            # Clean in dependency order
            cursor.execute(
                """
                DELETE pms FROM player_match_stats pms
                JOIN matches m ON pms.match_id = m.id
                WHERE m.venue LIKE '_TEST_%'
                """
            )
            cursor.execute("DELETE FROM player_match_stats WHERE player_id IN (SELECT id FROM players WHERE full_name LIKE '_TEST_%')")
            cursor.execute(
                """
                DELETE r FROM results r
                JOIN matches m ON r.match_id = m.id
                WHERE m.venue LIKE '_TEST_%' OR r.notes LIKE '_TEST_%'
                """
            )
            cursor.execute("DELETE FROM results WHERE notes LIKE '_TEST_%'")
            cursor.execute("DELETE FROM matches WHERE venue LIKE '_TEST_%'")
            cursor.execute("DELETE FROM players WHERE full_name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM tournaments WHERE name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM teams WHERE name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM sports WHERE name LIKE '_TEST_SPORT_S_%'")
            conn.commit()
            cursor.close()
            conn.close()

    def setUp(self):
        self.clear_session()

    def tearDown(self):
        self.clear_session()

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

    def create_match_fixture(self, tourn_id, t1_id, t2_id, status='completed', venue='_TEST_Venue_Std'):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            INSERT INTO matches (tournament_id, team1_id, team2_id, match_datetime, venue, status)
            VALUES (%s, %s, %s, '2026-11-10 14:00:00', %s, %s)
            """,
            (tourn_id, t1_id, t2_id, venue, status)
        )
        conn.commit()
        match_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return match_id

    def record_match_result(self, match_id, s1, s2, winner_id=None, notes=None):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO results (match_id, team1_score, team2_score, winner_team_id, notes)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (match_id, s1, s2, winner_id, notes)
        )
        conn.commit()
        cursor.close()
        conn.close()

    def record_player_stats(self, player_id, match_id, goals=0, assists=0, points=0):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO player_match_stats (player_id, match_id, goals, assists, points)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (player_id, match_id, goals, assists, points)
        )
        conn.commit()
        cursor.close()
        conn.close()

    # -------------------------------------------------------------------------
    # Scenario 1: Admin can access standings
    # -------------------------------------------------------------------------
    def test_01_admin_can_access_standings(self):
        self.set_admin_session()
        response = self.client.get(f'/admin/tournaments/{self.football_tourn_id}/standings')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('Tournament Standings', html)
        self.assertIn('_TEST_Tourn_Football_Cup', html)

    # -------------------------------------------------------------------------
    # Scenario 2: Unauthenticated visitors redirected to login
    # -------------------------------------------------------------------------
    def test_02_unauthenticated_visitor_redirected(self):
        self.clear_session()
        response = self.client.get(f'/admin/tournaments/{self.football_tourn_id}/standings')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers.get('Location', ''))
        response.close()

        res_redir = self.client.get('/admin/standings')
        self.assertEqual(res_redir.status_code, 302)
        self.assertIn('/login', res_redir.headers.get('Location', ''))
        res_redir.close()

    # -------------------------------------------------------------------------
    # Scenario 3: Logged-in non-admin player receives 403
    # -------------------------------------------------------------------------
    @patch('auth.get_current_user')
    def test_03_authenticated_player_forbidden(self, mock_user):
        mock_user.return_value = {
            'id': 999, 'username': 'test_player', 'email': 'player@test.com', 'role': 'player', 'is_active': 1
        }
        self.set_player_session()
        response = self.client.get(f'/admin/tournaments/{self.football_tourn_id}/standings')
        self.assertEqual(response.status_code, 403)
        response.close()

        res2 = self.client.get('/admin/standings')
        self.assertEqual(res2.status_code, 403)
        response.close()

    # -------------------------------------------------------------------------
    # Scenario 4: Invalid or nonexistent tournament IDs return 404
    # -------------------------------------------------------------------------
    def test_04_missing_tournament_returns_404(self):
        self.set_admin_session()
        response = self.client.get('/admin/tournaments/999999/standings')
        self.assertEqual(response.status_code, 404)
        response.close()

    # -------------------------------------------------------------------------
    # Scenario 5: Tournament with no completed matches displays empty state
    # -------------------------------------------------------------------------
    def test_05_empty_tournament_displays_empty_state(self):
        self.set_admin_session()
        response = self.client.get(f'/admin/tournaments/{self.empty_tourn_id}/standings')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('No Qualifying Match Results Yet', html)
        self.assertIn('No Player Statistics Recorded Yet', html)

    # -------------------------------------------------------------------------
    # Scenarios 6 & 7: Scheduled, ongoing, cancelled, and result-less matches excluded
    # -------------------------------------------------------------------------
    def test_06_and_07_ineligible_matches_excluded(self):
        # Create fixtures with various ineligible states
        tA = self.test_teams['_TEST_TEAM_A']
        tB = self.test_teams['_TEST_TEAM_B']

        m_scheduled = self.create_match_fixture(self.football_tourn_id, tA, tB, status='scheduled')
        m_ongoing = self.create_match_fixture(self.football_tourn_id, tA, tB, status='ongoing')
        m_cancelled = self.create_match_fixture(self.football_tourn_id, tA, tB, status='cancelled')
        self.record_match_result(m_cancelled, 2, 0, tA, notes='_TEST_ Cancelled match result')

        m_completed_no_result = self.create_match_fixture(self.football_tourn_id, tA, tB, status='completed')

        try:
            self.set_admin_session()
            response = self.client.get(f'/admin/tournaments/{self.football_tourn_id}/standings')
            self.assertEqual(response.status_code, 200)
            html = response.data.decode('utf-8')
            response.close()

            # Should still show empty state because no qualifying matches exist
            self.assertIn('No Qualifying Match Results Yet', html)
            self.assertIn('0', html)  # 0 completed matches with valid results
        finally:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM results WHERE match_id IN (%s, %s, %s, %s)", (m_scheduled, m_ongoing, m_cancelled, m_completed_no_result))
            cur.execute("DELETE FROM matches WHERE id IN (%s, %s, %s, %s)", (m_scheduled, m_ongoing, m_cancelled, m_completed_no_result))
            conn.commit()
            cur.close()
            conn.close()

    # -------------------------------------------------------------------------
    # Scenarios 8, 9, 10, 11, 12: Decisive wins, draws, tie-break outcomes, totals
    # -------------------------------------------------------------------------
    def test_08_to_12_standings_calculations_and_tie_breaks(self):
        tA = self.test_teams['_TEST_TEAM_A']
        tB = self.test_teams['_TEST_TEAM_B']
        tC = self.test_teams['_TEST_TEAM_C']

        # Match 1: Team A 3 - 1 Team B (Decisive win Team A)
        m1 = self.create_match_fixture(self.football_tourn_id, tA, tB, status='completed')
        self.record_match_result(m1, 3, 1, winner_id=tA, notes='_TEST_ Match 1')

        # Match 2: Team B 2 - 2 Team C (Ordinary Draw, winner NULL)
        m2 = self.create_match_fixture(self.football_tourn_id, tB, tC, status='completed')
        self.record_match_result(m2, 2, 2, winner_id=None, notes='_TEST_ Match 2')

        # Match 3: Team A 1 - 1 Team C (Tie-Break win Team C, equal scores)
        m3 = self.create_match_fixture(self.football_tourn_id, tA, tC, status='completed')
        self.record_match_result(m3, 1, 1, winner_id=tC, notes='_TEST_ Team C won 5-4 on penalty shootout')

        try:
            self.set_admin_session()
            response = self.client.get(f'/admin/tournaments/{self.football_tourn_id}/standings')
            self.assertEqual(response.status_code, 200)
            html = response.data.decode('utf-8')
            response.close()

            # Verify participating teams in HTML
            self.assertIn('_TEST_TEAM_A', html)
            self.assertIn('_TEST_TEAM_B', html)
            self.assertIn('_TEST_TEAM_C', html)

            # Scenario 12: Team D (never played) must NOT appear in standings table
            self.assertNotIn('_TEST_TEAM_D_NoPlay', html)

            # Verify calculations via pure helper function directly
            matches_data = [
                {'team1_id': tA, 'team1_name': 'Team A', 'team2_id': tB, 'team2_name': 'Team B', 'team1_score': 3, 'team2_score': 1, 'winner_team_id': tA, 'notes': ''},
                {'team1_id': tB, 'team1_name': 'Team B', 'team2_id': tC, 'team2_name': 'Team C', 'team1_score': 2, 'team2_score': 2, 'winner_team_id': None, 'notes': ''},
                {'team1_id': tA, 'team1_name': 'Team A', 'team2_id': tC, 'team2_name': 'Team C', 'team1_score': 1, 'team2_score': 1, 'winner_team_id': tC, 'notes': 'Penalties'},
            ]
            standings, info = calculate_tournament_standings('FootBall', matches_data)

            # Map results by team_id
            s_map = {row['team_id']: row for row in standings}

            # Team A:
            # Played: 2 (M1, M3)
            # Wins: 1 (regulation M1), Draws: 0, Losses: 0
            # Tie-break Wins: 0, Tie-break Losses: 1 (M3)
            # Total Wins: 1, Total Losses: 1
            # Score For: 3 + 1 = 4, Score Against: 1 + 1 = 2, Score Diff = +2
            # Football Points: (1 win * 3) + (0 * 3) + (0 * 1) = 3 pts
            self.assertEqual(s_map[tA]['played'], 2)
            self.assertEqual(s_map[tA]['wins'], 1)
            self.assertEqual(s_map[tA]['draws'], 0)
            self.assertEqual(s_map[tA]['losses'], 0)
            self.assertEqual(s_map[tA]['tie_break_wins'], 0)
            self.assertEqual(s_map[tA]['tie_break_losses'], 1)
            self.assertEqual(s_map[tA]['score_for'], 4)
            self.assertEqual(s_map[tA]['score_against'], 2)
            self.assertEqual(s_map[tA]['score_diff'], 2)
            self.assertEqual(s_map[tA]['points'], 3)

            # Team C:
            # Played: 2 (M2, M3)
            # Wins: 0, Draws: 1 (M2), Losses: 0
            # Tie-break Wins: 1 (M3), Tie-break Losses: 0
            # Total Wins: 1, Total Losses: 0
            # Score For: 2 + 1 = 3, Score Against: 2 + 1 = 3, Score Diff = 0
            # Football Points: (0 * 3) + (1 tb win * 3) + (1 draw * 1) = 4 pts
            self.assertEqual(s_map[tC]['played'], 2)
            self.assertEqual(s_map[tC]['wins'], 0)
            self.assertEqual(s_map[tC]['draws'], 1)
            self.assertEqual(s_map[tC]['losses'], 0)
            self.assertEqual(s_map[tC]['tie_break_wins'], 1)
            self.assertEqual(s_map[tC]['tie_break_losses'], 0)
            self.assertEqual(s_map[tC]['score_for'], 3)
            self.assertEqual(s_map[tC]['score_against'], 3)
            self.assertEqual(s_map[tC]['score_diff'], 0)
            self.assertEqual(s_map[tC]['points'], 4)

            # Team B:
            # Played: 2 (M1, M2)
            # Wins: 0, Draws: 1 (M2), Losses: 1 (M1)
            # Score For: 1 + 2 = 3, Score Against: 3 + 2 = 5, Score Diff = -2
            # Football Points: 0 + 0 + 1 = 1 pt
            self.assertEqual(s_map[tB]['played'], 2)
            self.assertEqual(s_map[tB]['wins'], 0)
            self.assertEqual(s_map[tB]['draws'], 1)
            self.assertEqual(s_map[tB]['losses'], 1)
            self.assertEqual(s_map[tB]['score_diff'], -2)
            self.assertEqual(s_map[tB]['points'], 1)

            # Ordering in football:
            # 1st: Team C (4 pts)
            # 2nd: Team A (3 pts)
            # 3rd: Team B (1 pt)
            self.assertEqual(standings[0]['team_id'], tC)
            self.assertEqual(standings[1]['team_id'], tA)
            self.assertEqual(standings[2]['team_id'], tB)
        finally:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM results WHERE match_id IN (%s, %s, %s)", (m1, m2, m3))
            cur.execute("DELETE FROM matches WHERE id IN (%s, %s, %s)", (m1, m2, m3))
            conn.commit()
            cur.close()
            conn.close()

    # -------------------------------------------------------------------------
    # Scenarios 13 & 14: Player stats aggregated without duplicates; excluded if ineligible
    # -------------------------------------------------------------------------
    def test_13_and_14_player_stats_aggregation(self):
        tA = self.test_teams['_TEST_TEAM_A']
        tB = self.test_teams['_TEST_TEAM_B']
        p_striker = self.test_players['_TEST_Player_Striker']
        p_playmaker = self.test_players['_TEST_Player_Playmaker']

        # Qualifying Match 1: completed with result
        m1 = self.create_match_fixture(self.football_tourn_id, tA, tB, status='completed')
        self.record_match_result(m1, 2, 0, winner_id=tA, notes='_TEST_ M1')
        self.record_player_stats(p_striker, m1, goals=2, assists=0, points=0)
        self.record_player_stats(p_playmaker, m1, goals=0, assists=2, points=0)

        # Ineligible Match 2: cancelled with stats recorded
        m2 = self.create_match_fixture(self.football_tourn_id, tA, tB, status='cancelled')
        self.record_player_stats(p_striker, m2, goals=5, assists=0, points=0)

        # Ineligible Match 3: completed but NO result record
        m3 = self.create_match_fixture(self.football_tourn_id, tA, tB, status='completed')
        self.record_player_stats(p_striker, m3, goals=3, assists=0, points=0)

        try:
            self.set_admin_session()
            response = self.client.get(f'/admin/tournaments/{self.football_tourn_id}/standings')
            self.assertEqual(response.status_code, 200)
            html = response.data.decode('utf-8')
            response.close()

            # Striker should have only 2 goals from Match 1 (5 from cancelled and 3 from result-less match excluded)
            self.assertIn('_TEST_Player_Striker', html)
            self.assertIn('_TEST_Player_Playmaker', html)
            self.assertIn('Top Goalscorers', html)
            self.assertIn('Top Assists', html)

            # Query database directly using helper to verify aggregated numbers
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            from app import get_tournament_leaderboards
            lb = get_tournament_leaderboards(self.football_tourn_id, 'FootBall', cur)
            cur.close()
            conn.close()

            striker_stat = next(p for p in lb['goals'] if p['player_id'] == p_striker)
            self.assertEqual(striker_stat['total_goals'], 2)
            self.assertEqual(striker_stat['matches_played'], 1)

            playmaker_stat = next(p for p in lb['assists'] if p['player_id'] == p_playmaker)
            self.assertEqual(playmaker_stat['total_assists'], 2)
            self.assertEqual(playmaker_stat['matches_played'], 1)
        finally:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM player_match_stats WHERE match_id IN (%s, %s, %s)", (m1, m2, m3))
            cur.execute("DELETE FROM results WHERE match_id = %s", (m1,))
            cur.execute("DELETE FROM matches WHERE id IN (%s, %s, %s)", (m1, m2, m3))
            conn.commit()
            cur.close()
            conn.close()

    # -------------------------------------------------------------------------
    # Scenario 15: Tied statistics are ordered deterministically
    # -------------------------------------------------------------------------
    def test_15_tied_statistics_ordered_consistently(self):
        # Two teams with identical scores and results
        matches = [
            {'team1_id': 101, 'team1_name': 'Beta Team', 'team2_id': 102, 'team2_name': 'Alpha Team', 'team1_score': 1, 'team2_score': 1, 'winner_team_id': None, 'notes': ''}
        ]
        standings, info = calculate_tournament_standings('FootBall', matches)
        # Both have 1 pt, 0 GD, 1 GF.
        # Alphabetical team name should break the tie: Alpha Team before Beta Team
        self.assertEqual(standings[0]['team_name'], 'Alpha Team')
        self.assertEqual(standings[1]['team_name'], 'Beta Team')

    # -------------------------------------------------------------------------
    # Scenario 16: Standings and leaderboards do not modify results
    # -------------------------------------------------------------------------
    def test_16_views_do_not_modify_existing_data(self):
        tA = self.test_teams['_TEST_TEAM_A']
        tB = self.test_teams['_TEST_TEAM_B']
        m = self.create_match_fixture(self.football_tourn_id, tA, tB, status='completed')
        self.record_match_result(m, 2, 1, winner_id=tA, notes='_TEST_ Immutable result')

        try:
            self.set_admin_session()
            self.client.get(f'/admin/tournaments/{self.football_tourn_id}/standings').close()

            # Check DB row is completely intact
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM results WHERE match_id = %s", (m,))
            res = cur.fetchone()
            self.assertEqual(res['team1_score'], 2)
            self.assertEqual(res['team2_score'], 1)
            self.assertEqual(res['winner_team_id'], tA)
            self.assertEqual(res['notes'], '_TEST_ Immutable result')
            cur.close()
            conn.close()
        finally:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM results WHERE match_id = %s", (m,))
            cur.execute("DELETE FROM matches WHERE id = %s", (m,))
            conn.commit()
            cur.close()
            conn.close()

    # -------------------------------------------------------------------------
    # Scenario 17: Non-football sports handle unconfigured points gracefully
    # -------------------------------------------------------------------------
    def test_17_non_football_sports_handle_unconfigured_points(self):
        tX = self.test_teams['_TEST_TEAM_BB_X']
        tY = self.test_teams['_TEST_TEAM_BB_Y']
        m_bb = self.create_match_fixture(self.basketball_tourn_id, tX, tY, status='completed')
        self.record_match_result(m_bb, 88, 75, winner_id=tX, notes='_TEST_ Basketball game')

        try:
            self.set_admin_session()
            response = self.client.get(f'/admin/tournaments/{self.basketball_tourn_id}/standings')
            self.assertEqual(response.status_code, 200)
            html = response.data.decode('utf-8')
            response.close()

            self.assertIn('N/A', html)
            self.assertIn('PF', html)
            self.assertIn('PA', html)
            self.assertIn('PD', html)
            self.assertIn('not configured', html.lower())
        finally:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM results WHERE match_id = %s", (m_bb,))
            cur.execute("DELETE FROM matches WHERE id = %s", (m_bb,))
            conn.commit()
            cur.close()
            conn.close()

    # -------------------------------------------------------------------------
    # Scenario 18: Standings redirect convenience route
    # -------------------------------------------------------------------------
    def test_18_standings_redirect_route(self):
        self.set_admin_session()
        response = self.client.get('/admin/standings')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/standings', response.headers.get('Location', ''))
        response.close()


if __name__ == '__main__':
    unittest.main()
