# Spec: Registration

## Overview
This step lets a visitor create a Spendly account. Right now `GET /register` shows the sign-up form, but the form posts to a route that doesn't exist. This step adds `POST /register`. The handler validates the submitted name, email and password, rejects duplicate emails, hashes the password with werkzeug and stores the new user in the `users` table built in Step 1. When the account is created, the user is sent to the sign-in page with a success message. On any error, the form is shown again with the problem explained and the user's entries kept. Registration comes before login and logout (Step 3) because a user has to exist before they can sign in. It also needs the first user-writing helpers in `database/db.py`.

## Depends on
- **Step 1: Database setup.** Needs the `users` table (`email` UNIQUE), `get_db()`, `init_db()` and `PASSWORD_HASH_METHOD` in `database/db.py`.

## Routes
- `GET /register`: renders the registration form. Already implemented; its behaviour doesn't change. Access: public.
- `POST /register`: validates the form and creates the user. On success it redirects to `url_for('login')` with a flashed success message. On a validation error or duplicate email, it re-renders `register.html` with HTTP 400, an `error` message and the submitted `name`/`email` (never the password). Access: public.

`GET` and `POST` are handled by the existing `register()` view function, using `methods=["GET", "POST"]`.

## Database changes
No database changes. The Step 1 `users` table already has `name`, `email` (UNIQUE, NOT NULL), `password_hash` and `created_at`.

New helper functions in `database/db.py`, with no schema change:
- `get_user_by_email(email)` returns the matching `sqlite3.Row` or `None`.
- `create_user(name, email, password)` hashes the password with `generate_password_hash(password, method=PASSWORD_HASH_METHOD)`, inserts the row, commits and returns the new user id. If the insert raises `sqlite3.IntegrityError` because the email already exists (a race past the pre-check), it returns `None`.

## Templates
- **Create:** none
- **Modify:**
  - `templates/register.html`:
    - Change the hard-coded `action="/register"` to `action="{{ url_for('register') }}"`.
    - Pre-fill the `name` and `email` inputs with `value="{{ name or '' }}"` / `value="{{ email or '' }}"`.
    - Add `minlength="8"` to the password input.
  - `templates/login.html`: render flashed messages (`get_flashed_messages(with_categories=true)`) above the form so the "Account created, please sign in" message appears after redirect.

## Files to change
- `app.py`:
  - Set `app.secret_key`, read from the `SECRET_KEY` env var with a dev fallback. `flash()` needs it.
  - Import `request`, `redirect`, `url_for` and `flash`.
  - Import `create_user` and `get_user_by_email`.
  - Make `register()` accept `POST`.
- `database/db.py`: add `get_user_by_email()` and `create_user()`.
- `templates/register.html`: see Templates.
- `templates/login.html`: see Templates.
- `static/css/style.css`: add an `.auth-success` message style next to the existing `.auth-error` (a shared auth style, not page-specific), using only existing CSS variables (`--accent`, `--accent-light`).

## Files to create
- `tests/test_register.py`: tests for the two DB helpers and the `GET`/`POST /register` route. Route tests must patch `database.db.DB_PATH` to a temp file **before** importing `app`, because importing `app.py` runs `init_db()`/`seed_db()` against the real `expense_tracker.db` (see `conftest.py`). If that needs a new fixture, add it to `conftest.py`.

## New dependencies
No new dependencies. Use `werkzeug.security` and `sqlite3`, which are already available.

## Rules for implementation
- No SQLAlchemy or ORMs.
- Parameterised queries only (`?` placeholders). No f-strings or `.format()` in SQL.
- Hash passwords with werkzeug: `generate_password_hash(..., method=PASSWORD_HASH_METHOD)`. Never store or log plain-text passwords.
- Use CSS variables. Never hardcode hex values.
- All templates extend `base.html`.
- No SQL in `app.py`. The route calls `get_user_by_email()` / `create_user()` only.
- Use `url_for()` for every internal link, form action and redirect.
- Validation, done server-side in the route. Keep the HTML5 attributes as a convenience only.
  - Strip whitespace from `name` and `email`, and lowercase `email`, before checking or storing.
  - All three fields are required. Otherwise show "All fields are required."
  - Email must contain `@` with text on both sides and a `.` in the domain part. Otherwise show "Please enter a valid email address."
  - Password must be at least 8 characters. Otherwise show "Password must be at least 8 characters."
  - Duplicate email shows "An account with that email already exists."
- On a validation error, re-render with status 400. Never echo the password back into the form.
- Don't log the user in or touch `session` for auth. Login is Step 3.
- Don't implement any other stub route (`/logout`, `/profile`, `/expenses/*`).
- Vanilla JS only. No JS is required for this step.

## Definition of done
- [ ] `python app.py` starts on port 5001 without errors.
- [ ] `GET /register` renders the form, and its `action` points at `/register` via `url_for`.
- [ ] Submitting a valid name, email and password (8+ characters) redirects to `/login`, which shows a success message.
- [ ] The new user row exists in `users` with a lowercased, trimmed email, and its `password_hash` starts with `pbkdf2:sha256` (it isn't the plain password).
- [ ] Registering again with the same email (in any letter case) re-renders the form with "An account with that email already exists." and no second row is created.
- [ ] Registering with `demo@spendly.com` is rejected as a duplicate.
- [ ] Submitting with any field blank shows "All fields are required."
- [ ] Submitting a malformed email shows "Please enter a valid email address."
- [ ] Submitting a password shorter than 8 characters shows "Password must be at least 8 characters."
- [ ] After any error, name and email stay filled in and the password field is empty. The response status is 400.
- [ ] No hex colours are added to CSS, and the success message uses CSS variables.
- [ ] `pytest` passes, including the new `tests/test_register.py` and the existing `tests/test_db.py`. The real `expense_tracker.db` is not modified by the test run.
