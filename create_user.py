# =============================================================================
# create_user.py — Interactive CLI for User Account Creation (Player or Admin)
# =============================================================================
#
# This script enables system administrators to provision user accounts directly
# from the terminal, specifically supporting creation of Player user accounts
# that can subsequently be linked to athletic profiles in Player Management.
#
# SECURITY FEATURES:
#   1. Password input is masked via getpass.getpass() — never echoed to terminal.
#   2. Plaintext password is discarded immediately after hashing.
#   3. Werkzeug scrypt hashing is used (matching application login).
#   4. Credentials and hashes are never printed or logged.
# =============================================================================

import sys
import getpass
import re
from werkzeug.security import generate_password_hash
from database import get_db_connection


def validate_username(username):
    if not username or len(username.strip()) == 0:
        return False, "Username cannot be empty."
    username = username.strip()
    if len(username) > 50:
        return False, "Username cannot exceed 50 characters."
    if " " in username:
        return False, "Username cannot contain spaces."
    if not re.match(r'^[a-zA-Z0-9_.-]+$', username):
        return False, "Username may only contain letters, numbers, dots, hyphens, and underscores."
    return True, ""


def validate_email(email):
    if not email or len(email.strip()) == 0:
        return False, "Email cannot be empty."
    email = email.strip()
    if len(email) > 150:
        return False, "Email cannot exceed 150 characters."
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return False, "Email format is invalid."
    return True, ""


def validate_password(password):
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if len(password) > 128:
        return False, "Password cannot exceed 128 characters."
    return True, ""


def main():
    print("=" * 60)
    print("SportsPro Management System — Create User Account")
    print("=" * 60)

    conn = get_db_connection()
    if conn is None:
        print("\nERROR: Could not connect to MySQL. Ensure MySQL is running.")
        sys.exit(1)

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Prompt for role
        while True:
            role_choice = input("\nSelect account role [1 for Player (default), 2 for Admin]: ").strip()
            if role_choice in ('', '1', 'player', 'Player'):
                role = 'player'
                break
            elif role_choice in ('2', 'admin', 'Admin'):
                role = 'admin'
                break
            else:
                print("Invalid choice. Please enter 1 for Player or 2 for Admin.")

        # 2. Prompt for username
        while True:
            username = input(f"\nEnter {role} username: ").strip()
            valid, msg = validate_username(username)
            if not valid:
                print(f"Invalid input: {msg}")
                continue

            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                print("Error: That username is already in use. Please choose another.")
                continue
            break

        # 3. Prompt for email
        while True:
            email = input(f"Enter {role} email: ").strip()
            valid, msg = validate_email(email)
            if not valid:
                print(f"Invalid input: {msg}")
                continue

            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                print("Error: That email is already registered. Please choose another.")
                continue
            break

        # 4. Prompt for password (masked input)
        while True:
            password = getpass.getpass("Enter password (min 8 chars): ")
            valid, msg = validate_password(password)
            if not valid:
                print(f"Invalid password: {msg}")
                continue

            confirm_password = getpass.getpass("Confirm password: ")
            if password != confirm_password:
                print("Error: Passwords do not match. Please try again.")
                continue
            break

        # 5. Generate secure hash and discard plaintext password
        password_hash = generate_password_hash(password)
        del password
        del confirm_password

        # 6. Insert user
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, role, is_active)
            VALUES (%s, %s, %s, %s, 1)
            """,
            (username, email, password_hash, role)
        )
        conn.commit()

        cursor.close()
        conn.close()

        print("\n" + "=" * 60)
        print(f"SUCCESS: Account created for username '{username}'.")
        print(f"Role: {role} | Active: True")
        if role == 'player':
            print("NOTE: You can now link this player account to an athletic profile")
            print("      in Player Management (/admin/players).")
        print("=" * 60)

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print(f"\nERROR creating account: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
