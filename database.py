# =============================================================================
# database.py — MySQL Connection Helper
# =============================================================================
#
# WHAT DOES THIS FILE DO?
#   This file provides a single reusable function: get_db_connection()
#   Any part of the application that needs to talk to MySQL calls this function
#   to get a live connection to the database.
#
# WHAT IS A "DATABASE CONNECTION"?
#   Think of it like a phone call between Python and MySQL:
#     1. Python "dials" MySQL using the host, port, user, and password
#     2. MySQL answers and checks the credentials
#     3. If everything is correct, an open "line" (connection) is established
#     4. Python sends SQL queries through this line, MySQL sends back results
#     5. When done, the connection is "hung up" (closed)
#
# WHY A SEPARATE FILE?
#   Instead of writing connection code in every route, we write it once here.
#   This follows the DRY principle: Don't Repeat Yourself.
#   It also makes it easy to change the connection logic in one place.
#
# =============================================================================

import mysql.connector                    # The MySQL driver we installed via pip
from mysql.connector import Error         # Error class for catching MySQL-specific errors
from config import DB_CONFIG              # Our database settings (host, port, user, etc.)


def get_db_connection():
    """
    Opens and returns a connection to the MySQL database.

    RETURNS:
        mysql.connector.connection.MySQLConnection — an open database connection
        None — if the connection could not be established

    HOW TO USE:
        conn = get_db_connection()
        if conn is None:
            # Handle the error — MySQL is unavailable
            return

        cursor = conn.cursor()         # A cursor lets you send SQL commands
        cursor.execute("SELECT 1")     # Run a query
        result = cursor.fetchone()     # Fetch the result
        cursor.close()                 # Close the cursor
        conn.close()                   # Close the connection (hang up the phone)

    IMPORTANT:
        Always close the cursor and connection when you are done.
        Leaving connections open wastes server resources.
    """
    try:
        # mysql.connector.connect() attempts to open the connection.
        # **DB_CONFIG unpacks the dictionary as keyword arguments:
        #   host=DB_CONFIG['host'], port=DB_CONFIG['port'], etc.
        connection = mysql.connector.connect(**DB_CONFIG)

        # connection.is_connected() returns True if the connection is alive.
        if connection.is_connected():
            return connection

    except Error as e:
        # ---------------------------------------------------------------
        # Error Handling — Beginner-Friendly Messages
        # ---------------------------------------------------------------
        # MySQL errors have numeric codes. We decode the most common ones
        # so you know exactly what went wrong instead of seeing raw numbers.
        # ---------------------------------------------------------------

        error_code = e.errno  # MySQL's numeric error code

        if error_code == 1045:
            # Access denied — wrong username or password
            print("=" * 60)
            print("DATABASE ERROR: Access Denied")
            print("Cause:   Wrong MySQL username or password in .env")
            print(f"User:    {DB_CONFIG['user']}")
            print(f"Host:    {DB_CONFIG['host']}")
            print("Fix:     Check DB_USER and DB_PASSWORD in your .env file")
            print("=" * 60)

        elif error_code == 1049:
            # Unknown database — the database doesn't exist yet
            print("=" * 60)
            print("DATABASE ERROR: Unknown Database")
            print(f"Cause:   Database '{DB_CONFIG['database']}' does not exist")
            print("Fix:     Create it in MySQL Workbench or with:")
            print(f"         CREATE DATABASE {DB_CONFIG['database']};")
            print("=" * 60)

        elif error_code == 2003:
            # Can't connect to server — MySQL might be stopped
            print("=" * 60)
            print("DATABASE ERROR: Cannot Connect to MySQL Server")
            print(f"Cause:   MySQL is not running on {DB_CONFIG['host']}:{DB_CONFIG['port']}")
            print("Fix:     Open Services (services.msc) and start 'MySQL80'")
            print("         OR run: net start MySQL80  (in an admin terminal)")
            print("=" * 60)

        elif error_code == 2005:
            # Unknown host — wrong hostname
            print("=" * 60)
            print("DATABASE ERROR: Unknown Host")
            print(f"Cause:   Cannot resolve host '{DB_CONFIG['host']}'")
            print("Fix:     Check DB_HOST in your .env file. Use 'localhost' locally.")
            print("=" * 60)

        else:
            # Any other MySQL error
            print("=" * 60)
            print(f"DATABASE ERROR: {e}")
            print("Check your .env file settings and ensure MySQL is running.")
            print("=" * 60)

        return None  # Signal that no connection is available
