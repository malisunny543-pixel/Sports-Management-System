# Phase 9.5 — Player Self-Registration & Account Linking Report

**Project:** SportsPro — Sports Management System  
**Project Root:** `D:\Projects\Sports-Management-System\`  
**Date:** October 2, 2026  
**Status:** Complete & Fully Verified (All 254 Tests Passing)  
**Report File:** `phase_9_5_report.md`  

---

## 1. Initial Findings

An architectural inspection of the SportsPro platform prior to modification revealed:

1. **Authentication & Session Security:**
   * Session security is hardened with `HttpOnly=True`, `SameSite='Lax'`, and sliding 2-hour expirations.
   * Access control is enforced via decorators in `auth.py`: `@login_required`, `@admin_required`, and `@player_required`.
   * User identity is verified against MySQL on each request via `g.current_user = get_current_user()`, requiring `users.is_active == 1`.
2. **Database Schema & Entity Relationship:**
   * `users` table: Holds authentication credentials (`id`, `username`, `email`, `password_hash`, `role`, `is_active`).
   * `players` table: Holds athletic roster profiles (`id`, `full_name`, `sport_id`, `team_id`, `jersey_number`, `user_id`).
   * `players.user_id` has a `UNIQUE KEY` referencing `users.id`, ensuring a strict 1-to-1 relationship between an athletic profile and a user login.
3. **Player Dashboard State:**
   * `/player/dashboard` derives player identity strictly from `g.current_user['id']` in the session.
   * If `user_id` is linked to an athlete, the dashboard renders the player's personal profile, team affiliation, upcoming match fixtures, recent results, and performance statistics.
   * If unlinked, the dashboard gracefully renders an informational warning card stating that the account is pending administrator verification.

---

## 2. Missing Functionality (Addressed in Phase 9.5)

Before Phase 9.5, the application had complete administrative user management and a functional player dashboard, but lacked:
1. A public self-registration route (`/register`) allowing athletes to create login accounts.
2. A public registration template (`templates/auth/register.html`) with SportsPro dark navy and teal styling.
3. Public calls-to-action ("Sign Up" / "Join as Player") on the homepage, navbar, and login interface.
4. Server-enforced role protection ensuring public registrations strictly receive `role='player'`.
5. An end-to-end automated test suite verifying the complete 16-point registration and linking workflow.

---

## 3. Files Created and Modified

### Files Modified:
1. **[app.py](file:///D:/Projects/Sports-Management-System/app.py):**
   * *Changes:* Added `@app.route('/register', methods=['GET', 'POST'])` implementing server-side input validation, password confirmation, duplicate checks, mandatory `role='player'` assignment, secure `scrypt` password hashing, and redirect to `/login`.
   * *Preservation:* Preserved authenticated user redirects (`if g.current_user: ...`), admin user creation (`/admin/users/create`), and existing dashboard routes.
2. **[templates/auth/login.html](file:///D:/Projects/Sports-Management-System/templates/auth/login.html):**
   * *Changes:* Added "Don't have a player account? Sign Up" navigation link (`#link-to-register`).
