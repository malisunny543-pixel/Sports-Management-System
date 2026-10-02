import re
import unittest
from datetime import datetime, date
from unittest.mock import patch
from app import app
from database import get_db_connection
from werkzeug.security import generate_password_hash


class Phase6PlayerPortalTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = cls.app.test_client()
        cls.client.testing = True

        # Clean up any potential leftover test data
        cls.cleanup_test_data()

        # Seed isolated test sports, teams, users, players, and match stats
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            # 1. Sport
            cursor.execute(
                "INSERT INTO sports (name, description) VALUES (%s, %s)",
                ('_TEST_SPORT_P_Football', 'Test Football for Player Portal')
            )
            conn.commit()
            cursor.execute("SELECT id FROM sports WHERE name = '_TEST_SPORT_P_Football'")
            cls.sport_id = cursor.fetchone()['id']

            # 2. Teams
            cursor.execute("INSERT INTO teams (name, sport_id) VALUES (%s, %s)", ('_TEST_TEAM_P_1', cls.sport_id))
            cursor.execute("INSERT INTO teams (name, sport_id) VALUES (%s, %s)", ('_TEST_TEAM_P_2', cls.sport_id))
            conn.commit()
            cursor.execute("SELECT id, name FROM teams WHERE name LIKE '_TEST_TEAM_P_%'")
            teams = {t['name']: t['id'] for t in cursor.fetchall()}
            cls.team1_id = teams['_TEST_TEAM_P_1']
            cls.team2_id = teams['_TEST_TEAM_P_2']

            # 3. User Accounts (Player A, Player B, Unlinked Player)
            pwd_hash = generate_password_hash('Password123!')
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 1)
                """,
                ('_TEST_user_player_a', '_test_player_a@example.com', pwd_hash)
            )
            cls.user_a_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 1)
                """,
                ('_TEST_user_player_b', '_test_player_b@example.com', pwd_hash)
            )
            cls.user_b_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, 'player', 1)
                """,
                ('_TEST_user_unlinked', '_test_unlinked@example.com', pwd_hash)
            )
            cls.user_unlinked_id = cursor.lastrowid

            # 4. Athletic Player Records (Alice = User A, Bob = User B)
            cursor.execute(
                """
                INSERT INTO players (user_id, full_name, date_of_birth, gender, sport_id, team_id, jersey_number)
                VALUES (%s, %s, '2001-05-15', 'female', %s, %s, 10)
                """,
                (cls.user_a_id, '_TEST_Player_Alice', cls.sport_id, cls.team1_id)
            )
            cls.player_a_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO players (user_id, full_name, date_of_birth, gender, sport_id, team_id, jersey_number)
                VALUES (%s, %s, '2000-08-20', 'male', %s, %s, 9)
                """,
                (cls.user_b_id, '_TEST_Player_Bob', cls.sport_id, cls.team1_id)
            )
            cls.player_b_id = cursor.lastrowid

            # 5. Tournament & Match Fixtures
            cursor.execute(
                """
                INSERT INTO tournaments (name, sport_id, start_date, end_date, status, description)
                VALUES (%s, %s, '2026-11-01', '2026-11-30', 'ongoing', 'Player portal tournament')
                """,
                ('_TEST_Tournament_Portal', cls.sport_id)
            )
            cls.tournament_id = cursor.lastrowid

            # Match 1: Completed match with result
            cursor.execute(
                """
                INSERT INTO matches (tournament_id, team1_id, team2_id, match_datetime, venue, status)
                VALUES (%s, %s, %s, '2026-11-10 15:00:00', '_TEST_Stadium_1', 'completed')
                """,
                (cls.tournament_id, cls.team1_id, cls.team2_id)
            )
            cls.match_completed_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO results (match_id, team1_score, team2_score, winner_team_id, notes)
                VALUES (%s, 3, 1, %s, '_TEST_ Portal victory')
                """,
                (cls.match_completed_id, cls.team1_id)
            )

            # Match 2: Upcoming match
            cursor.execute(
                """
                INSERT INTO matches (tournament_id, team1_id, team2_id, match_datetime, venue, status)
                VALUES (%s, %s, %s, '2026-11-25 18:00:00', '_TEST_Stadium_2', 'scheduled')
                """,
                (cls.tournament_id, cls.team1_id, cls.team2_id)
            )
            cls.match_upcoming_id = cursor.lastrowid

            # 6. Player Match Performance Stats for Player A in Match 1
            cursor.execute(
                """
                INSERT INTO player_match_stats (player_id, match_id, goals, assists, points)
                VALUES (%s, %s, 2, 1, 0)
                """,
                (cls.player_a_id, cls.match_completed_id)
            )
            conn.commit()

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
            cursor.execute("DELETE FROM tournaments WHERE name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM players WHERE full_name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM teams WHERE name LIKE '_TEST_%'")
            cursor.execute("DELETE FROM sports WHERE name LIKE '_TEST_SPORT_P_%'")
            cursor.execute("DELETE FROM users WHERE username LIKE '_TEST_%'")
            conn.commit()
            cursor.close()
            conn.close()

    def setUp(self):
        self.clear_session()

    def tearDown(self):
        self.clear_session()

    def clear_session(self):
        with self.client.session_transaction() as sess:
            sess.clear()

    def set_player_session(self, user_id=None, username='_TEST_user_player_a'):
        uid = user_id or self.user_a_id
        with self.client.session_transaction() as sess:
            sess['user_id'] = uid
            sess['username'] = username
            sess['role'] = 'player'

    def set_admin_session(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'roshan_admin'
            sess['role'] = 'admin'

    def get_csrf_token(self, path='/player/profile'):
        response = self.client.get(path)
        html = response.data.decode('utf-8')
        response.close()
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
        if not match:
            match = re.search(r'value="([^"]+)"\s+name="csrf_token"', html)
        self.assertIsNotNone(match, f"CSRF token not found in response from {path}")
        return match.group(1)

    # -------------------------------------------------------------------------
    # Scenario 1: Player can access player dashboard
    # -------------------------------------------------------------------------
    def test_01_player_can_access_dashboard(self):
        self.set_player_session(self.user_a_id, '_TEST_user_player_a')
        response = self.client.get('/player/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('Player Portal', html)
        self.assertIn('_TEST_Player_Alice', html)
        self.assertIn('_TEST_SPORT_P_Football', html)
        self.assertIn('_TEST_TEAM_P_1', html)
        self.assertIn('#10', html)

    # -------------------------------------------------------------------------
    # Scenario 2: Admin accessing player dashboard receives 403 Forbidden
    # -------------------------------------------------------------------------
    def test_02_admin_accessing_player_dashboard_forbidden(self):
        self.set_admin_session()
        response = self.client.get('/player/dashboard')
        self.assertEqual(response.status_code, 403)
        response.close()

    # -------------------------------------------------------------------------
    # Scenario 3: Unauthenticated visitor accessing dashboard redirected to login
    # -------------------------------------------------------------------------
    def test_03_unauthenticated_visitor_redirected(self):
        self.clear_session()
        response = self.client.get('/player/dashboard')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers.get('Location', ''))
        response.close()

    # -------------------------------------------------------------------------
    # Scenario 4: Player can access profile page
    # -------------------------------------------------------------------------
    def test_04_player_can_access_profile(self):
        self.set_player_session(self.user_a_id, '_TEST_user_player_a')
        response = self.client.get('/player/profile')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('My Profile &amp; Account', html)
        self.assertIn('_TEST_Player_Alice', html)
        self.assertIn('_test_player_a@example.com', html)

    # -------------------------------------------------------------------------
    # Scenario 5: Admin accessing player profile receives 403 Forbidden
    # -------------------------------------------------------------------------
    def test_05_admin_accessing_player_profile_forbidden(self):
        self.set_admin_session()
        response = self.client.get('/player/profile')
        self.assertEqual(response.status_code, 403)
        response.close()

    # -------------------------------------------------------------------------
    # Scenario 6: Unauthenticated visitor accessing profile redirected to login
    # -------------------------------------------------------------------------
    def test_06_unauthenticated_visitor_profile_redirected(self):
        self.clear_session()
        response = self.client.get('/player/profile')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers.get('Location', ''))
        response.close()

    # -------------------------------------------------------------------------
    # Scenario 7: Unlinked player account displays graceful warning without 500 error
    # -------------------------------------------------------------------------
    def test_07_unlinked_player_displays_graceful_warning(self):
        self.set_player_session(self.user_unlinked_id, '_TEST_user_unlinked')
        response = self.client.get('/player/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('Athletic Profile Unlinked', html)
        self.assertIn('administrator has not yet linked', html)

        # Profile view also renders safely
        res_prof = self.client.get('/player/profile')
        self.assertEqual(res_prof.status_code, 200)
        html_prof = res_prof.data.decode('utf-8')
        res_prof.close()
        self.assertIn('No Athletic Profile Linked', html_prof)
        self.assertIn('_test_unlinked@example.com', html_prof)

    # -------------------------------------------------------------------------
    # Scenario 8: Dashboard displays team fixtures and recent results
    # -------------------------------------------------------------------------
    def test_08_dashboard_displays_fixtures_and_results(self):
        self.set_player_session(self.user_a_id, '_TEST_user_player_a')
        response = self.client.get('/player/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()

        # Upcoming fixture
        self.assertIn('Upcoming Match Schedule', html)
        self.assertIn('_TEST_Stadium_2', html)

        # Recent result
        self.assertIn('Recent Match Results', html)
        self.assertIn('3 &ndash; 1', html)
        self.assertIn('Won', html)

    # -------------------------------------------------------------------------
    # Scenario 9: Dashboard displays individual performance statistics
    # -------------------------------------------------------------------------
    def test_09_dashboard_displays_player_performance_stats(self):
        self.set_player_session(self.user_a_id, '_TEST_user_player_a')
        response = self.client.get('/player/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()

        self.assertIn('My Individual Match Performance', html)
        self.assertIn('id="stat-goals-count">2<', html)
        self.assertIn('id="stat-assists-count">1<', html)
        self.assertIn('id="stat-matches-count">1<', html)

    # -------------------------------------------------------------------------
    # Scenario 10: Player can update safe personal fields
    # -------------------------------------------------------------------------
    def test_10_player_can_update_permitted_profile_fields(self):
        self.set_player_session(self.user_a_id, '_TEST_user_player_a')
        csrf_token = self.get_csrf_token('/player/profile')

        response = self.client.post('/player/profile', data={
            'csrf_token': csrf_token,
            'full_name': '_TEST_Player_Alice_Updated',
            'email': '_test_player_a_updated@example.com',
            'date_of_birth': '2001-06-20',
            'gender': 'female'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('profile details have been updated successfully', html.lower())

        # Verify in database
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT email FROM users WHERE id = %s", (self.user_a_id,))
        u = cur.fetchone()
        self.assertEqual(u['email'], '_test_player_a_updated@example.com')

        cur.execute("SELECT full_name, date_of_birth, gender FROM players WHERE user_id = %s", (self.user_a_id,))
        p = cur.fetchone()
        self.assertEqual(p['full_name'], '_TEST_Player_Alice_Updated')
        self.assertEqual(str(p['date_of_birth']), '2001-06-20')
        self.assertEqual(p['gender'], 'female')
        cur.close()
        conn.close()

    # -------------------------------------------------------------------------
    # Scenario 11: Invalid email format or duplicate email rejected
    # -------------------------------------------------------------------------
    def test_11_invalid_or_duplicate_email_rejected(self):
        self.set_player_session(self.user_a_id, '_TEST_user_player_a')
        csrf_token = self.get_csrf_token('/player/profile')

        # Invalid email
        res1 = self.client.post('/player/profile', data={
            'csrf_token': csrf_token,
            'full_name': '_TEST_Player_Alice',
            'email': 'not-an-email',
        }, follow_redirects=True)
        self.assertEqual(res1.status_code, 200)
        html1 = res1.data.decode('utf-8')
        res1.close()
        self.assertIn('valid email', html1.lower())

        # Duplicate email (already used by Player B)
        csrf_token2 = self.get_csrf_token('/player/profile')
        res2 = self.client.post('/player/profile', data={
            'csrf_token': csrf_token2,
            'full_name': '_TEST_Player_Alice',
            'email': '_test_player_b@example.com',
        }, follow_redirects=True)
        self.assertEqual(res2.status_code, 200)
        html2 = res2.data.decode('utf-8')
        res2.close()
        self.assertIn('already in use', html2.lower())

    # -------------------------------------------------------------------------
    # Scenario 12: Future date of birth is rejected
    # -------------------------------------------------------------------------
    def test_12_future_date_of_birth_rejected(self):
        self.set_player_session(self.user_a_id, '_TEST_user_player_a')
        csrf_token = self.get_csrf_token('/player/profile')

        response = self.client.post('/player/profile', data={
            'csrf_token': csrf_token,
            'full_name': '_TEST_Player_Alice',
            'email': '_test_player_a_updated@example.com',
            'date_of_birth': '2099-01-01'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()
        self.assertIn('cannot be in the future', html.lower())

    # -------------------------------------------------------------------------
    # Scenario 13: Unauthorized field manipulation (role escalation, team change) blocked
    # -------------------------------------------------------------------------
    def test_13_unauthorized_fields_cannot_be_manipulated(self):
        self.set_player_session(self.user_a_id, '_TEST_user_player_a')
        csrf_token = self.get_csrf_token('/player/profile')

        # Malicious POST body attempting to escalate to admin and transfer team
        response = self.client.post('/player/profile', data={
            'csrf_token': csrf_token,
            'full_name': '_TEST_Player_Alice_Hacker',
            'email': '_test_player_a_updated@example.com',
            'role': 'admin',
            'is_active': 0,
            'team_id': str(self.team2_id),
            'jersey_number': '99',
            'user_id': '1'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        response.close()

        # Verify role and team were NOT changed in database
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT role, is_active FROM users WHERE id = %s", (self.user_a_id,))
        u = cur.fetchone()
        self.assertEqual(u['role'], 'player', "Role must remain 'player'")
        self.assertEqual(u['is_active'], 1, "is_active must remain 1")

        cur.execute("SELECT team_id, jersey_number, user_id FROM players WHERE user_id = %s", (self.user_a_id,))
        p = cur.fetchone()
        self.assertEqual(p['team_id'], self.team1_id, "Team assignment must remain unchanged")
        self.assertEqual(p['jersey_number'], 10, "Jersey number must remain unchanged")
        self.assertEqual(p['user_id'], self.user_a_id, "user_id linkage must remain unchanged")
        cur.close()
        conn.close()

    # -------------------------------------------------------------------------
    # Scenario 14: Cross-player data isolation
    # -------------------------------------------------------------------------
    def test_14_cross_player_data_isolation(self):
        # Logged in as Player B
        self.set_player_session(self.user_b_id, '_TEST_user_player_b')
        response = self.client.get('/player/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        response.close()

        # Should see Bob's data, NOT Alice's data
        self.assertIn('_TEST_Player_Bob', html)
        self.assertNotIn('_TEST_Player_Alice', html)
        self.assertIn('#9', html)

        # Bob has 0 recorded player match stats
        self.assertIn('id="stat-goals-count">0<', html)

    # -------------------------------------------------------------------------
    # Scenario 15: POST without CSRF token rejected with 400 Bad Request
    # -------------------------------------------------------------------------
    def test_15_post_without_csrf_rejected(self):
        self.set_player_session(self.user_a_id, '_TEST_user_player_a')
        response = self.client.post('/player/profile', data={
            'full_name': 'Unauthorized Edit',
            'email': 'unauth@example.com'
        })
        self.assertEqual(response.status_code, 400)
        response.close()


if __name__ == '__main__':
    unittest.main()
