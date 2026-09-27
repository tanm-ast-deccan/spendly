"""Tests for the SQLite data layer — Step 1, Database Setup."""

import re
import sqlite3
from datetime import date

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import (
    CATEGORIES,
    DEMO_USER_EMAIL,
    DEMO_USER_NAME,
    DEMO_USER_PASSWORD,
    PASSWORD_HASH_METHOD,
    SEED_EXPENSES,
    get_db,
    init_db,
    seed_db,
)

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def insert_user(db, name="Alice", email="alice@example.com", password="secret"):
    """Insert a user directly and return its id."""
    cursor = db.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, generate_password_hash(password, method=PASSWORD_HASH_METHOD)),
    )
    db.commit()
    return cursor.lastrowid


# --------------------------------------------------------------------- #
# Connection behaviour                                                   #
# --------------------------------------------------------------------- #

def test_get_db_requires_an_application_context():
    """No app context means a clear RuntimeError, not a silent stray connection.

    Deliberately takes no fixture: pytest-flask pushes an application context
    for any fixture named ``app``, so requesting one here would mask the very
    behaviour under test. get_db() touches flask.g before it touches sqlite, so
    nothing can reach the real database from here.
    """
    with pytest.raises(RuntimeError):
        get_db()


def test_get_db_reuses_one_connection_per_app_context(app):
    with app.app_context():
        assert get_db() is get_db()


def test_connection_is_closed_on_app_context_teardown(app):
    with app.app_context():
        connection = get_db()
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_foreign_key_enforcement_is_enabled(db):
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_row_factory_gives_dictionary_like_access(db):
    insert_user(db, name="Alice", email="alice@example.com")
    row = db.execute(
        "SELECT name, email FROM users WHERE email = ?", ("alice@example.com",)
    ).fetchone()

    assert row["name"] == "Alice"
    assert row["email"] == "alice@example.com"
    assert set(row.keys()) == {"name", "email"}
    assert dict(row) == {"name": "Alice", "email": "alice@example.com"}


def test_database_file_is_created_on_disk(app):
    from database import db as db_module

    with app.app_context():
        init_db()
        # sqlite3.connect() alone creates the file, so a bare exists() check
        # would still pass with an empty init_db(). Assert real content too.
        tables = {
            row["name"]
            for row in get_db().execute(
                "SELECT name FROM sqlite_master WHERE type = ?", ("table",)
            )
        }

    assert db_module.DB_PATH.exists()
    assert db_module.DB_PATH.stat().st_size > 0
    assert {"users", "expenses"} <= tables


# --------------------------------------------------------------------- #
# Conformance to the spec's fixed values                                 #
#                                                                        #
# These assert literals on purpose. Every other test compares seeded data #
# against the constants imported from database.db, which only proves the  #
# module agrees with itself — renaming a category or the demo email would #
# keep the whole suite green. These are the tests that would fail.        #
# --------------------------------------------------------------------- #

def test_categories_match_the_specification():
    assert set(CATEGORIES) == {
        "Food",
        "Transport",
        "Bills",
        "Health",
        "Entertainment",
        "Shopping",
        "Other",
    }


def test_demo_user_constants_match_the_specification():
    assert DEMO_USER_NAME == "Demo User"
    assert DEMO_USER_EMAIL == "demo@spendly.com"
    assert DEMO_USER_PASSWORD == "demo123"


def test_spec_requires_exactly_eight_seed_expenses():
    assert len(SEED_EXPENSES) == 8


# --------------------------------------------------------------------- #
# Schema                                                                 #
# --------------------------------------------------------------------- #

def test_users_table_has_the_expected_columns(db):
    columns = {row["name"]: row for row in db.execute("PRAGMA table_info(users)")}

    assert set(columns) == {"id", "name", "email", "password_hash", "created_at"}
    assert columns["id"]["type"] == "INTEGER"
    assert columns["id"]["pk"] == 1
    assert columns["name"]["type"] == "TEXT"
    assert columns["name"]["notnull"] == 1
    assert columns["email"]["type"] == "TEXT"
    assert columns["email"]["notnull"] == 1
    assert columns["password_hash"]["type"] == "TEXT"
    assert columns["password_hash"]["notnull"] == 1
    assert columns["created_at"]["type"] == "TEXT"
    assert columns["created_at"]["dflt_value"] == "datetime('now')"


def test_expenses_table_has_the_expected_columns(db):
    columns = {row["name"]: row for row in db.execute("PRAGMA table_info(expenses)")}

    assert set(columns) == {
        "id",
        "user_id",
        "amount",
        "category",
        "date",
        "description",
        "created_at",
    }
    assert columns["id"]["pk"] == 1
    assert columns["user_id"]["type"] == "INTEGER"
    assert columns["user_id"]["notnull"] == 1
    assert columns["amount"]["type"] == "REAL"
    assert columns["amount"]["notnull"] == 1
    assert columns["category"]["type"] == "TEXT"
    assert columns["category"]["notnull"] == 1
    assert columns["date"]["type"] == "TEXT"
    assert columns["date"]["notnull"] == 1
    assert columns["description"]["notnull"] == 0
    assert columns["created_at"]["dflt_value"] == "datetime('now')"


