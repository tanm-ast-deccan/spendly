# Spec: Login and Logout

## Overview
This step lets a registered user sign in and out of Spendly. Step 2 made accounts and sends new users to `/login` with a success message, but `/login` only renders the form (a POST gets 405), and `/logout` is a raw-string stub. This step adds `POST /login`, which checks the email and password against the `users` table with werkzeug's `check_password_hash`, starts a Flask session (`session["user_id"]`, `session["user_name"]`) and redirects to the landing page. It also replaces the `/logout` stub with a route that clears the session. The navbar in `base.html` becomes session-aware, showing the user's name and a "Sign out" link instead of "Sign in" / "Get started". Flashed messages move from `login.html` into `base.html` so they show on any page the user lands on. This is the base that Step 4 (Profile) and every expense step builds on, since they all need to know who is logged in.

## Depends on
- **Step 1: Database setup.** Needs the `users` table, `get_db()`, `PASSWORD_HASH_METHOD` and the seeded demo user (`demo@spendly.com` / `demo123`).
- **Step 2: Registration.** Needs `get_user_by_email()`, `app.secret_key` (sessions and `flash()` rely on it), the `.auth-success` style and the redirect to `/login` after sign-up.

## Routes
- `GET /login`: renders the sign-in form. If the user is already logged in (`"user_id" in session`), redirects to `url_for('landing')` instead. Access: public.
- `POST /login`: normalises the email (strip and lowercase), then checks the credentials through `authenticate_user()`.
  - **On success:** clears the session, then sets `session["user_id"]` and `session["user_name"]`, flashes "Welcome back, <name>." (category `success`) and redirects to `url_for('landing')`.
  - **On failure:** re-renders `login.html` with HTTP 401, the error "Invalid email or password." and the submitted email (never the password). A blank field gives HTTP 400 and "Email and password are required."
  - **Access:** public.
- `GET /logout`: clears the session, flashes "You have been signed out." (category `success`) and redirects to `url_for('landing')`. It replaces the Step 3 stub. It works, and redirects the same way, even when nobody is logged in. Access: public.
- `GET /register`: new guard only. If the user is already logged in, redirects to `url_for('landing')`. `POST /register` behaviour is unchanged.

`GET` and `POST /login` are handled by the existing `login()` view function, using `methods=["GET", "POST"]`. `/logout` stays `GET`, as listed in CLAUDE.md's route table.

## Database changes
No database changes. The Step 1 `users` table already has everything login needs.

New helper in `database/db.py`, with no schema change:
- `authenticate_user(email, password)` looks the user up with `get_user_by_email(email)` and returns the `sqlite3.Row` if `check_password_hash(row["password_hash"], password)` passes, otherwise `None`. When no user matches, it still runs `check_password_hash` once against a module-level dummy hash, so a response doesn't reveal through its timing whether the email exists. The caller normalises the email first.

## Templates
- **Create:** none
- **Modify:**
  - `templates/base.html`:
    - **Navbar:** when `session.get("user_id")` is set, show `<span class="nav-user">{{ session.get("user_name") }}</span>` and `<a href="{{ url_for('logout') }}" class="nav-cta">Sign out</a>`. Otherwise keep the current "Sign in" / "Get started" links.
      - Sign out uses `nav-cta` so it stays visible on mobile, where `style.css` hides the other nav links.
    - **Flashes:** add a flash block at the top of `<main class="main-content">`. It renders `get_flashed_messages(with_categories=true)` inside a `<div class="flash-messages">`, using `auth-success` for the `success` category and `auth-error` otherwise.
  - `templates/login.html`:
    - Remove its own flash loop, since `base.html` now renders flashes. Keeping both would consume the messages in the wrong place.
    - Pre-fill the email input with `value="{{ email or '' }}"`. The password input never gets a `value`.

## Files to change
- `app.py`:
  - Import `session` from flask.
  - Import `authenticate_user` from `database.db`.
  - Set `app.config["SESSION_COOKIE_SAMESITE"] = "Lax"`. Flask already makes the session cookie HttpOnly by default.
  - Make `login()` accept `POST`.
  - Replace the `logout()` stub.
  - Add the logged-in guard to `GET /register`.
  - Move `/logout` out of the "Placeholder routes" section.
