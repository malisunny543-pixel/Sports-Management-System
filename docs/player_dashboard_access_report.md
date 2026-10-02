# SportsPro — Player Dashboard Access Investigation & Resolution Report

**Project Root:** `D:\Projects\Sports-Management-System\`  
**Date:** October 1, 2026  
**Status:** Complete & Verified (All 225 Tests Passing)  
**Report File:** `player_dashboard_access_report.md`  

---

## 1. Executive Summary

This investigation was conducted to resolve why the **SportsPro Admin Dashboard** (`/admin/dashboard`) could be accessed normally, but the **Player Dashboard** (`/player/dashboard`) could not be accessed.

### Key Findings:
1. **Strict Role-Based Access Control (RBAC):**  
   The application enforces strict authorization separation. The route `/player/dashboard` is protected by `@player_required`. When an administrator account (such as `roshan_admin`, which has `role='admin'`) requests `/player/dashboard`, `auth.py` evaluates:
   ```python
   if user.get('role') != 'player':
       return render_template('auth/403.html'), 403
   ```
   The user received an **HTTP 403 Forbidden** response because administrative accounts are not permitted to access player-only routes directly.
2. **Absence of Player User Accounts in MySQL:**  
   Inspection of the `users` table revealed **only 1 account** existed:
   * `id: 1`, `username: roshan_admin`, `role: admin`, `is_active: 1`
   * There were **zero user accounts with `role='player'`** in the database.
3. **Unlinked Athletic Profiles:**  
   Inspection of the `players` table revealed **4 athletic records** (`krushna ronaldo`, `VAIRAT KOLI`, `MS DHONI`, `modio`), but all four had `user_id = NULL`.
4. **Missing UI Account Creation Feature:**  
   In Phase 7, the user management module (`/admin/users`) provided listing, search, filtering, status toggling, and role changes, but **lacked a "Create User" endpoint or UI form**. The only existing account creation tool was `create_admin.py`, which is restricted to creating admin accounts. Consequently, administrators had no mechanism within the application to provision player accounts or link them to athletes.

### Resolution & Minimum Necessary Fix:
Without altering the database schema, weakening authorization rules, or disturbing existing admin functionality:
* Implemented `GET /admin/users/create` and `POST /admin/users/create` (`user_create` in [app.py](file:///D:/Projects/Sports-Management-System/app.py)) allowing administrators to provision new user accounts with roles `player` or `admin`.
* Created the template [templates/admin/user_form.html](file:///D:/Projects/Sports-Management-System/templates/admin/user_form.html) matching SportsPro dark navy and teal styling with input validation, CSRF protection, and role selection.
* Added a `+ Create New User` button in [templates/admin/users.html](file:///D:/Projects/Sports-Management-System/templates/admin/users.html).
* Created a companion CLI tool [create_user.py](file:///D:/Projects/Sports-Management-System/create_user.py) allowing terminal-based account creation with masked password input.
* Created a comprehensive test suite [test_player_dashboard_access.py](file:///D:/Projects/Sports-Management-System/test_player_dashboard_access.py) verifying account creation, profile linking, player login, dashboard rendering, unlinked graceful states, and 403 authorization enforcement.

---

## 2. Technical Inspection of Architecture & Routes

### 2.1 Route & Authorization Decorators ([auth.py](file:///D:/Projects/Sports-Management-System/auth.py))
* `get_current_user()` re-queries MySQL on every protected request to verify account existence and `is_active == 1`.
* `@admin_required`: Ensures `session['user_id']` is valid and `user['role'] == 'admin'`. Non-admins receive `403 Forbidden`.
* `@player_required`: Ensures `session['user_id']` is valid and `user['role'] == 'player'`. Non-players (including administrators) receive `403 Forbidden`.

### 2.2 Login & Redirection Mechanism ([app.py](file:///D:/Projects/Sports-Management-System/app.py#L175-L242))
When credentials are submitted to `/login`, `app.py` authenticates the user, secures the session, and redirects by role:
```python
if user['role'] == 'admin':
    return redirect(url_for('admin_dashboard'))
