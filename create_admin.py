# =============================================================================
# create_admin.py — Secure Interactive CLI for Admin Account Creation
# =============================================================================
#
# This script is run from the terminal to create an initial administrator account.
#
# SECURITY FEATURES:
#   1. Password input is masked via getpass.getpass() — never echoed to terminal.
#   2. Plaintext password is discarded immediately after hashing.
#   3. Werkzeug scrypt hashing is used (matching application login).
#   4. Credentials and hashes are never printed or logged.
#   5. Not exposed as an HTTP endpoint.
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
    return True, ""


def main():
    print("=" * 60)
    print("Sports Management System — Create Administrator Account")
    print("=" * 60)

    conn = get_db_connection()
    if conn is None:
        print("\nERROR: Could not connect to MySQL. Ensure MySQL is running.")
        sys.exit(1)

    try:
        cursor = conn.cursor(dictionary=True)

        # Check if an admin already exists and inform the user
        cursor.execute("SELECT COUNT(*) AS admin_count FROM users WHERE role = 'admin'")
        row = cursor.fetchone()
        if row and row['admin_count'] > 0:
            print(f"\nNOTE: {row['admin_count']} admin account(s) already exist.")

        # Prompt for username
        while True:
            username = input("\nEnter admin username: ").strip()
            valid, msg = validate_username(username)
            if not valid:
                print(f"Invalid input: {msg}")
                continue

            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                print("Error: That username is already in use. Please choose another.")
                continue
            break

        # Prompt for email
        while True:
            email = input("Enter admin email: ").strip()
            valid, msg = validate_email(email)
            if not valid:
                print(f"Invalid input: {msg}")
                continue

            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                print("Error: That email is already registered. Please choose another.")
                continue
            break

        # Prompt for password (masked input)
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

        # Generate secure hash and discard plaintext password
        password_hash = generate_password_hash(password)
        del password
        del confirm_password

        # Insert administrator user
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, role, is_active)
            VALUES (%s, %s, %s, 'admin', 1)
            """,
            (username, email, password_hash)
        )
        conn.commit()

        cursor.close()
        conn.close()

        print("\n" + "=" * 60)
        print(f"SUCCESS: Admin account created for username '{username}'.")
        print("Role: admin | Active: True")
        print("=" * 60)

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print(f"\nERROR creating admin account: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
