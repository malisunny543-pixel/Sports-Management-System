import csv
import io
import re
import unittest
from datetime import datetime, date
from app import app
from database import get_db_connection
from werkzeug.security import generate_password_hash


class Phase8ReportsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = cls.app.test_client()
        cls.client.testing = True

        # Clean up any potential leftover test data
        cls.cleanup_test_data()

        # Seed isolated test records: sports, teams, users, players, tournaments, matches, results, stats
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)

            # 1. Sport
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_SPORT_R_Football', 'Football for Reports Testing')
            )
            conn.commit()
            cursor.execute("SELECT id FROM sports WHERE name = '_TEST_SPORT_R_Football'")
            cls.sport_id = cursor.fetchone()['id']

            # 2. Teams
            cursor.execute("INSERT INTO teams (name, sport_id) VALUES (%s, %s)", ('_TEST_TEAM_R_Alpha', cls.sport_id))
            cursor.execute("INSERT INTO teams (name, sport_id) VALUES (%s, %s)", ('_TEST_TEAM_R_Beta', cls.sport_id))
            conn.commit()
            cursor.execute("SELECT id FROM teams WHERE name = '_TEST_TEAM_R_Alpha'")
            cls.team_alpha_id = cursor.fetchone()['id']
            cursor.execute("SELECT id FROM teams WHERE name = '_TEST_TEAM_R_Beta'")
            cls.team_beta_id = cursor.fetchone()['id']

            # 3. Users (Admin and Player)
            pwd_hash = generate_password_hash('Password123!')
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'admin', 1)
                """,
                ('_TEST_admin_rep', '_test_admin_rep@example.com', pwd_hash)
            )
            cls.admin_user_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 1)
                """,
                ('_TEST_player_rep', '_test_player_rep@example.com', pwd_hash)
            )
            cls.player_user_id = cursor.lastrowid
            conn.commit()

            # 4. Players
            cursor.execute(
                """
                INSERT INTO players (full_name, date_of_birth, gender, sport_id, team_id, jersey_number, user_id)
                VALUES (%s, %s, 'male', %s, %s, 10, %s)
                """,
                ('_TEST_Striker_Alex', '2000-01-01', cls.sport_id, cls.team_alpha_id, cls.player_user_id)
            )
            cls.player_alex_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO players (full_name, date_of_birth, gender, sport_id, team_id, jersey_number, user_id)
                VALUES (%s, %s, 'female', %s, %s, 7, NULL)
                """,
                ('_TEST_Midfielder_Bea', '2001-02-02', cls.sport_id, cls.team_beta_id)
            )
            cls.player_bea_id = cursor.lastrowid
            conn.commit()

            # 5. Tournaments (Active Tournament & Empty Tournament)
            cursor.execute(
                """
                INSERT INTO tournaments (name, sport_id, start_date, end_date, status, description)
                VALUES (%s, %s, '2026-11-01', '2026-11-30', 'ongoing', 'Tournament for Reports Verification')
                """,
                ('_TEST_Tournament_Reports', cls.sport_id)
            )
            cls.tournament_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO tournaments (name, sport_id, start_date, end_date, status, description)
                VALUES (%s, %s, '2026-12-01', '2026-12-31', 'upcoming', 'Empty Tournament with zero matches')
                """,
                ('_TEST_Tournament_Empty', cls.sport_id)
            )
            cls.empty_tournament_id = cursor.lastrowid
            conn.commit()

            # 6. Matches
            # Match 1: Completed with Result (Alpha 3 - 1 Beta)
            cursor.execute(
                """
                INSERT INTO matches (tournament_id, team1_id, team2_id, match_datetime, venue, status)
                VALUES (%s, %s, %s, '2026-11-10 14:00:00', '_TEST_Venue_One', 'completed')
                """,
                (cls.tournament_id, cls.team_alpha_id, cls.team_beta_id)
            )
            cls.match_completed_id = cursor.lastrowid

            # Result for Match 1
            cursor.execute(
                """
                INSERT INTO results (match_id, team1_score, team2_score, winner_team_id)
                VALUES (%s, 3, 1, %s)
                """,
                (cls.match_completed_id, cls.team_alpha_id)
            )

            # Match 2: Completed WITHOUT Result (pending result entry)
            cursor.execute(
                """
                INSERT INTO matches (tournament_id, team1_id, team2_id, match_datetime, venue, status)
                VALUES (%s, %s, %s, '2026-11-15 16:00:00', '_TEST_Venue_Two', 'completed')
                """,
                (cls.tournament_id, cls.team_beta_id, cls.team_alpha_id)
            )
            cls.match_unrecorded_id = cursor.lastrowid

            # Match 3: Scheduled (Upcoming)
            cursor.execute(
                """
                INSERT INTO matches (tournament_id, team1_id, team2_id, match_datetime, venue, status)
                VALUES (%s, %s, %s, '2026-11-20 18:00:00', '_TEST_Venue_Three', 'scheduled')
                """,
                (cls.tournament_id, cls.team_alpha_id, cls.team_beta_id)
            )
            cls.match_upcoming_id = cursor.lastrowid
            conn.commit()

            # 7. Player Match Stats for Match 1 (Alex: 2 goals, 1 assist; Bea: 1 goal)
            cursor.execute(
                """
                INSERT INTO player_match_stats (player_id, match_id, goals, assists, points)
                VALUES (%s, %s, 2, 1, 0)
                """,
                (cls.player_alex_id, cls.match_completed_id)
            )
            cursor.execute(
                """
                INSERT INTO player_match_stats (player_id, match_id, goals, assists, points)
                VALUES (%s, %s, 1, 0, 0)
                """,
                (cls.player_bea_id, cls.match_completed_id)
            )
            conn.commit()

            cursor.close()
            conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.cleanup_test_data()

    @classmethod
    def cleanup_test_data(cls):
        """Safely cleans up all records starting with '_TEST_%' in child-to-parent order."""
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
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

    def set_admin_session(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin_user_id
            sess['username'] = '_TEST_admin_rep'
            sess['role'] = 'admin'

    def set_player_session(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.player_user_id
            sess['username'] = '_TEST_player_rep'
            sess['role'] = 'player'

    def clear_session(self):
        with self.client.session_transaction() as sess:
            sess.clear()

    # -------------------------------------------------------------------------
    # Scenario 1: Unauthenticated access redirects to /login
    # -------------------------------------------------------------------------
    def test_01_unauthenticated_access_redirects_to_login(self):
        self.clear_session()
        endpoints = [
            '/admin/reports',
            f'/admin/reports/export/standings?tournament_id={self.tournament_id}',
            '/admin/reports/export/matches',
            '/admin/reports/export/players',
            '/admin/reports/export/teams',
        ]
        for ep in endpoints:
            res = self.client.get(ep)
            self.assertEqual(res.status_code, 302, f"Failed on {ep}")
            self.assertIn('/login', res.headers.get('Location', ''))

    # -------------------------------------------------------------------------
    # Scenario 2: Player access returns 403 Forbidden
    # -------------------------------------------------------------------------
    def test_02_player_cannot_access_reports_or_exports(self):
        self.set_player_session()
        endpoints = [
            '/admin/reports',
            f'/admin/reports/export/standings?tournament_id={self.tournament_id}',
            '/admin/reports/export/matches',
            '/admin/reports/export/players',
            '/admin/reports/export/teams',
        ]
        for ep in endpoints:
            res = self.client.get(ep)
            self.assertEqual(res.status_code, 403, f"Failed on {ep}")

    # -------------------------------------------------------------------------
    # Scenario 3: Admin can access reports dashboard
    # -------------------------------------------------------------------------
    def test_03_admin_can_access_reports_dashboard(self):
        self.set_admin_session()
        res = self.client.get('/admin/reports')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        self.assertIn('Reports &amp; Analytics', html)
        self.assertIn('System Overview', html)
        self.assertIn('id="metric-total-sports"', html)
        self.assertIn('id="metric-total-teams"', html)
        self.assertIn('id="metric-total-players"', html)
        self.assertIn('id="metric-total-tournaments"', html)
        self.assertIn('id="metric-total-matches"', html)
        self.assertIn('id="metric-completed-matches"', html)
        self.assertIn('id="metric-upcoming-matches"', html)
        self.assertIn('id="metric-unrecorded-matches"', html)

    # -------------------------------------------------------------------------
    # Scenario 4: Reports dashboard displays correct summary counts
    # -------------------------------------------------------------------------
    def test_04_reports_dashboard_metrics_counts(self):
        self.set_admin_session()
        res = self.client.get('/admin/reports')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # Connect to DB to get exact ground truth counts
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)
        c.execute("SELECT COUNT(*) AS cnt FROM sports")
        sports_cnt = c.fetchone()['cnt']
        c.execute("SELECT COUNT(*) AS cnt FROM teams")
        teams_cnt = c.fetchone()['cnt']
        c.execute("SELECT COUNT(*) AS cnt FROM players")
        players_cnt = c.fetchone()['cnt']
        c.execute("SELECT COUNT(*) AS cnt FROM tournaments")
        tourn_cnt = c.fetchone()['cnt']
        c.execute("SELECT COUNT(*) AS cnt FROM matches")
        matches_cnt = c.fetchone()['cnt']
        c.execute("SELECT COUNT(*) AS cnt FROM matches WHERE status = 'completed'")
        comp_cnt = c.fetchone()['cnt']
        c.execute("SELECT COUNT(*) AS cnt FROM matches WHERE status IN ('scheduled', 'ongoing')")
        upc_cnt = c.fetchone()['cnt']
        c.execute("SELECT COUNT(*) AS cnt FROM matches m LEFT JOIN results r ON r.match_id = m.id WHERE r.id IS NULL")
        unrec_cnt = c.fetchone()['cnt']
        c.close()
        conn.close()

        self.assertIn(f'id="metric-total-sports">\n                {sports_cnt}', html)
        self.assertIn(f'id="metric-total-teams">\n                {teams_cnt}', html)
        self.assertIn(f'id="metric-total-players">\n                {players_cnt}', html)
        self.assertIn(f'id="metric-total-tournaments">\n                {tourn_cnt}', html)
        self.assertIn(f'id="metric-total-matches">\n                {matches_cnt}', html)
        self.assertIn(f'id="metric-completed-matches">\n                {comp_cnt}', html)
        self.assertIn(f'id="metric-upcoming-matches">\n                {upc_cnt}', html)
        self.assertIn(f'id="metric-unrecorded-matches">\n                {unrec_cnt}', html)

    # -------------------------------------------------------------------------
    # Scenario 5: Tournament report filtering displays standings, fixtures, results
    # -------------------------------------------------------------------------
    def test_05_tournament_reports_filtering(self):
        self.set_admin_session()
        res = self.client.get(f'/admin/reports?tournament_id={self.tournament_id}')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # Tournament details
        self.assertIn('_TEST_Tournament_Reports', html)
        self.assertIn('_TEST_SPORT_R_Football', html)

        # Standings table present with team Alpha (Winner: 3 pts) and team Beta (0 pts)
        self.assertIn('id="tournament-standings-table"', html)
        self.assertIn('_TEST_TEAM_R_Alpha', html)
        self.assertIn('_TEST_TEAM_R_Beta', html)
        self.assertIn(f'id="standings-pts-{self.team_alpha_id}">3<', html)
        self.assertIn(f'id="standings-pts-{self.team_beta_id}">0<', html)

        # Match fixtures present with completed result, pending result, and upcoming
        self.assertIn('id="tournament-matches-table"', html)
        self.assertIn('3 &ndash; 1', html)
        self.assertIn('Result Pending', html)
        self.assertIn('scheduled', html)

        # Participating teams
        self.assertIn('Participating Teams', html)
        self.assertIn('_TEST_TEAM_R_Alpha', html)
        self.assertIn('_TEST_TEAM_R_Beta', html)

    # -------------------------------------------------------------------------
    # Scenario 6: Empty tournament displays graceful empty states
    # -------------------------------------------------------------------------
    def test_06_empty_tournament_handled_gracefully(self):
        self.set_admin_session()
        res = self.client.get(f'/admin/reports?tournament_id={self.empty_tournament_id}')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        self.assertIn('_TEST_Tournament_Empty', html)
        self.assertIn('No completed match results have been recorded for this tournament yet', html)
        self.assertIn('No matches have been scheduled for this tournament yet', html)

    # -------------------------------------------------------------------------
    # Scenario 7: Standings consistency with Phase 5.7 calculations
    # -------------------------------------------------------------------------
    def test_07_standings_consistency_with_phase_5_7(self):
        self.set_admin_session()
        res_reports = self.client.get(f'/admin/reports?tournament_id={self.tournament_id}')
        res_standings = self.client.get(f'/admin/tournaments/{self.tournament_id}/standings')

        self.assertEqual(res_reports.status_code, 200)
        self.assertEqual(res_standings.status_code, 200)

        html_reports = res_reports.data.decode('utf-8')
        html_standings = res_standings.data.decode('utf-8')

        # Both pages must display identical points for Team Alpha (3 pts) and Team Beta (0 pts)
        self.assertIn(f'id="standings-pts-{self.team_alpha_id}">3<', html_reports)
        self.assertIn(f'id="standings-pts-{self.team_beta_id}">0<', html_reports)

        # In Phase 5.7 standings page, verify team rows and points
        self.assertIn(f'data-team-id="{self.team_alpha_id}"', html_standings)
        self.assertIn(f'data-team-id="{self.team_beta_id}"', html_standings)
        self.assertIn('_TEST_TEAM_R_Alpha', html_standings)
        self.assertIn('_TEST_TEAM_R_Beta', html_standings)

    # -------------------------------------------------------------------------
    # Scenario 8: CSV Export — Tournament Standings
    # -------------------------------------------------------------------------
    def test_08_export_standings_csv(self):
        self.set_admin_session()
        res = self.client.get(f'/admin/reports/export/standings?tournament_id={self.tournament_id}')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('Content-Type'), 'text/csv; charset=utf-8')
        self.assertIn('attachment; filename="standings_tournament_', res.headers.get('Content-Disposition', ''))

        csv_text = res.data.decode('utf-8')
        reader = list(csv.reader(io.StringIO(csv_text)))
        self.assertGreaterEqual(len(reader), 3)  # Headers + at least 2 teams

        headers = reader[0]
        self.assertIn('Rank', headers)
        self.assertIn('Team Name', headers)
        self.assertIn('Points', headers)

        # Team Alpha should be Rank 1 with 3 points
        team_alpha_row = [r for r in reader[1:] if r[1] == '_TEST_TEAM_R_Alpha'][0]
        self.assertEqual(team_alpha_row[0], '1')
        self.assertEqual(team_alpha_row[-1], '3')

    # -------------------------------------------------------------------------
    # Scenario 9: CSV Export — Matches
    # -------------------------------------------------------------------------
    def test_09_export_matches_csv(self):
        self.set_admin_session()

        # Export for specific tournament
        res_tourn = self.client.get(f'/admin/reports/export/matches?tournament_id={self.tournament_id}')
        self.assertEqual(res_tourn.status_code, 200)
        self.assertEqual(res_tourn.headers.get('Content-Type'), 'text/csv; charset=utf-8')
        self.assertIn(f'matches_report_tournament_{self.tournament_id}.csv', res_tourn.headers.get('Content-Disposition', ''))

        csv_text = res_tourn.data.decode('utf-8')
        reader = list(csv.reader(io.StringIO(csv_text)))
        self.assertEqual(len(reader), 4)  # Headers + 3 matches

        headers = reader[0]
        self.assertIn('Match ID', headers)
        self.assertIn('Tournament', headers)
        self.assertIn('Venue', headers)
        self.assertIn('Result Recorded', headers)

        # Export for all matches
        res_all = self.client.get('/admin/reports/export/matches')
        self.assertEqual(res_all.status_code, 200)
        self.assertIn('matches_report_all.csv', res_all.headers.get('Content-Disposition', ''))

    # -------------------------------------------------------------------------
    # Scenario 10: CSV Export — Players Statistics (Sensitive data excluded)
    # -------------------------------------------------------------------------
    def test_10_export_players_csv_sensitive_data_excluded(self):
        self.set_admin_session()
        res = self.client.get('/admin/reports/export/players')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('Content-Type'), 'text/csv; charset=utf-8')
        self.assertIn('player_statistics_report.csv', res.headers.get('Content-Disposition', ''))

        csv_text = res.data.decode('utf-8')
        reader = list(csv.reader(io.StringIO(csv_text)))
        self.assertGreaterEqual(len(reader), 2)  # Headers + rows

        headers = reader[0]
        self.assertIn('Player ID', headers)
        self.assertIn('Full Name', headers)
        self.assertIn('Goals', headers)
        self.assertIn('Assists', headers)

        # Check Alex's stats (2 goals, 1 assist)
        alex_row = [r for r in reader if r[1] == '_TEST_Striker_Alex'][0]
        self.assertIn('2', alex_row)
        self.assertIn('1', alex_row)

        # Verify strict absence of sensitive fields: password hashes, emails, tokens
        self.assertNotIn('pbkdf2', csv_text.lower())
        self.assertNotIn('$2b$', csv_text)
        self.assertNotIn('scrypt', csv_text.lower())
        self.assertNotIn('@example.com', csv_text)

    # -------------------------------------------------------------------------
    # Scenario 11: CSV Export — Teams Summary
    # -------------------------------------------------------------------------
    def test_11_export_teams_csv(self):
        self.set_admin_session()
        res = self.client.get('/admin/reports/export/teams')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('Content-Type'), 'text/csv; charset=utf-8')
        self.assertIn('teams_summary_report.csv', res.headers.get('Content-Disposition', ''))

        csv_text = res.data.decode('utf-8')
        reader = list(csv.reader(io.StringIO(csv_text)))
        self.assertGreaterEqual(len(reader), 3)  # Headers + at least 2 test teams

        headers = reader[0]
        self.assertIn('Team ID', headers)
        self.assertIn('Team Name', headers)
        self.assertIn('Sport', headers)
        self.assertIn('Active Roster Count', headers)
        self.assertIn('Scheduled Matches Count', headers)

        alpha_row = [r for r in reader if r[1] == '_TEST_TEAM_R_Alpha'][0]
        self.assertEqual(alpha_row[2], '_TEST_SPORT_R_Football')
        self.assertEqual(alpha_row[3], '1')  # 1 player in roster

    # -------------------------------------------------------------------------
    # Scenario 12: Invalid tournament IDs return 404
    # -------------------------------------------------------------------------
    def test_12_invalid_ids_and_filters_return_404(self):
        self.set_admin_session()

        invalid_urls = [
            '/admin/reports?tournament_id=999999',
            '/admin/reports?tournament_id=-1',
            '/admin/reports?tournament_id=not_an_int',
            '/admin/reports/export/standings?tournament_id=999999',
            '/admin/reports/export/standings?tournament_id=-5',
            '/admin/reports/export/standings',  # missing required parameter
            '/admin/reports/export/matches?tournament_id=999999',
        ]
        for url in invalid_urls:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 404, f"Expected 404 for {url}, got {res.status_code}")

    # -------------------------------------------------------------------------
    # Scenario 13: Formula injection prevention in CSV export
    # -------------------------------------------------------------------------
    def test_13_csv_formula_injection_defense(self):
        from app import make_safe_csv_response
        test_rows = [
            ['Name', 'Score'],
            ['=1+1', '+500'],
            ['-25', '@SUM(A1:A10)'],
            ['Normal Name', '42']
        ]
        with self.app.app_context():
            res = make_safe_csv_response(test_rows, 'injection_test.csv')
            csv_text = res.data.decode('utf-8')

        # Ensure all dangerous characters (=, +, -, @) are prefixed with a quote
        self.assertIn("'=1+1", csv_text)
        self.assertIn("'+500", csv_text)
        self.assertIn("'-25", csv_text)
        self.assertIn("'@SUM(A1:A10)", csv_text)
        self.assertIn("Normal Name,42", csv_text)


if __name__ == '__main__':
    unittest.main()
