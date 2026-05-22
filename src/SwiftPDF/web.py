import argparse
import os
import shutil
import tempfile
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import Flask, after_this_request, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.utils import secure_filename

from SwiftPDF.auth import AuthError, authenticate_user, create_user, get_user, init_db
from SwiftPDF.core import PdfSplitError, PdfUnlockError, split_pdf, unlock_pdf


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
    package_instance = Path(app.root_path) / "instance"
    legacy_instance = Path(app.root_path).parent / "instance"
    app.config["DATABASE"] = package_instance / "swiftpdf.sqlite3"

    legacy_database = legacy_instance / "swiftpdf.sqlite3"
    if not app.config["DATABASE"].exists() and legacy_database.exists():
        app.config["DATABASE"].parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_database, app.config["DATABASE"])

    app.secret_key = os.environ.get("SWIFTPDF_SECRET_KEY", "dev-change-this-secret-key")
    init_db(app.config["DATABASE"])

    def wants_json() -> bool:
        return request.headers.get("X-Requested-With") == "fetch"

    def current_user():
        user_id = session.get("user_id")
        if user_id is None:
            return None
        return get_user(app.config["DATABASE"], int(user_id))

    def login_required(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if current_user() is None:
                if wants_json():
                    return jsonify({"error": "Please log in to continue."}), 401
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped_view

    def error_response(message: str, status_code: int):
        if wants_json():
            return jsonify({"error": message}), status_code
        return render_template("index.html", error=message, user=current_user()), status_code

    @app.get("/")
    @login_required
    def index():
        return render_template("index.html", user=current_user())

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "GET":
            return render_template("register.html")

        first_name = request.form.get("first_name", "")
        last_name = request.form.get("last_name", "")
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if password != confirm_password:
            return render_template(
                "register.html",
                error="Passwords do not match.",
                first_name=first_name,
                last_name=last_name,
                email=email,
            ), 400

        try:
            user_id = create_user(app.config["DATABASE"], first_name, last_name, email, password)
        except AuthError as exc:
            return render_template(
                "register.html",
                error=str(exc),
                first_name=first_name,
                last_name=last_name,
                email=email,
            ), 400

        session.clear()
        session["user_id"] = user_id
        return redirect(url_for("index"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_template("login.html")

        email = request.form.get("email", "")
        password = request.form.get("password", "")

        try:
            user = authenticate_user(app.config["DATABASE"], email, password)
        except AuthError as exc:
            return render_template("login.html", error=str(exc), email=email), 400

        session.clear()
        session["user_id"] = user["id"]
        return redirect(url_for("index"))

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.post("/unlock")
    @login_required
    def unlock():
        uploaded_file = request.files.get("pdf")
        password = request.form.get("password", "")

        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a PDF file first.", 400)

        filename = secure_filename(uploaded_file.filename)
        if not filename.lower().endswith(".pdf"):
            return error_response("Only PDF files are supported.", 400)

        work_dir = Path(tempfile.mkdtemp(prefix="swiftpdf-"))
        input_path = work_dir / f"{uuid4()}-{filename}"
        output_name = f"{Path(filename).stem}-unlocked.pdf"
        output_path = work_dir / output_name
        uploaded_file.save(input_path)

        try:
            unlock_pdf(input_path, output_path, password, overwrite=True)
        except PdfUnlockError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)

        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response

        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/split")
    @login_required
    def split():
        uploaded_file = request.files.get("pdf")
        page_ranges = request.form.get("page_ranges", "")

        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a PDF file first.", 400)

        filename = secure_filename(uploaded_file.filename)
        if not filename.lower().endswith(".pdf"):
            return error_response("Only PDF files are supported.", 400)

        work_dir = Path(tempfile.mkdtemp(prefix="swiftpdf-splitter-"))
        input_path = work_dir / f"{uuid4()}-{filename}"
        output_name = f"{Path(filename).stem}-split.pdf"
        output_path = work_dir / output_name
        uploaded_file.save(input_path)

        try:
            split_pdf(input_path, output_path, page_ranges, overwrite=True)
        except PdfSplitError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)

        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response

        return send_file(output_path, as_attachment=True, download_name=output_name)

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swiftpdf-ui",
        description="Start the local SwiftPDF web interface.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host address to bind.")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    app = create_app()
    app.run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
