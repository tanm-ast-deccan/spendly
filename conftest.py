"""Shared pytest fixtures for Spendly.

This file lives at the project root on purpose: pytest prepends the directory
containing a conftest.py to sys.path, which is what makes ``import database``
(and later ``import app``) resolve when tests are collected from ``tests/``.
"""

import pytest
from flask import Flask

from database import db as db_module


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A throwaway Flask app whose database lives in a temp directory.

    Deliberately does NOT import app.py: importing it would run its module-level
    ``init_db()``/``seed_db()`` block against the developer's real
    expense_tracker.db before any monkeypatching could take effect. These tests
    exercise the data layer, so a bare Flask app is all the app context we need.

    Patching the module-level DB_PATH works because get_db() looks the name up
    at call time; monkeypatch restores it automatically after each test.
    """
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test_expense_tracker.db")

    flask_app = Flask(__name__)
    flask_app.config.update(TESTING=True)
    db_module.init_app(flask_app)
    return flask_app


@pytest.fixture
def db(app):
    """An initialised, empty database inside a pushed application context.

    Leaving the ``with`` block fires teardown_appcontext, which closes the
    connection — so the teardown wiring is exercised by every test that uses
    this fixture.
    """
    with app.app_context():
        db_module.init_db()
        yield db_module.get_db()


@pytest.fixture
def spendly_app(tmp_path, monkeypatch):
    """The real app from app.py, backed by a fresh temp database per test.

    Named ``spendly_app`` rather than ``app`` so it neither shadows the bare-app
    fixture above nor triggers pytest-flask's autouse context push. app.py is
    imported *inside* the fixture, after DB_PATH is patched, so the module-level
    init_db()/seed_db() of the first import lands in tmp_path. Test modules must
    never import app at top level: collection runs before any fixture, and that
    import would seed the developer's real expense_tracker.db.

    Later tests reuse the cached module, so the schema and demo user are
    recreated here explicitly on each new temp path.
    """
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test_expense_tracker.db")
    import app as app_module  # deliberately late; see docstring

    flask_app = app_module.app
    monkeypatch.setitem(flask_app.config, "TESTING", True)
    with flask_app.app_context():
        db_module.init_db()
        db_module.seed_db()
    return flask_app


@pytest.fixture
def spendly_client(spendly_app):
    """A test client for the real app. Cookies persist, so flash() round-trips."""
    return spendly_app.test_client()
