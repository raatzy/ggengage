import os
import sys
import functools

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import (
    Flask, render_template, redirect, url_for,
    request, send_file, abort, session, flash
)
from email_automation.config import Config
from email_automation.database import (
    init_db, get_post, get_posts, update_post, set_status, set_posted
)
from social.poster import post_to_platforms, results_to_json, results_from_json

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY

ALL_PLATFORMS = ["facebook", "instagram", "tiktok", "x"]


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if (
            request.form.get("username") == Config.DASHBOARD_USERNAME
            and request.form.get("password") == Config.DASHBOARD_PASSWORD
        ):
            session["logged_in"] = True
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "Invalid username or password."
    return render_template("login.html", error=error, business_name=Config.BUSINESS_NAME)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    pending = get_posts("pending")
    approved = get_posts("approved")
    posted = get_posts("posted")
    rejected = get_posts("rejected")
    return render_template(
        "dashboard.html",
        pending=pending,
        approved=approved,
        posted=posted,
        rejected=rejected,
        business_name=Config.BUSINESS_NAME,
    )


# ── Post detail ───────────────────────────────────────────────────────────────

@app.route("/post/<int:post_id>")
@login_required
def post_detail(post_id):
    post = get_post(post_id)
    if not post:
        abort(404)
    selected = (post["platforms"] or "facebook,instagram").split(",")
    results = results_from_json(post["post_results"] or "")
    return render_template(
        "post.html",
        post=post,
        business_name=Config.BUSINESS_NAME,
        all_platforms=ALL_PLATFORMS,
        selected_platforms=selected,
        post_results=results,
    )


# ── Actions ───────────────────────────────────────────────────────────────────

@app.route("/post/<int:post_id>/approve", methods=["POST"])
@login_required
def approve(post_id):
    set_status(post_id, "approved")
    return redirect(url_for("post_detail", post_id=post_id))


@app.route("/post/<int:post_id>/reject", methods=["POST"])
@login_required
def reject(post_id):
    set_status(post_id, "rejected")
    return redirect(url_for("dashboard"))


@app.route("/post/<int:post_id>/edit", methods=["POST"])
@login_required
def edit(post_id):
    generated_text = request.form.get("generated_text", "")
    hashtags = request.form.get("hashtags", "")
    notes = request.form.get("notes", "")
    platforms = ",".join(request.form.getlist("platforms"))
    update_post(post_id, generated_text, hashtags, platforms, notes)
    flash("Changes saved.", "success")
    return redirect(url_for("post_detail", post_id=post_id))


@app.route("/post/<int:post_id>/publish", methods=["POST"])
@login_required
def publish(post_id):
    post = get_post(post_id)
    if not post:
        abort(404)

    platforms = (post["platforms"] or "").split(",")
    platforms = [p.strip() for p in platforms if p.strip()]
    if not platforms:
        flash("No platforms selected.", "error")
        return redirect(url_for("post_detail", post_id=post_id))

    image_path = post["image_path"] or None
    full_text = f"{post['generated_text']}\n\n{post['hashtags']}\n\n{post['referral_link']}"

    results = post_to_platforms(
        text=post["generated_text"],
        hashtags=f"{post['hashtags']}\n{post['referral_link']}",
        image_path=image_path,
        platforms=platforms,
    )

    set_posted(post_id, results_to_json(results))

    success_count = sum(1 for r in results.values() if r.get("success"))
    flash(
        f"Posted to {success_count}/{len(platforms)} platforms.",
        "success" if success_count == len(platforms) else "warning",
    )
    return redirect(url_for("post_detail", post_id=post_id))


# ── Image serving ─────────────────────────────────────────────────────────────

@app.route("/image/<path:filename>")
@login_required
def serve_image(filename):
    full = os.path.join(os.getcwd(), Config.UPLOADS_PATH, filename)
    if not os.path.exists(full):
        abort(404)
    return send_file(full)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