return redirect(url_for('player_dashboard'))
```
If an already authenticated user visits `/login`, the application immediately redirects them to their respective dashboard based on their active role.

### 2.3 The Relationship Between `users` and `players`
* The `users` table holds authentication credentials (`id`, `username`, `email`, `password_hash`, `role`, `is_active`).
* The `players` table holds athletic profile data (`id`, `full_name`, `sport_id`, `team_id`, `jersey_number`, `user_id`).
* `players.user_id` is an optional foreign key (`UNIQUE KEY (user_id) REFERENCES users(id)`):
  * **When `user_id IS NOT NULL`:** The user logs in as a player and `/player/dashboard` fetches their profile, assigned team, upcoming matches, recent results, and personal match statistics.
  * **When `user_id IS NULL`:** The user logs in as a player and `/player/dashboard` renders an informational card stating: *"Athletic Profile Unlinked: Your user account is active, but an administrator has not yet linked your account to an athletic player profile."*

---

## 3. Implemented Fixes

### 3.1 Web Route: `user_create` in [app.py](file:///D:/Projects/Sports-Management-System/app.py)
* **URL:** `GET /admin/users/create`, `POST /admin/users/create`
* **Protection:** `@login_required`, `@admin_required`
* **Validation:**
  * Username: Alphanumeric with dots, hyphens, and underscores (1–50 chars, no spaces).
  * Email: Standard RFC-compliant format, max 150 chars.
  * Role: Constrained to `'player'` or `'admin'` (defaulting to `'player'`).
  * Password: Minimum 8 characters, maximum 128 characters.
  * Confirmation: `password == confirm_password`.
  * Uniqueness: Verifies `username` and `email` are not already present in `users`.
* **Security:** Hashes passwords using `werkzeug.security.generate_password_hash` (`scrypt`). Plaintext is immediately discarded.

### 3.2 Template: [templates/admin/user_form.html](file:///D:/Projects/Sports-Management-System/templates/admin/user_form.html)
* Dark navy background with teal accents, breadcrumb navigation, and responsive card container.
* CSRF token integration (`{{ csrf_token() }}`).
* Helper text informing administrators how to link the newly created player account in Player Management.

### 3.3 Navigation Update: [templates/admin/users.html](file:///D:/Projects/Sports-Management-System/templates/admin/users.html)
* Added `+ Create New User` button (`#btn-create-user`) in the header.
* Added fallback create button in the empty state when no users exist.

### 3.4 CLI Utility: [create_user.py](file:///D:/Projects/Sports-Management-System/create_user.py)
* Interactive terminal tool allowing administrators to provision accounts directly via the command line.
* Uses `getpass.getpass()` for masked password input.
* Prompts for role (`player` or `admin`) and validates all constraints.

---

## 4. How to Access the Player Dashboard (Step-by-Step Guide)

You can now easily create a player account, link it, and access the player dashboard:

### Method A: Via Web UI
1. **Log in as Administrator:** Navigate to `http://127.0.0.1:5000/login` and log in with your admin credentials.
2. **Create Player Account:**
   * Go to **User Management** in the top navigation or visit `http://127.0.0.1:5000/admin/users`.
   * Click the **`+ Create New User`** button.
   * Enter a username (e.g., `ronaldo7`), an email address, select Role **`Player`**, enter a password (min 8 chars), and confirm it.
   * Click **Create User Account**.
3. **Link Account to Player Profile:**
   * Go to **Player Management** (`http://127.0.0.1:5000/admin/players`).
   * Click **Edit** next to any player (e.g., `krushna ronaldo`).
   * In the **Linked User Account** dropdown, select `@ronaldo7`.
   * Click **Update Player**.
4. **Log in as the Player:**
   * Sign out of your admin account (or open an Incognito / private browsing window).
   * Go to `http://127.0.0.1:5000/login`.
   * Enter `ronaldo7` and the password you set.
   * The application automatically redirects you to **`/player/dashboard`**.
   * You will see the personalized **Player Portal** displaying the player's name, team, sport, jersey number, match schedule, and performance stats!