def test_both_tables_use_autoincrement_primary_keys(db):
    """PRAGMA table_info only reports pk == 1, so check the stored DDL."""
    ddl = {
        row["name"]: row["sql"]
        for row in db.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = ?", ("table",)
        )
    }

    assert "AUTOINCREMENT" in ddl["users"]
    assert "AUTOINCREMENT" in ddl["expenses"]


def test_expenses_declares_a_foreign_key_to_users(db):
    keys = list(db.execute("PRAGMA foreign_key_list(expenses)"))

    assert len(keys) == 1
    assert keys[0]["table"] == "users"
    assert keys[0]["from"] == "user_id"
    assert keys[0]["to"] == "id"


def test_init_db_is_safe_to_call_twice(app):
    with app.app_context():
        init_db()
        init_db()  # must not raise
        tables = {
            row["name"]
            for row in get_db().execute(
                "SELECT name FROM sqlite_master WHERE type = ?", ("table",)
            )
        }
    assert {"users", "expenses"} <= tables


# --------------------------------------------------------------------- #
# Constraints                                                            #
# --------------------------------------------------------------------- #

def test_duplicate_email_is_rejected(db):
    insert_user(db, email="taken@example.com")
    with pytest.raises(sqlite3.IntegrityError):
        insert_user(db, name="Bob", email="taken@example.com")


def test_expense_with_unknown_user_id_is_rejected(db):
    # The FK is immediate, not DEFERRABLE, so execute() itself raises — there is
    # no commit() here because it would be unreachable.
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            (99999, 10.0, "Food", "2026-09-01", "orphan"),
        )


def test_expense_with_a_valid_user_id_is_accepted(db):
    user_id = insert_user(db)
    db.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description)"
        " VALUES (?, ?, ?, ?, ?)",
        (user_id, 10.0, "Food", "2026-09-01", None),
    )
    db.commit()
    assert db.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 1


def test_amount_round_trips_as_a_float(db):
    user_id = insert_user(db)
    db.execute(
        "INSERT INTO expenses (user_id, amount, category, date) VALUES (?, ?, ?, ?)",
        (user_id, 12.34, "Food", "2026-09-01"),
    )
    db.commit()
    amount = db.execute("SELECT amount FROM expenses").fetchone()["amount"]
    assert isinstance(amount, float)
    assert amount == pytest.approx(12.34)


# --------------------------------------------------------------------- #
# Seeding                                                                #
# --------------------------------------------------------------------- #

def test_seed_db_inserts_one_user_and_eight_expenses(db):
    seed_db()

    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 8


def test_seed_db_is_idempotent(db):
    seed_db()
    seed_db()

    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 8


def test_demo_user_has_a_hashed_password_that_verifies(db):
    seed_db()
    user = db.execute(
        "SELECT * FROM users WHERE email = ?", (DEMO_USER_EMAIL,)
    ).fetchone()

    assert user is not None
    assert user["name"] == DEMO_USER_NAME
    assert user["password_hash"] != DEMO_USER_PASSWORD
    assert check_password_hash(user["password_hash"], DEMO_USER_PASSWORD)
    assert not check_password_hash(user["password_hash"], "wrong-password")


def test_seed_expenses_all_belong_to_the_demo_user(db):
    seed_db()
    demo_id = db.execute(
        "SELECT id FROM users WHERE email = ?", (DEMO_USER_EMAIL,)
    ).fetchone()["id"]
    owners = {row["user_id"] for row in db.execute("SELECT user_id FROM expenses")}

    assert owners == {demo_id}


def test_seed_expenses_cover_every_category(db):
    seed_db()
    used = [row["category"] for row in db.execute("SELECT category FROM expenses")]

    assert set(used) == set(CATEGORIES)
    assert len(used) == 8  # seven categories, one of them twice


def test_seed_dates_are_iso_formatted_and_in_the_current_month(db):
    seed_db()
    current_month = date.today().strftime("%Y-%m")
    dates = [row["date"] for row in db.execute("SELECT date FROM expenses")]

    assert len(set(dates)) == 8  # spread out, not all on the same day
    for value in dates:
        assert ISO_DATE.match(value), value
        assert value.startswith(current_month)


def test_seed_amounts_are_positive_floats(db):
    seed_db()
    for row in db.execute("SELECT amount FROM expenses"):
        assert isinstance(row["amount"], float)
        assert row["amount"] > 0


def test_seed_allows_a_null_description(db):
    seed_db()
    null_count = db.execute(
        "SELECT COUNT(*) FROM expenses WHERE description IS NULL"
    ).fetchone()[0]
    expected = sum(1 for _, _, _, description in SEED_EXPENSES if description is None)

    assert null_count == expected == 1


def test_seed_db_does_nothing_when_users_already_exist(db):
    insert_user(db, name="Pre-existing", email="someone@example.com")
    seed_db()

    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0