- `database/db.py`: add `authenticate_user()`, and a `_DUMMY_PASSWORD_HASH` constant for the timing guard. Import `check_password_hash`.
- `templates/base.html`: see Templates.
- `templates/login.html`: see Templates.
- `static/css/style.css`:
  - Add `.flash-messages`, a centred wrapper at `max-width: var(--auth-width)` with top margin.
  - Add `.nav-user`, muted text styled like the nav links.
  - Use only existing CSS variables.
- `CLAUDE.md`: update the "Implemented vs stub routes" table.
  - `GET/POST /login`: Implemented.
  - `GET /logout`: Implemented, clears the session.
  - Also note that `POST /register` is implemented.

## Files to create
- `tests/test_auth.py`: tests for `authenticate_user()` (using the `db` fixture) and for the `/login`, `/logout` and navbar behaviour (using the existing `spendly_client` / `spendly_app` fixtures from `conftest.py`).
  - Never import `app` at the top of the module, for the same reason as `tests/test_register.py`.
  - Check session state with `with spendly_client.session_transaction() as sess:`.

## New dependencies
No new dependencies. Flask's built-in signed-cookie `session`, `werkzeug.security.check_password_hash` and `sqlite3` are already available. No Flask-Login.

## Rules for implementation
- No SQLAlchemy or ORMs.
- Parameterised queries only (`?` placeholders). No f-strings or `.format()` in SQL.
- Passwords are hashed with werkzeug. Verify with `check_password_hash` only, and never compare hashes or plain passwords by hand. Never store, log, flash or re-render the password.
- Use CSS variables. Never hardcode hex values.
- All templates extend `base.html`.
- No SQL and no password checking in `app.py`. The route calls `authenticate_user()` only.
- Use `url_for()` for every internal link, form action and redirect.
- Python 3.9 compatible (the venv is 3.9.6): no `match` statements and no `X | None`. Use `typing.Optional`.
- Use the same error message ("Invalid email or password.") for an unknown email and a wrong password, so the login form can't be used to find out which emails are registered.
- Call `session.clear()` before setting the user keys on login (so a pre-login session can't carry over), and on logout.
- Store only `user_id` and `user_name` in the session. Never store the password hash or the email.
- Don't add a `login_required` decorator and don't protect any routes yet. That's Step 4 (Profile).
- Don't redirect to `/profile` after login, because it's still a stub. Redirect to `landing`.
- Don't implement any other stub route (`/profile`, `/expenses/*`).
- Vanilla JS only. No JS is required for this step.

## Definition of done
- [ ] `python app.py` starts on port 5001 without errors.
- [ ] Signing in as `demo@spendly.com` / `demo123` redirects to `/` and shows "Welcome back, Demo User." The navbar shows "Demo User" and "Sign out" instead of "Sign in" / "Get started".
- [ ] Signing in with `  DEMO@Spendly.com ` (mixed case, with spaces) also works.
- [ ] A user registered through `/register` can then sign in with the same credentials.
- [ ] A wrong password re-renders the form with "Invalid email or password.", HTTP 401, the email kept and the password field empty.
- [ ] An unknown email shows exactly the same message and status as a wrong password.
- [ ] Submitting with a blank email or password shows "Email and password are required." with HTTP 400.
- [ ] After a successful login, the session holds `user_id` and `user_name` and nothing else.
- [ ] Visiting `/login` or `/register` while logged in redirects to `/`.
- [ ] Clicking "Sign out" redirects to `/`, shows "You have been signed out." and the navbar shows "Sign in" / "Get started" again. The session is empty afterwards.
- [ ] Visiting `/logout` while logged out redirects to `/` without an error.
- [ ] The Step 2 flow still works: after registering, `/login` shows "Account created — please sign in." exactly once.
- [ ] `/logout` no longer returns a raw string.
- [ ] No hex colours are added to CSS.
- [ ] `pytest` passes, including the new `tests/test_auth.py`, `tests/test_register.py` and `tests/test_db.py`. The real `expense_tracker.db` is not modified by the test run.
