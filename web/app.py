import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, redirect, url_for, request, send_file, abort
from email_automation.config import Config
from email_automation.database import (
    init_db, get_post, get_posts, update_post, set_status
)

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY


@app.route("/")
def dashboard():
    pending = get_posts("pending")
    approved = get_posts("approved")
    rejected = get_posts("rejected")
    return render_template(
        "dashboard.html",
        pending=pending,
        approved=approved,
        rejected=rejected,
        business_name=Config.BUSINESS_NAME,
    )


@app.route("/post/<int:post_id>")
def post_detail(post_id):
    post = get_post(post_id)
    if not post:
        abort(404)
    return render_template("post.html", post=post, business_name=Config.BUSINESS_NAME)


@app.route("/post/<int:post_id>/approve", methods=["POST"])
def approve(post_id):
    set_status(post_id, "approved")
    return redirect(url_for("dashboard"))


@app.route("/post/<int:post_id>/reject", methods=["POST"])
def reject(post_id):
    set_status(post_id, "rejected")
    return redirect(url_for("dashboard"))


@app.route("/post/<int:post_id>/edit", methods=["POST"])
def edit(post_id):
    generated_text = request.form.get("generated_text", "")
    hashtags = request.form.get("hashtags", "")
    notes = request.form.get("notes", "")
    update_post(post_id, generated_text, hashtags, notes)
    return redirect(url_for("post_detail", post_id=post_id))


@app.route("/image/<path:filename>")
def serve_image(filename):
    full = os.path.join(os.getcwd(), Config.UPLOADS_PATH, filename)
    if not os.path.exists(full):
        abort(404)
    return send_file(full)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
