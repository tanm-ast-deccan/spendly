"""Tests for login and logout — Step 3.

Never import ``app`` at the top of this module: see the ``spendly_app``
fixture in conftest.py for why.
"""

import pytest

from database import db as db_module
from database.db import (
    DEMO_USER_EMAIL,
    DEMO_USER_NAME,
    DEMO_USER_PASSWORD,
    authenticate_user,
    create_user,
    seed_db,
)


def post_login(client, email=DEMO_USER_EMAIL, password=DEMO_USER_PASSWORD, **kwargs):
    """POST the login form."""
    return client.post("/login", data={"email": email, "password": password}, **kwargs)


def login_as_demo(client):
    """Sign in as the demo user and follow the redirect, consuming the flash."""
    return post_login(client, follow_redirects=True)


# --------------------------------------------------------------------- #
# authenticate_user                                                      #
# --------------------------------------------------------------------- #

def test_authenticate_user_returns_row_on_correct_password(db):
    seed_db()

    user = authenticate_user(DEMO_USER_EMAIL, DEMO_USER_PASSWORD)
    assert user is not None
    assert user["name"] == DEMO_USER_NAME


def test_authenticate_user_returns_none_on_wrong_password(db):
    seed_db()

    assert authenticate_user(DEMO_USER_EMAIL, "wrong-password") is None


def test_authenticate_user_returns_none_for_unknown_email(db):
    seed_db()

    assert authenticate_user("nobody@example.com", DEMO_USER_PASSWORD) is None


def test_authenticate_user_works_for_created_user(db):
    create_user("Alice", "alice@example.com", "password123")

    assert authenticate_user("alice@example.com", "password123")["name"] == "Alice"


def test_authenticate_user_is_exact_match(db):
    """Normalising the email is the caller's job."""
    seed_db()

    assert authenticate_user(DEMO_USER_EMAIL.upper(), DEMO_USER_PASSWORD) is None


def test_unknown_email_still_runs_a_hash_check(db, monkeypatch):
    checked = []
    real_check = db_module.check_password_hash

    def counting_check(password_hash, password):
        checked.append(password_hash)
        return real_check(password_hash, password)

    monkeypatch.setattr(db_module, "check_password_hash", counting_check)

    assert authenticate_user("nobody@example.com", "whatever") is None
    assert checked == [db_module._DUMMY_PASSWORD_HASH]


# --------------------------------------------------------------------- #
# POST /login — success                                                  #
# --------------------------------------------------------------------- #

def test_demo_login_redirects_to_landing(spendly_client):
    response = post_login(spendly_client)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_login_shows_welcome_and_user_navbar(spendly_client):
    response = login_as_demo(spendly_client)
    body = response.get_data(as_text=True)

    assert response.request.path == "/"
    assert "Welcome back, Demo User." in body
    assert 'class="nav-user"' in body
    assert "Sign out" in body
    assert 'href="/logout"' in body
    assert "Sign in" not in body
    assert "Get started" not in body


def test_login_normalises_email(spendly_client):
    assert post_login(spendly_client, email="  DEMO@Spendly.com ").status_code == 302


def test_registered_user_can_sign_in(spendly_client):
    spendly_client.post(
        "/register",
        data={"name": "Alice", "email": "alice@example.com", "password": "password123"},
    )

    response = post_login(spendly_client, email="alice@example.com", password="password123")
    assert response.status_code == 302
    with spendly_client.session_transaction() as sess:
        assert sess["user_name"] == "Alice"


def test_session_holds_only_user_id_and_name(spendly_app, spendly_client):
    login_as_demo(spendly_client)

    with spendly_app.app_context():
        demo_id = db_module.get_user_by_email(DEMO_USER_EMAIL)["id"]
    with spendly_client.session_transaction() as sess:
        assert set(sess.keys()) == {"user_id", "user_name"}
        assert sess["user_id"] == demo_id
        assert sess["user_name"] == DEMO_USER_NAME


def test_login_clears_preexisting_session(spendly_client):
    with spendly_client.session_transaction() as sess:
        sess["stale"] = "x"

    login_as_demo(spendly_client)

    with spendly_client.session_transaction() as sess:
        assert "stale" not in sess


# --------------------------------------------------------------------- #
# POST /login — rejections                                               #
# --------------------------------------------------------------------- #

def test_wrong_password_rerenders_with_401(spendly_client):
    response = post_login(spendly_client, password="wrong-pass-xyz")
    body = response.get_data(as_text=True)

    assert response.status_code == 401
    assert "Invalid email or password." in body
    assert f'value="{DEMO_USER_EMAIL}"' in body
    assert "wrong-pass-xyz" not in body
    with spendly_client.session_transaction() as sess:
        assert "user_id" not in sess


def test_unknown_email_matches_wrong_password(spendly_client):
    wrong_password = post_login(spendly_client, password="wrong-pass-xyz")
    unknown_email = post_login(spendly_client, email="nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert b"Invalid email or password." in wrong_password.data
    assert b"Invalid email or password." in unknown_email.data


@pytest.mark.parametrize(
    "overrides",
    [{"email": ""}, {"password": ""}, {"email": "   "}],
)
def test_blank_field_gives_400(spendly_client, overrides):
    response = post_login(spendly_client, **overrides)

    assert response.status_code == 400
    assert b"Email and password are required." in response.data


# --------------------------------------------------------------------- #
# Logged-in guards                                                       #
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("path", ["/login", "/register"])
def test_logged_in_get_redirects_to_landing(spendly_client, path):
    login_as_demo(spendly_client)

    response = spendly_client.get(path)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


# --------------------------------------------------------------------- #
# GET /logout                                                            #
# --------------------------------------------------------------------- #

def test_logout_clears_session_and_flashes(spendly_client):
    login_as_demo(spendly_client)

    response = spendly_client.get("/logout", follow_redirects=True)
    body = response.get_data(as_text=True)

    assert response.request.path == "/"
    assert "You have been signed out." in body
    assert 'class="flash-messages"' in body
    assert "Sign in" in body
    assert "Get started" in body
    assert "Sign out" not in body
    with spendly_client.session_transaction() as sess:
        assert dict(sess) == {}


def test_logout_when_logged_out(spendly_client):
    response = spendly_client.get("/logout")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    assert b"coming in Step 3" not in response.data
    assert spendly_client.get("/").status_code == 200


# --------------------------------------------------------------------- #
# Flash rendering from base.html                                         #
# --------------------------------------------------------------------- #

def test_register_flash_shown_once_on_login(spendly_client):
    response = spendly_client.post(
        "/register",
        data={"name": "Alice", "email": "alice@example.com", "password": "password123"},
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)

    assert response.request.path == "/login"
    assert body.count("Account created — please sign in.") == 1
    assert b"auth-success" not in spendly_client.get("/login").data


# --------------------------------------------------------------------- #
# Landing page calls to action                                           #
# --------------------------------------------------------------------- #

def test_landing_shows_sign_up_calls_to_action_when_logged_out(spendly_client):
    body = spendly_client.get("/").get_data(as_text=True)

    assert body.count("Create free account") == 2
    assert "Ready to take control?" in body


def test_landing_hides_sign_up_calls_to_action_when_logged_in(spendly_client):
    login_as_demo(spendly_client)

    body = spendly_client.get("/").get_data(as_text=True)
    assert "Create free account" not in body
    assert "Ready to take control?" not in body
    assert "See how it works" in body


def test_no_flash_wrapper_without_messages(spendly_client):
    assert b"flash-messages" not in spendly_client.get("/").data