3. **[templates/layout/base.html](file:///D:/Projects/Sports-Management-System/templates/layout/base.html):**
   * *Changes:* Added a "Sign Up" button (`#nav-register-btn`) in the main navigation bar for unauthenticated visitors.
4. **[templates/index.html](file:///D:/Projects/Sports-Management-System/templates/index.html):**
   * *Changes:* Added "Join as Player (Sign Up)" button in the hero section alongside "Sign In to SportsPro" and "Explore Capabilities", and updated the bottom access card.
5. **[test_phase9.py](file:///D:/Projects/Sports-Management-System/test_phase9.py) & [test_user_experience.py](file:///D:/Projects/Sports-Management-System/test_user_experience.py):**
   * *Changes:* Restored `app.config['WTF_CSRF_ENABLED'] = True` in `tearDownClass` to prevent cross-suite side-effects during test discovery.

### Files Created:
1. **[templates/auth/register.html](file:///D:/Projects/Sports-Management-System/templates/auth/register.html):**
   * *Purpose:* Public registration form matching SportsPro theme with CSRF protection, input constraints, helper text, and link to sign in.
2. **[test_phase_9_5.py](file:///D:/Projects/Sports-Management-System/test_phase_9_5.py):**
   * *Purpose:* Comprehensive 16-scenario test suite verifying all Phase 9.5 requirements.
3. **[test_player_registration.py](file:///D:/Projects/Sports-Management-System/test_player_registration.py):**
   * *Purpose:* Dedicated player registration unit test suite.
4. **[phase_9_5_report.md](file:///D:/Projects/Sports-Management-System/phase_9_5_report.md):**
   * *Purpose:* Completion report in the project root.

---

## 4. Registration and Login Workflow

The verified workflow operates as follows:

```
[Public Visitor] ──> Homepage / Navbar ──> Clicks "Sign Up" (/register)
       │
       ▼
[Registration Form] ──> Submits Username, Email, Password, Confirm Password
       │
       ▼
[Server Validation] ──> Validates format, uniqueness, & forces role='player'
       │
       ▼
[Database Insert] ──> INSERT INTO users (role='player', password_hash, is_active=1)
       │
       ▼
[Redirect to /login] ──> Flash message: "Registration successful! You may now sign in..."
       │
       ▼
[Player Sign In] ──> Authenticates credentials ──> 302 Redirect to /player/dashboard
       │
       ▼
[Unlinked State] ──> Informational card: "Athletic Profile Unlinked"
       │
       ▼
[Admin Linking] ──> Administrator opens /admin/players/<id>/edit 
                    Selects player account from dropdown ──> Saves
       │
       ▼
[Linked Dashboard] ──> Player refreshes dashboard ──> Views personalized fixtures, team, and stats
```

---

## 5. Account-Linking Behavior & Roster Security

* **Decoupled Architecture:** Registration creates an authentication identity in `users`, but does not automatically associate the user with any athlete in `players`.
* **No Name/Email Guessing:** Accounts are never auto-linked based on matching names or emails, preventing unauthorized takeover of roster profiles.
* **Administrator Verification:** League administrators retain exclusive authority over player assignments through **Player Management** (`/admin/players/<id>/edit`).
* **Database Constraint Enforcement:** The `UNIQUE KEY (user_id)` constraint on the `players` table guarantees that an athletic profile can only be claimed by one user account, and one user account cannot claim multiple profiles.
* **Safe Unlinked State:** Unlinked players see an informative notice explaining that administrative verification is required, without encountering database errors or unauthorized data exposure.

---

## 6. Security Protections Implemented

1. **Privilege Escalation Defense:**
   * The `/register` endpoint strictly hardcodes `role='player'` on the server. Any submitted `role` field in the request body is ignored.
   * Administrative accounts can only be created by logged-in administrators via `/admin/users/create` or via the interactive CLI `create_admin.py`.
2. **Password Security:**
   * Passwords are never stored or logged in plaintext.
   * Hashed using Werkzeug `scrypt` (`generate_password_hash`), providing modern defense against brute-force and rainbow table attacks.
3. **Input Validation:**
   * Username: 1–50 characters, alphanumeric with dots, hyphens, and underscores; no spaces.
   * Email: 1–150 characters, verified against RFC-compliant regex.
   * Password: Minimum 8 characters, maximum 128 characters, verified confirmation match.
4. **Duplicate Prevention:**
   * Explicit pre-insert database checks for existing usernames and email addresses.
   * Database-level MySQL error 1062 duplicate key handling.
5. **CSRF Protection:**
   * Global CSRF protection enabled via Flask-WTF; every registration and login form includes a hidden CSRF token verified on POST.
6. **Session & Redirection Safeguards:**
   * Authenticated administrators visiting `/register` or `/login` are automatically redirected to `/admin/dashboard`.
   * Authenticated players visiting `/register` or `/login` are automatically redirected to `/player/dashboard`.
   * Inactive accounts (`is_active = 0`) are immediately blocked from authenticating.
7. **Data Privacy & Isolation:**
   * `/player/dashboard` and `/player/profile` derive user identity strictly from `g.current_user['id']` in the session.
   * Players cannot pass query parameters or form fields to view or modify another athlete's data.

---

## 7. Actual Test Results

### Phase 9.5 Dedicated Test Suite: `test_phase_9_5.py`
Command:
```powershell
.\venv\Scripts\python.exe -m unittest test_phase_9_5.py
```
Results:
| # | Test Case | Description | Result |
| :--- | :--- | :--- | :---: |
| 1 | `test_01_registration_page_loads_successfully` | Registration page loads with all required fields & CSRF | **PASS** |
| 2 | `test_02_valid_registration_creates_player_account` | Valid registration creates user & redirects to /login | **PASS** |
| 3 | `test_03_assigned_role_is_always_player` | Server enforces `role='player'` | **PASS** |
| 4 | `test_04_passwords_are_stored_as_hashes_not_plaintext` | Password stored as scrypt hash, not plaintext | **PASS** |
| 5 | `test_05_duplicate_usernames_and_emails_rejected` | Duplicate usernames and emails return validation error | **PASS** |
| 6 | `test_06_invalid_input_and_mismatched_passwords_rejected` | Missing fields, short passwords, and mismatches rejected | **PASS** |
| 7 | `test_07_public_attempts_to_create_admin_account_fail_safely` | Role tampering ignored; role is always player | **PASS** |
| 8 | `test_08_csrf_protection_follows_existing_conventions` | POST without CSRF token returns 400 Bad Request | **PASS** |
| 9 | `test_09_player_login_redirects_to_player_dashboard` | Player login returns 302 redirecting to /player/dashboard | **PASS** |
| 10 | `test_10_admin_login_redirects_to_admin_dashboard` | Admin login returns 302 redirecting to /admin/dashboard | **PASS** |
| 11 | `test_11_unlinked_players_see_correct_informational_state` | Unlinked player sees graceful warning message | **PASS** |
| 12 | `test_12_admin_linking_connects_correct_player_profile` | Admin links account to profile in Player Management | **PASS** |
| 13 | `test_13_linked_players_see_their_own_dashboard_information` | Linked player views personal profile, team, and stats | **PASS** |
| 14 | `test_14_players_cannot_access_admin_only_routes` | Player accessing admin routes receives 403 Forbidden | **PASS** |
| 15 | `test_15_players_cannot_access_another_players_private_data` | Player session strictly isolates private data | **PASS** |
| 16 | `test_16_existing_admin_and_management_features_continue_to_work` | Admin console, user management, and reports intact | **PASS** |

### Complete Platform Regression Suite
Command:
```powershell
.\venv\Scripts\python.exe -m unittest discover -p "test_*.py"
```
Output:
```text
Ran 254 tests in 18.118s
OK
```

All 254 tests across all phases (Phases 4 through 9, UX, Admin Provisioning, and Phase 9.5) passed with **0 errors and 0 failures**.

---

## 8. Remaining Limitations

* **Administrative Profile Linking Requirement:** By design, self-registered players will see an "Athletic Profile Unlinked" notice on their dashboard until an authorized administrator associates their login with a verified athlete roster record in Player Management. This is an intentional security safeguard to preserve competitive league roster integrity.
* **No Database Migrations Required:** The implementation strictly adheres to the existing database schema without adding new tables or altering columns.

---

## 9. Conclusion

Phase 9.5 is complete and fully verified. Public visitors can register securely as players, log in to their dedicated Player Portal, and view their verified athletic profile and fixtures once linked by an administrator, while the entire administrative console and existing system features remain 100% operational.
