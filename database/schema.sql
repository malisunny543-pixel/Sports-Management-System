-- =============================================================================
-- database/schema.sql
-- Sports Management System -- Complete Database Schema
-- =============================================================================
--
-- Schema Version : 3.1 (Approved)
-- Database       : sports_management
-- Engine         : InnoDB
-- Charset        : utf8mb4 / utf8mb4_unicode_ci
-- MySQL Version  : 8.0+
--
-- SECURITY NOTES:
--   * This file contains NO passwords, credentials, or sensitive data.
--   * Passwords are stored by the application as bcrypt hashes only.
--
-- SAMPLE DATA:
--   * This file contains NO sample data, test users, or demo records.
--
-- CREATION ORDER (parent tables before child tables):
--   1. users
--   2. sports
--   3. teams               (references: users, sports)
--   4. players             (references: users, sports, teams)
--   5. tournaments         (references: sports)
--   6. matches             (references: tournaments, teams)
--   7. results             (references: matches, teams)
--   8. player_match_stats  (references: players, matches)
-- =============================================================================

USE sports_management;

-- =============================================================================
-- TABLE 1: users
-- =============================================================================
-- Stores all login accounts for the application.
-- Supports two roles: admin (system manager) and player (athlete login).
-- password_hash: bcrypt hash only. Plain text MUST NEVER be stored here.
-- is_active: 1=active (can log in), 0=disabled (login blocked).
-- =============================================================================
CREATE TABLE users (
    id            INT UNSIGNED                   NOT NULL AUTO_INCREMENT,
    username      VARCHAR(50)                    NOT NULL,
    email         VARCHAR(150)                   NOT NULL,
    password_hash VARCHAR(255)                   NOT NULL,
    role          ENUM('admin', 'player')        NOT NULL DEFAULT 'player',
    is_active     TINYINT(1)                     NOT NULL DEFAULT 1,
    created_at    DATETIME                       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME                                DEFAULT CURRENT_TIMESTAMP
                  ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_users_username (username),
    UNIQUE KEY uq_users_email    (email)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- TABLE 2: sports
-- =============================================================================
-- Master reference list of sports (Football, Cricket, Basketball, etc.).
-- Every team, player, and tournament must reference this table.
-- UNIQUE(name): prevents duplicate sport entries.
-- =============================================================================
CREATE TABLE sports (
    id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    name        VARCHAR(100)    NOT NULL,
    description TEXT                     DEFAULT NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_sports_name (name)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- TABLE 3: teams
-- =============================================================================
-- Teams that compete in matches. Each team belongs to exactly one sport.
-- UNIQUE(name, sport_id): same name allowed across different sports.
-- created_by: admin who created the team.
--   ON DELETE SET NULL: team survives if creator account is deleted.
-- sport_id ON DELETE RESTRICT: cannot delete a sport that has teams.
-- =============================================================================
CREATE TABLE teams (
    id         INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    name       VARCHAR(100)    NOT NULL,
    sport_id   INT UNSIGNED    NOT NULL,
    created_by INT UNSIGNED             DEFAULT NULL,
    created_at DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_teams_name_sport (name, sport_id),
    INDEX idx_teams_sport (sport_id),

    CONSTRAINT fk_teams_sport
        FOREIGN KEY (sport_id)
        REFERENCES sports(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_teams_created_by
        FOREIGN KEY (created_by)
        REFERENCES users(id)
        ON DELETE SET NULL

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- TABLE 4: players
-- =============================================================================
-- Sports profile for a player. Authentication lives in users.
-- user_id: optional link to login account. UNIQUE: one player per user.
--   ON DELETE SET NULL: player profile survives if account is deleted.
-- sport_id ON DELETE RESTRICT: cannot delete a sport with players.
-- team_id: current team only. NULL = unassigned.
--   ON DELETE SET NULL: players become unassigned if team is deleted.
-- LIMITATION: team_id reflects current membership only. Historical
--   team membership after transfers is NOT preserved in this schema.
-- =============================================================================
CREATE TABLE players (
    id            INT UNSIGNED                   NOT NULL AUTO_INCREMENT,
    user_id       INT UNSIGNED                            DEFAULT NULL,
    full_name     VARCHAR(150)                   NOT NULL,
    date_of_birth DATE                                    DEFAULT NULL,
    gender        ENUM('male', 'female', 'other')         DEFAULT NULL,
    sport_id      INT UNSIGNED                   NOT NULL,
    team_id       INT UNSIGNED                            DEFAULT NULL,
    jersey_number TINYINT UNSIGNED                        DEFAULT NULL,
    created_at    DATETIME                       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME                                DEFAULT CURRENT_TIMESTAMP
                  ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_players_user_id (user_id),
    INDEX idx_players_sport (sport_id),
    INDEX idx_players_team  (team_id),

    CONSTRAINT fk_players_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_players_sport
        FOREIGN KEY (sport_id)
        REFERENCES sports(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_players_team
        FOREIGN KEY (team_id)
        REFERENCES teams(id)
        ON DELETE SET NULL

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- TABLE 5: tournaments
-- =============================================================================
-- Competition events for one sport with a defined time window and status.
-- CHECK (end_date >= start_date): enforced by MySQL engine level.
--   Flask also validates this for user-friendly error messages.
-- status lifecycle: upcoming -> ongoing -> completed | cancelled
-- sport_id ON DELETE RESTRICT: cannot delete a sport with tournaments.
-- =============================================================================
CREATE TABLE tournaments (
    id          INT UNSIGNED                                            NOT NULL AUTO_INCREMENT,
    name        VARCHAR(150)                                            NOT NULL,
    sport_id    INT UNSIGNED                                            NOT NULL,
    start_date  DATE                                                    NOT NULL,
    end_date    DATE                                                    NOT NULL,
    status      ENUM('upcoming', 'ongoing', 'completed', 'cancelled')  NOT NULL DEFAULT 'upcoming',
    description TEXT                                                             DEFAULT NULL,
    created_at  DATETIME                                                NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME                                                         DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    INDEX idx_tournaments_sport  (sport_id),
    INDEX idx_tournaments_status (status),

    CONSTRAINT fk_tournaments_sport
        FOREIGN KEY (sport_id)
        REFERENCES sports(id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_tournament_dates
        CHECK (end_date >= start_date)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- TABLE 6: matches
-- =============================================================================
-- Scheduled game within a tournament between exactly two teams.
-- CHECK (team1_id <> team2_id): a team cannot play against itself.
-- tournament_id RESTRICT: cannot delete tournament with matches.
-- team1_id / team2_id RESTRICT: cannot delete teams referenced in matches.
-- CANCELLATION: matches with results or stats must not be deleted.
--   Use status='cancelled' instead. Flask enforces this before any DELETE.
-- =============================================================================
CREATE TABLE matches (
    id             INT UNSIGNED                                             NOT NULL AUTO_INCREMENT,
    tournament_id  INT UNSIGNED                                             NOT NULL,
    team1_id       INT UNSIGNED                                             NOT NULL,
    team2_id       INT UNSIGNED                                             NOT NULL,
    match_datetime DATETIME                                                 NOT NULL,
    venue          VARCHAR(200)                                                      DEFAULT NULL,
    status         ENUM('scheduled', 'ongoing', 'completed', 'cancelled')  NOT NULL DEFAULT 'scheduled',
    created_at     DATETIME                                                 NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     DATETIME                                                          DEFAULT CURRENT_TIMESTAMP
                   ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    INDEX idx_matches_tournament (tournament_id),
    INDEX idx_matches_status     (status),
    INDEX idx_matches_datetime   (match_datetime),
    INDEX idx_matches_team1      (team1_id),
    INDEX idx_matches_team2      (team2_id),

    CONSTRAINT fk_matches_tournament
        FOREIGN KEY (tournament_id)
        REFERENCES tournaments(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_matches_team1
        FOREIGN KEY (team1_id)
        REFERENCES teams(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_matches_team2
        FOREIGN KEY (team2_id)
        REFERENCES teams(id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_matches_different_teams
        CHECK (team1_id <> team2_id)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- TABLE 7: results
-- =============================================================================
-- Final score and winner for a completed match.
-- UNIQUE(match_id): one match can have at most one result.
-- SMALLINT UNSIGNED for scores: supports up to 65,535 (cricket, basketball).
-- winner_team_id: NULL = draw. Must be team1_id or team2_id of the match.
-- RESULT VALIDATION (Flask-enforced):
--   team1_score > team2_score -> winner MUST be team1_id
--   team2_score > team1_score -> winner MUST be team2_id
--   scores equal, winner NULL -> draw, accepted
--   scores equal, winner set  -> tie-break; notes MUST be non-empty
--   winner contradicts scores -> REJECTED by Flask
-- match_id CASCADE: result deleted when match is deleted.
-- winner_team_id RESTRICT: cannot delete a team recorded as winner.
-- =============================================================================
CREATE TABLE results (
    id             INT UNSIGNED      NOT NULL AUTO_INCREMENT,
    match_id       INT UNSIGNED      NOT NULL,
    team1_score    SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    team2_score    SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    winner_team_id INT UNSIGNED               DEFAULT NULL,
    notes          TEXT                       DEFAULT NULL,
    created_at     DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     DATETIME                   DEFAULT CURRENT_TIMESTAMP
                   ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_results_match_id (match_id),

    CONSTRAINT fk_results_match
        FOREIGN KEY (match_id)
        REFERENCES matches(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_results_winner
        FOREIGN KEY (winner_team_id)
        REFERENCES teams(id)
        ON DELETE RESTRICT

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- TABLE 8: player_match_stats
-- =============================================================================
-- Per-player performance for a specific match.
-- UNIQUE(player_id, match_id): one record per player per match.
-- Generic fields: goals, assists, points (sport-agnostic).
-- player_id CASCADE: stats deleted when player is deleted.
-- match_id  CASCADE: stats deleted when match is deleted.
-- APPLICATION VALIDATION (Flask):
--   Player's current team_id must equal team1_id or team2_id of the match.
--   Record stats before any team transfers occur.
-- =============================================================================
CREATE TABLE player_match_stats (
    id         INT UNSIGNED      NOT NULL AUTO_INCREMENT,
    player_id  INT UNSIGNED      NOT NULL,
    match_id   INT UNSIGNED      NOT NULL,
    goals      TINYINT UNSIGNED  NOT NULL DEFAULT 0,
    assists    TINYINT UNSIGNED  NOT NULL DEFAULT 0,
    points     SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    created_at DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME                   DEFAULT CURRENT_TIMESTAMP
               ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_pms_player_match (player_id, match_id),
    INDEX idx_pms_player (player_id),
    INDEX idx_pms_match  (match_id),

    CONSTRAINT fk_pms_player
        FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_pms_match
        FOREIGN KEY (match_id)
        REFERENCES matches(id)
        ON DELETE CASCADE

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- END OF SCHEMA
-- Tables created   : 8
-- Foreign keys     : 13
-- Unique keys      : 7
-- Check constraints: 2  (chk_tournament_dates, chk_matches_different_teams)
-- Named indexes    : 9  (plus automatic PK and UNIQUE indexes)
-- No sample data inserted.
-- =============================================================================
