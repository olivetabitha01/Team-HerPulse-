"""
Create (or reset) a HerPulse login account.

Usage:
    python create_user.py tabitha mypassword123
"""
import sys
from werkzeug.security import generate_password_hash
from app import get_db, init_db

def create_user(username, password):
    init_db()  # make sure tables + demo user exist first
    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                     (generate_password_hash(password), username))
        print(f"Updated password for existing user '{username}'.")
    else:
        conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                     (username, generate_password_hash(password)))
        print(f"Created new user '{username}'.")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python create_user.py <username> <password>")
        sys.exit(1)
    create_user(sys.argv[1], sys.argv[2])
