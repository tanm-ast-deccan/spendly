"""SQLite data layer for Spendly.

Every database access in the app goes through this module — routes must never
contain inline SQL.

Design notes
------------
* One connection per Flask application context, cached on ``flask.g`` and
  closed by the ``teardown_appcontext`` hook registered in :func:`init_app`.
* ``PRAGMA foreign_keys = ON`` runs on every new connection: SQLite disables
  foreign key enforcement by default, and the pragma is a no-op if it is issued
  inside an open transaction, so it must be the first statement on the
  connection.
* All queries are parameterised with ``?`` placeholders. Never build SQL with
  f-strings or ``.format()``.
"""

import sqlite3
from datetime import date
from pathlib import Path

from flask import g
from werkzeug.security import generate_password_hash

# db.py lives in database/, so the project root is two levels up. Resolving from
# __file__ keeps the database in the project root no matter what the current
# working directory is when the app or the tests are started.
DB_PATH = Path(__file__).resolve().parent.parent / "expense_tracker.db"

# The fixed category list from the spec. Shared so that routes and tests never
# hard-code their own copy.
CATEGORIES = (
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
)

DEMO_USER_NAME = "Demo User"
DEMO_USER_EMAIL = "demo@spendly.com"
DEMO_USER_PASSWORD = "demo123"

# Werkzeug 3.x defaults to scrypt, which needs hashlib.scrypt — unavailable on
# Pythons linked against LibreSSL (this venv's 3.9.6 is one), where
# generate_password_hash raises AttributeError. pbkdf2:sha256 is pure hashlib,
# available everywhere, and still a sound password hash. Stated explicitly so
# the choice does not silently change with the interpreter.
PASSWORD_HASH_METHOD = "pbkdf2:sha256"

# (day_of_month, amount, category, description)
# Eight rows covering all seven categories; "Food" appears twice. Day numbers
# stay at or below 28 so that they are valid in every month, and the actual
# month/year is filled in at seed time so the demo data is always "this month".
# One description is deliberately None to exercise the nullable column.
SEED_EXPENSES = (
    (3, 42.75, "Food", "Weekly grocery run"),
    (5, 12.50, "Transport", "Metro card top-up"),
    (8, 89.99, "Bills", "Electricity bill"),
    (12, 35.00, "Health", "Pharmacy - prescription refill"),
    (15, 18.00, "Entertainment", "Cinema ticket"),
    (19, 129.40, "Shopping", "Running shoes"),
    (22, 25.00, "Other", None),
    (25, 56.20, "Food", "Dinner with friends"),
)

# NOTE: SQLite only accepts a function call in a DEFAULT clause when it is
# wrapped in parentheses — bare ``DEFAULT datetime('now')`` is a syntax error.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    amount      REAL NOT NULL,
    category    TEXT NOT NULL,
    date        TEXT NOT NULL,
    description TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users (id)
);
"""


def get_db():
    """Return the SQLite connection for the current application context.

    The connection is opened on first use, cached on ``flask.g``, and reused for
    the rest of the context. Requires an active application context; calling
    this outside one raises ``RuntimeError`` from Flask.
    """
    if "db" not in g:
        connection = sqlite3.connect(DB_PATH)
        # Must be the first statement on the connection: foreign key
        # enforcement is per-connection and is ignored inside a transaction.
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        g.db = connection
    return g.db


def close_db(e=None):
    """Close the connection cached on ``g``, if one was opened.

    Registered as a ``teardown_appcontext`` handler by :func:`init_app`; Flask
    passes the unhandled exception (or ``None``) as the single argument.
    """
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_app(app):
    """Wire this module into a Flask app.

    Keeps all knowledge of the connection lifecycle inside db.py — app.py only
    has to say that the app uses a database.
    """
    app.teardown_appcontext(close_db)


def init_db():
    """Create both tables if they do not exist. Safe to call repeatedly.

    Must be called inside an application context.
    """
    db = get_db()
    db.executescript(SCHEMA_SQL)
    db.commit()


def seed_db():
    """Insert the demo user and eight sample expenses, once.

    Returns early if the ``users`` table already holds any row, so repeated
    calls never duplicate data. Must be called inside an application context.
    """
    db = get_db()
    user_count = db.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    if user_count > 0:
        return

    cursor = db.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (
            DEMO_USER_NAME,
            DEMO_USER_EMAIL,
            generate_password_hash(DEMO_USER_PASSWORD, method=PASSWORD_HASH_METHOD),
        ),
    )
    demo_user_id = cursor.lastrowid

    today = date.today()
    rows = [
        (
            demo_user_id,
            amount,
            category,
            today.replace(day=day).isoformat(),
            description,
        )
        for day, amount, category, description in SEED_EXPENSES
    ]
    db.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description)"
        " VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    db.commit()
