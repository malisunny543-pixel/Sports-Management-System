-- =============================================================================
-- database/schema_deploy.sql
-- Sports Management System — Deployment Schema
-- =============================================================================
--
-- Schema Version : 3.1 (Deployment-Safe Copy)
-- Engine         : InnoDB
-- Charset        : utf8mb4 / utf8mb4_unicode_ci
-- MySQL Version  : 8.0+ (compatible with Aiven MySQL 8.0)
--
-- HOW TO USE:
--   Import this file into a freshly created Aiven (or any MySQL 8.0+) database:
--
--   Option A — mysql CLI:
--     mysql -h <HOST> -P <PORT> -u <USER> -p --ssl-ca=ca.pem <DATABASE> < schema_deploy.sql
--
--   Option B — MySQL Workbench / DBeaver:
--     Connect to the remote database, open this file, and run all statements.
--
-- DIFFERENCES FROM database/schema.sql:
--   * No "USE <database>;" statement — the target database is selected by the
--     connection itself (via -D flag or connection dialog), so this file works
--     regardless of what the database is named on Aiven.
--
-- SAFETY:
--   * This file contains NO passwords, credentials, or real user data.
--   * Tables are created with IF NOT EXISTS — safe to re-run without data loss.
--   * No DROP TABLE statements — this will NEVER destroy existing data.
-- =============================================================================

-- =============================================================================
-- TABLE 1: users
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
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
CREATE TABLE IF NOT EXISTS sports (
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
CREATE TABLE IF NOT EXISTS teams (
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
CREATE TABLE IF NOT EXISTS players (
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
CREATE TABLE IF NOT EXISTS tournaments (
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
CREATE TABLE IF NOT EXISTS matches (
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
CREATE TABLE IF NOT EXISTS results (
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
CREATE TABLE IF NOT EXISTS player_match_stats (
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
-- Tables created   : 8 (using IF NOT EXISTS — safe to re-run)
-- Foreign keys     : 13
-- Unique keys      : 7
-- Check constraints: 2
-- No sample data inserted. See demo_data.sql for fictional demo records.
-- =============================================================================
