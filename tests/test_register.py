"""Tests for registration — Step 2.

Never import ``app`` at the top of this module: see the ``spendly_app``
fixture in conftest.py for why.
"""

import pytest
from werkzeug.security import check_password_hash

from database import db as db_module
from database.db import DEMO_USER_EMAIL, create_user, get_db, get_user_by_email

VALID_FORM = {
    "name": "  Alice  ",
    "email": "  Alice@Example.COM ",
    "password": "password123",
}


def post_register(client, **overrides):
    """POST the registration form, with ``overrides`` replacing VALID_FORM fields."""
    return client.post("/register", data={**VALID_FORM, **overrides})


def user_count(flask_app):
    with flask_app.app_context():
        return get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0]


# --------------------------------------------------------------------- #
# DB helpers                                                             #
# --------------------------------------------------------------------- #

def test_get_user_by_email_returns_none_when_missing(db):
    assert get_user_by_email("nobody@example.com") is None


def test_create_user_returns_id_of_fetchable_row(db):
    user_id = create_user("Alice", "alice@example.com", "password123")

    row = get_user_by_email("alice@example.com")
    assert row["id"] == user_id
    assert row["name"] == "Alice"
    assert row["email"] == "alice@example.com"


def test_create_user_hashes_password(db):
    create_user("Alice", "alice@example.com", "password123")

    password_hash = get_user_by_email("alice@example.com")["password_hash"]
    assert password_hash != "password123"
    assert password_hash.startswith("pbkdf2:sha256")
    assert check_password_hash(password_hash, "password123")


def test_create_user_returns_none_on_duplicate_email(db):
    create_user("Alice", "alice@example.com", "password123")

    assert create_user("Other", "alice@example.com", "password456") is None
    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    # The rollback left the cached connection usable for the next write.
    assert create_user("Bob", "bob@example.com", "password123") is not None


# --------------------------------------------------------------------- #
# Test isolation                                                         #
# --------------------------------------------------------------------- #

def test_route_tests_use_a_temp_database(spendly_app, tmp_path):
    assert db_module.DB_PATH.parent == tmp_path


# --------------------------------------------------------------------- #
# GET /register                                                          #
# --------------------------------------------------------------------- #

def test_get_register_renders_form(spendly_client):
    response = spendly_client.get("/register")

    assert response.status_code == 200
    assert b'action="/register"' in response.data
    assert b'minlength="8"' in response.data


# --------------------------------------------------------------------- #
# POST /register — success                                               #
# --------------------------------------------------------------------- #

def test_valid_registration_redirects_to_login(spendly_client):
    response = post_register(spendly_client)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_success_message_shown_on_login_after_redirect(spendly_client):
    response = spendly_client.post("/register", data=VALID_FORM, follow_redirects=True)

    assert response.request.path == "/login"
    assert "Account created — please sign in." in response.get_data(as_text=True)
    assert b"auth-success" in response.data
    # Flashed messages are shown once only.
    assert b"auth-success" not in spendly_client.get("/login").data


def test_registered_user_is_normalised_and_hashed(spendly_app, spendly_client):
    post_register(spendly_client)

    with spendly_app.app_context():
        row = get_user_by_email("alice@example.com")
    assert row is not None
    assert row["name"] == "Alice"
    assert row["password_hash"].startswith("pbkdf2:sha256")
    assert row["password_hash"] != VALID_FORM["password"]


def test_eight_char_password_is_accepted(spendly_client):
    assert post_register(spendly_client, password="12345678").status_code == 302


# --------------------------------------------------------------------- #
# POST /register — rejections                                            #
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("email", ["alice@example.com", "ALICE@EXAMPLE.COM"])
def test_duplicate_email_any_case_is_rejected(spendly_app, spendly_client, email):
    post_register(spendly_client)

    response = post_register(spendly_client, email=email)
    assert response.status_code == 400
    assert b"An account with that email already exists." in response.data
    assert user_count(spendly_app) == 2  # demo user + Alice


@pytest.mark.parametrize("email", [DEMO_USER_EMAIL, "Demo@Spendly.com"])
def test_demo_email_is_rejected_as_duplicate(spendly_app, spendly_client, email):
    response = post_register(spendly_client, email=email)

    assert response.status_code == 400
    assert b"An account with that email already exists." in response.data
    assert user_count(spendly_app) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"email": ""},
        {"password": ""},
        {"name": "   "},
        {"email": "   "},
    ],
)
def test_blank_field_is_rejected(spendly_app, spendly_client, overrides):
    response = post_register(spendly_client, **overrides)

    assert response.status_code == 400
    assert b"All fields are required." in response.data
    assert user_count(spendly_app) == 1


@pytest.mark.parametrize(
    "email",
    ["alice.example.com", "@example.com", "alice@", "alice@localhost", "a@b@c.com"],
)
def test_malformed_email_is_rejected(spendly_app, spendly_client, email):
    response = post_register(spendly_client, email=email)

    assert response.status_code == 400
    assert b"Please enter a valid email address." in response.data
    assert user_count(spendly_app) == 1


def test_short_password_is_rejected(spendly_app, spendly_client):
    response = post_register(spendly_client, password="1234567")

    assert response.status_code == 400
    assert b"Password must be at least 8 characters." in response.data
    assert user_count(spendly_app) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "short77"},
        {"email": "alice@nodot", "password": "secretpass-xyz"},
        {"email": DEMO_USER_EMAIL, "password": "secretpass-xyz"},
    ],
)
def test_error_keeps_name_and_email_but_not_password(spendly_client, overrides):
    response = post_register(spendly_client, **overrides)
    body = response.get_data(as_text=True)
    expected_email = overrides.get("email", VALID_FORM["email"]).strip().lower()

    assert response.status_code == 400
    assert 'value="Alice"' in body
    assert f'value="{expected_email}"' in body
    assert overrides["password"] not in body


def test_rerendered_values_are_escaped(spendly_client):
    response = post_register(spendly_client, name="<b>x</b>", password="short")

    assert b"<b>x</b>" not in response.data
    assert b"&lt;b&gt;x&lt;/b&gt;" in response.data