### Method B: Via CLI Script
1. In your terminal, run:
   ```bash
   .\venv\Scripts\python.exe create_user.py
   ```
2. Select `1` for Player, enter username, email, and password.
3. Log in as admin to link the account in **Player Management**, then sign in as that player.

---

## 5. Verification & Test Results

An automated test suite was constructed and executed alongside the complete regression suite:

### Test Suite: `test_player_dashboard_access.py`
| Test Case | Description | Result |
| :--- | :--- | :---: |
| `test_01_admin_can_access_user_create_form` | Admin GET `/admin/users/create` returns 200 OK with form | PASS |
| `test_02_unauthenticated_user_create_redirects` | Visitor GET `/admin/users/create` redirects to `/login` | PASS |
| `test_03_user_create_validation_errors` | Missing fields & mismatched passwords trigger errors | PASS |
| `test_04_admin_creates_player_user_account` | Admin POST creates player account with `role='player'` | PASS |
| `test_05_player_appears_in_linking_dropdown` | Player appears in `available_users` on player form | PASS |
| `test_06_link_player_to_athletic_profile` | Player profile successfully links to player user account | PASS |
| `test_07_player_login_redirects_to_player_dashboard` | Player login returns 302 redirecting to `/player/dashboard` | PASS |
| `test_08_player_dashboard_renders_with_profile_data` | Dashboard renders 200 OK with name, sport, team, jersey | PASS |
| `test_09_unlinked_player_renders_graceful_state` | Unlinked player dashboard renders 200 OK warning card | PASS |
| `test_10_admin_accessing_player_dashboard_forbidden` | Admin accessing `/player/dashboard` receives 403 Forbidden | PASS |
| `test_11_unauthenticated_visitor_redirected` | Visitor accessing `/player/dashboard` redirects to `/login` | PASS |
| `test_12_player_cannot_access_admin_routes` | Player accessing `/admin/users` or `/admin/dashboard` gets 403 | PASS |

### Full Project Regression Results:
```text
Ran 225 tests in 15.378s
OK
```
* **Phase 4 (Auth & CSRF):** 100% Passed
* **Phase 5.1–5.7 (Sports, Teams, Players, Tournaments, Matches, Results, Standings):** 100% Passed
* **Phase 6 (Player Portal):** 100% Passed
* **Phase 7 (User Management):** 100% Passed
* **Phase 8 (Reports & CSV Exports):** 100% Passed
* **Phase 9 (Responsive Layouts & Polish):** 100% Passed
* **UX Review Suite:** 100% Passed
* **Player Dashboard Access Suite:** 100% Passed

---

## 6. Summary of Changes

| File | Purpose of Change |
| :--- | :--- |
| [app.py](file:///D:/Projects/Sports-Management-System/app.py) | Added `generate_password_hash` & `re` imports; implemented `user_create` route (`GET/POST /admin/users/create`). |
| [templates/admin/user_form.html](file:///D:/Projects/Sports-Management-System/templates/admin/user_form.html) | Created user account creation template with validation and CSRF. |
| [templates/admin/users.html](file:///D:/Projects/Sports-Management-System/templates/admin/users.html) | Added `+ Create New User` button in header and empty state. |
| [create_user.py](file:///D:/Projects/Sports-Management-System/create_user.py) | Created CLI utility for provisioning player or admin accounts. |
| [test_player_dashboard_access.py](file:///D:/Projects/Sports-Management-System/test_player_dashboard_access.py) | Automated test suite covering all access, linking, and redirection scenarios. |
| [player_dashboard_access_report.md](file:///D:/Projects/Sports-Management-System/player_dashboard_access_report.md) | Documentation of findings, fixes, instructions, and test outcomes. |

No database schema changes were required. No fake production accounts were created. Strict authorization remains fully intact.
