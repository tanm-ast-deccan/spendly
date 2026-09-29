import os
from typing import Optional

from flask import Flask, flash, redirect, render_template, request, url_for

from database.db import create_user, get_user_by_email, init_app, init_db, seed_db

app = Flask(__name__)
# flash() stores messages in the signed session cookie, so a key is required.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
init_app(app)

MIN_PASSWORD_LENGTH = 8

# Create the schema and the demo data before any route is served. Both calls
# are idempotent, so the Flask reloader re-running this module is harmless.
with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def validate_registration(name, email, password) -> Optional[str]:
    """Return the first validation error for normalised form input, or None."""
    if not name or not email or not password:
        return "All fields are required."
    local, _, domain = email.partition("@")
    if email.count("@") != 1 or not local or "." not in domain:
        return "Please enter a valid email address."
    if len(password) < MIN_PASSWORD_LENGTH:
        return "Password must be at least 8 characters."
    return None


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    error = validate_registration(name, email, password)
    if error is None and (
        get_user_by_email(email) is not None
        or create_user(name, email, password) is None
    ):
        error = "An account with that email already exists."
    if error is not None:
        # Not abort(): the form must re-render with the user's name and email kept.
        return render_template("register.html", error=error, name=name, email=email), 400

    flash("Account created — please sign in.", "success")
    return redirect(url_for("login"))


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    return "Logout — coming in Step 3"


@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
