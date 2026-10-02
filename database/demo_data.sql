-- =============================================================================
-- database/demo_data.sql
-- Sports Management System — Fictional Demo Data
-- =============================================================================
--
-- PURPOSE:
--   Populate a freshly deployed database with enough demo data to demonstrate
--   all application features: standings, leaderboards, reports, and CSV exports.
--
-- SAFETY RULES:
--   * ALL data in this file is entirely fictional.
--   * NO real names, passwords, email addresses, or personal information.
--   * NO user accounts, passwords, or credentials are included in this file.
--     Admin and player accounts must be created post-import (see below).
--   * Import ONLY into a fresh / empty database — or after importing schema_deploy.sql.
--   * This file is OPTIONAL. The application runs correctly with no data.
--
-- HOW TO IMPORT:
--   mysql -h <HOST> -P <PORT> -u <USER> -p --ssl-ca=ca.pem <DATABASE> < demo_data.sql
--
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Users
-- -----------------------------------------------------------------------------
-- *** NO USER ROWS ARE INSERTED HERE. ***
--
-- User accounts cannot be safely seeded in a SQL file because this file
-- is committed to a Git repository and any pre-hashed password would be
-- a public credential risk, and any unhashed password is a critical
-- security violation.
--
-- HOW TO CREATE ACCOUNTS AFTER IMPORTING DEMO DATA:
--
-- 1. Admin account (required):
--    Run on your local machine (pointed at Aiven via env vars):
--      python create_admin.py
--
-- 2. Player accounts:
--    Use the public self-registration page:
--      https://<your-app>.onrender.com/register
--    Then link player profiles via Admin → Players → Link Account.
--
-- See PHASE_11A_DEPLOYMENT_READINESS.md for full instructions.


-- -----------------------------------------------------------------------------
-- Sports
-- -----------------------------------------------------------------------------
INSERT INTO sports (name, description) VALUES
  ('Football',    'Association Football (Soccer)'),
  ('Basketball',  'Half-court and full-court basketball'),
  ('Cricket',     'Twenty20 and One-Day International format');

-- -----------------------------------------------------------------------------
-- Teams
-- -----------------------------------------------------------------------------
INSERT INTO teams (name, sport_id) VALUES
  ('Riverside Rovers',    1),  -- Football
  ('Lakeside Lions',      1),  -- Football
  ('Downtown Dunkers',    2),  -- Basketball
  ('Uptown Blazers',      2),  -- Basketball
  ('Valley Vipers',       3),  -- Cricket
  ('Highland Hawks',      3);  -- Cricket

-- -----------------------------------------------------------------------------
-- Players (unlinked demo profiles; link to user accounts post-registration)
-- -----------------------------------------------------------------------------
INSERT INTO players (user_id, full_name, date_of_birth, gender, sport_id, team_id, jersey_number) VALUES
  (NULL, 'Alice Adams',   '1998-04-12', 'female', 1, 1, 10),  -- Football, Riverside Rovers (ID 1)
  (NULL, 'Bob Brown',     '1997-11-23', 'male',   1, 2, 7),   -- Football, Lakeside Lions (ID 2)
  (NULL, 'Charlie Clark', '1999-01-15', 'male',   2, 3, 23),  -- Basketball, Downtown Dunkers (ID 3)
  (NULL, 'David Davis',   '2002-08-30', 'male',   2, 4, 5),   -- Basketball, Uptown Blazers (ID 4)
  (NULL, 'Emma Evans',    '2001-06-19', 'female', 1, 1, 9),   -- Football, Riverside Rovers (ID 5)
  (NULL, 'Frank Foster',  '1996-09-03', 'male',   3, 5, 1),   -- Cricket, Valley Vipers (ID 6)
  (NULL, 'Grace Grant',   '2000-02-28', 'female', 3, 6, 11);  -- Cricket, Highland Hawks (ID 7)

-- -----------------------------------------------------------------------------
-- Tournaments
-- -----------------------------------------------------------------------------
INSERT INTO tournaments (name, sport_id, start_date, end_date, status, description) VALUES
  ('Demo Cup 2026',         1, '2026-09-01', '2026-12-31', 'ongoing',   'Annual football league for demonstration.'),
  ('Hoop Classic 2026',     2, '2026-10-01', '2026-12-15', 'upcoming',  'Basketball showcase tournament.'),
  ('Cricket Premier 2026',  3, '2026-08-01', '2026-10-31', 'completed', 'Completed cricket season.');

-- -----------------------------------------------------------------------------
-- Matches
-- -----------------------------------------------------------------------------
INSERT INTO matches (tournament_id, team1_id, team2_id, match_datetime, venue, status) VALUES
  (1, 1, 2, '2026-09-15 15:00:00', 'Riverside Stadium',   'completed'),
  (1, 1, 2, '2026-11-01 14:00:00', 'Lakeside Arena',      'scheduled'),
  (2, 3, 4, '2026-10-20 18:00:00', 'Downtown Court',      'scheduled'),
  (3, 5, 6, '2026-08-20 10:00:00', 'Valley Ground',       'completed'),
  (3, 6, 5, '2026-09-15 10:00:00', 'Highland Oval',       'completed');

-- -----------------------------------------------------------------------------
-- Results (for completed matches only)
-- -----------------------------------------------------------------------------
-- Match 1: Riverside Rovers 3 – 1 Lakeside Lions  → Riverside wins
INSERT INTO results (match_id, team1_score, team2_score, winner_team_id, notes) VALUES
  (1, 3, 1, 1, 'Strong first-half performance by Riverside.');

-- Match 4: Valley Vipers 180 – 145 Highland Hawks  → Valley wins
INSERT INTO results (match_id, team1_score, team2_score, winner_team_id, notes) VALUES
  (4, 180, 145, 5, 'Valley dominated with consistent batting.');

-- Match 5: Highland Hawks 210 – 180 Valley Vipers  → Highland wins
INSERT INTO results (match_id, team1_score, team2_score, winner_team_id, notes) VALUES
  (5, 210, 180, 6, 'Highland chased down the target with 3 wickets to spare.');

-- -----------------------------------------------------------------------------
-- Player Match Stats
-- -----------------------------------------------------------------------------
-- Match 1 stats (Football)
INSERT INTO player_match_stats (player_id, match_id, goals, assists, points) VALUES
  (1, 1, 2, 1, 7),  -- Alice for Riverside
  (5, 1, 0, 2, 2),  -- Emma for Riverside
  (2, 1, 1, 0, 3);  -- Bob for Lakeside

-- Match 4 stats (Cricket — using points as runs)
INSERT INTO player_match_stats (player_id, match_id, goals, assists, points) VALUES
  (6, 4, 0, 0, 85),  -- Frank for Valley Vipers
  (7, 4, 0, 0, 60);  -- Grace for Highland Hawks

-- Match 5 stats (Cricket)
INSERT INTO player_match_stats (player_id, match_id, goals, assists, points) VALUES
  (6, 5, 0, 0, 55),   -- Frank for Valley Vipers
  (7, 5, 0, 0, 95);   -- Grace for Highland Hawks

-- =============================================================================
-- END OF DEMO DATA
-- Records inserted:
--   users:              0  (create via create_admin.py and /register)
--   sports:             3
--   teams:              6
--   players:            7  (all unlinked — link via Admin → Players after creating user accounts)
--   tournaments:        3
--   matches:            5
--   results:            3
--   player_match_stats: 7
-- =============================================================================
