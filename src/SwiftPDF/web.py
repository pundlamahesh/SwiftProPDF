import argparse
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import Flask, after_this_request, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from SwiftPDF.auth import (
    AuthError,
    admin_stats,
    authenticate_user_by_otp,
    authenticate_user,
    create_user,
    create_user_with_role,
    create_verified_user,
    delete_user,
    get_user,
    get_user_by_email,
    init_db,
    list_audit_events,
    list_users,
    log_audit_event,
    set_user_role,
    unlock_user,
    update_user_password,
    update_user,
    validate_registration_details,
)
from SwiftPDF.core import (
    PdfSplitError, PdfUnlockError, split_pdf, unlock_pdf,
    PdfMergeError, merge_pdfs,
    PdfCompressError, compress_pdf,
    ImageConversionError, pdf_to_images, images_to_pdf,
    PdfConversionError, pdf_to_word, pdf_to_powerpoint, pdf_to_excel,
    OfficeConversionError, office_to_pdf,
    PdfEditError, rotate_pdf_pages, delete_pdf_pages,
)
from SwiftPDF.email_otp import (
    EmailOtpError,
    generate_otp,
    send_login_otp,
    send_password_reset_otp,
    send_registration_otp,
)


def load_env_file() -> None:
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def create_app() -> Flask:
    load_env_file()
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
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SWIFTPDF_COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
    )
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

    def admin_required(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            user = current_user()
            if user is None:
                return redirect(url_for("login"))
            if not user["is_admin"]:
                log_audit("admin_denied", "Non-admin attempted to access admin area.", user["id"])
                return render_template("index.html", error="Admin access is required.", user=user), 403
            return view(*args, **kwargs)

        return wrapped_view

    def log_audit(event_type: str, details: str = "", user_id: int | None = None) -> None:
        actor_id = user_id
        if actor_id is None:
            user = current_user()
            actor_id = int(user["id"]) if user else None
        log_audit_event(
            app.config["DATABASE"],
            event_type,
            user_id=actor_id,
            details=details,
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip(),
        )

    def error_response(message: str, status_code: int):
        if wants_json():
            return jsonify({"error": message}), status_code
        return render_template("index.html", error=message, user=current_user()), status_code

    def render_register(error: str = "", **values):
        return render_template("register.html", error=error, **values)

    def render_verify_registration(error: str = ""):
        pending = session.get("pending_registration") or {}
        return render_template(
            "verify_registration.html",
            error=error,
            email=pending.get("email", ""),
        )

    def otp_expiry() -> datetime:
        return datetime.now(timezone.utc) + timedelta(
            minutes=int(os.environ.get("REGISTRATION_OTP_EXPIRY_MINUTES", "10"))
        )

    def store_pending_otp(key: str, email: str, otp: str) -> None:
        session[key] = {
            "email": email.strip().lower(),
            "otp_hash": generate_password_hash(otp),
            "expires_at": otp_expiry().isoformat(),
        }
        session.permanent = True

    def verify_pending_otp(key: str, otp: str) -> tuple[dict, str]:
        pending = session.get(key)
        if not pending:
            return {}, "Verification session expired. Please request a new code."

        expires_at = datetime.fromisoformat(pending["expires_at"])
        if expires_at < datetime.now(timezone.utc):
            session.pop(key, None)
            return {}, "Verification code expired. Please request a new code."

        if not check_password_hash(pending["otp_hash"], otp.strip()):
            return pending, "Invalid verification code."

        return pending, ""

    def render_admin(error: str = "", success: str = "", status_code: int = 200):
        return render_template(
            "admin.html",
            user=current_user(),
            users=list_users(app.config["DATABASE"]),
            stats=admin_stats(app.config["DATABASE"]),
            audit_events=list_audit_events(app.config["DATABASE"], limit=75),
            error=error,
            success=success,
        ), status_code

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
            return render_register(
                error="Passwords do not match.",
                first_name=first_name,
                last_name=last_name,
                email=email,
            ), 400

        try:
            validate_registration_details(app.config["DATABASE"], first_name, last_name, email.strip().lower(), password)
        except AuthError as exc:
            return render_register(
                error=str(exc),
                first_name=first_name,
                last_name=last_name,
                email=email,
            ), 400

        otp = generate_otp()
        try:
            send_registration_otp(email.strip().lower(), otp)
        except EmailOtpError as exc:
            return render_register(
                error=str(exc),
                first_name=first_name,
                last_name=last_name,
                email=email,
            ), 500

        session["pending_registration"] = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email.strip().lower(),
            "password_hash": generate_password_hash(password),
            "otp_hash": generate_password_hash(otp),
            "expires_at": otp_expiry().isoformat(),
        }
        session.permanent = True
        log_audit("registration_otp_sent", f"Sent registration OTP to {email.strip().lower()}.")
        return redirect(url_for("verify_registration"))

    @app.route("/register/verify", methods=["GET", "POST"])
    def verify_registration():
        pending = session.get("pending_registration")
        if not pending:
            return redirect(url_for("register"))

        if request.method == "GET":
            return render_verify_registration()

        expires_at = datetime.fromisoformat(pending["expires_at"])
        if expires_at < datetime.now(timezone.utc):
            session.pop("pending_registration", None)
            return render_register(error="Verification code expired. Please register again."), 400

        otp = request.form.get("otp", "").strip()
        if not check_password_hash(pending["otp_hash"], otp):
            return render_verify_registration(error="Invalid verification code."), 400

        session.clear()
        try:
            user_id = create_verified_user(
                app.config["DATABASE"],
                pending["first_name"],
                pending["last_name"],
                pending["email"],
                pending["password_hash"],
            )
        except AuthError as exc:
            return render_register(error=str(exc), email=pending["email"]), 400

        session["user_id"] = user_id
        session.permanent = True
        log_audit("register", f"Account registered for {pending['email']}.", user_id)
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
            log_audit("login_failed", f"Failed login for {email}.")
            return render_template("login.html", error=str(exc), email=email), 400

        session.clear()
        session["user_id"] = user["id"]
        session.permanent = True
        log_audit("login", "User logged in.", int(user["id"]))
        return redirect(url_for("index"))

    @app.route("/login/otp", methods=["GET", "POST"])
    def login_otp():
        if request.method == "GET":
            return render_template("login_otp.html")

        email = request.form.get("email", "").strip().lower()
        account = get_user_by_email(app.config["DATABASE"], email)
        if account is None:
            return render_template("login_otp.html", error="Account not found.", email=email), 404

        otp = generate_otp()
        try:
            send_login_otp(email, otp)
        except EmailOtpError as exc:
            return render_template("login_otp.html", error=str(exc), email=email), 500

        store_pending_otp("pending_login_otp", email, otp)
        log_audit("login_otp_sent", f"Sent login OTP to {email}.", int(account["id"]))
        return redirect(url_for("verify_login_otp"))

    @app.route("/login/otp/verify", methods=["GET", "POST"])
    def verify_login_otp():
        pending = session.get("pending_login_otp")
        if not pending:
            return redirect(url_for("login_otp"))

        if request.method == "GET":
            return render_template("verify_login_otp.html", email=pending["email"])

        pending, error = verify_pending_otp("pending_login_otp", request.form.get("otp", ""))
        if error:
            return render_template("verify_login_otp.html", error=error, email=pending.get("email", "")), 400

        session.clear()
        try:
            user = authenticate_user_by_otp(app.config["DATABASE"], pending["email"])
        except AuthError as exc:
            return render_template("login_otp.html", error=str(exc), email=pending["email"]), 400

        session["user_id"] = user["id"]
        session.permanent = True
        log_audit("login_otp", "User logged in with OTP.", int(user["id"]))
        return redirect(url_for("index"))

    @app.route("/forgot-password", methods=["GET", "POST"])
    def forgot_password():
        if request.method == "GET":
            return render_template("forgot_password.html")

        email = request.form.get("email", "").strip().lower()
        account = get_user_by_email(app.config["DATABASE"], email)
        if account is None:
            return render_template("forgot_password.html", error="Account not found.", email=email), 404

        otp = generate_otp()
        try:
            send_password_reset_otp(email, otp)
        except EmailOtpError as exc:
            return render_template("forgot_password.html", error=str(exc), email=email), 500

        store_pending_otp("pending_password_reset", email, otp)
        log_audit("password_reset_otp_sent", f"Sent password reset OTP to {email}.", int(account["id"]))
        return redirect(url_for("reset_password"))

    @app.route("/reset-password", methods=["GET", "POST"])
    def reset_password():
        pending = session.get("pending_password_reset")
        if not pending:
            return redirect(url_for("forgot_password"))

        if request.method == "GET":
            return render_template("reset_password.html", email=pending["email"])

        pending, error = verify_pending_otp("pending_password_reset", request.form.get("otp", ""))
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if error:
            return render_template("reset_password.html", error=error, email=pending.get("email", "")), 400

        if password != confirm_password:
            return render_template("reset_password.html", error="Passwords do not match.", email=pending["email"]), 400

        try:
            update_user_password(app.config["DATABASE"], pending["email"], password)
        except AuthError as exc:
            return render_template("reset_password.html", error=str(exc), email=pending["email"]), 400

        session.pop("pending_password_reset", None)
        account = get_user_by_email(app.config["DATABASE"], pending["email"])
        log_audit("password_reset", f"Password reset completed for {pending['email']}.", int(account["id"]) if account else None)
        return render_template("login.html", status="Password reset complete. You can log in now.", email=pending["email"])

    @app.post("/logout")
    def logout():
        user = current_user()
        if user:
            log_audit("logout", "User logged out.", int(user["id"]))
        session.clear()
        return redirect(url_for("login"))

    @app.get("/admin")
    @admin_required
    def admin_dashboard():
        return render_admin()

    @app.post("/admin/users")
    @admin_required
    def admin_create_user():
        first_name = request.form.get("first_name", "")
        last_name = request.form.get("last_name", "")
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        role = request.form.get("role", "user")

        try:
            user_id = create_user_with_role(app.config["DATABASE"], first_name, last_name, email, password, role)
        except AuthError as exc:
            return render_admin(error=str(exc), status_code=400)

        log_audit("admin_create_user", f"Created user id {user_id} ({email}) with role {role}.")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/users/<int:user_id>")
    @admin_required
    def admin_update_user(user_id: int):
        active_user = current_user()
        role = request.form.get("role", "user")

        if int(active_user["id"]) == user_id and role != "admin":
            log_audit("admin_role_change_blocked", "Admin attempted to remove own admin role.")
            return render_admin(error="You cannot remove your own admin role.", status_code=400)

        if role != "admin" and admin_stats(app.config["DATABASE"])["admins"] <= 1:
            existing_user = get_user(app.config["DATABASE"], user_id)
            if existing_user and existing_user["is_admin"]:
                return render_admin(error="At least one admin account is required.", status_code=400)

        try:
            update_user(
                app.config["DATABASE"],
                user_id,
                request.form.get("first_name", ""),
                request.form.get("last_name", ""),
                request.form.get("email", ""),
                role,
                request.form.get("password", ""),
            )
        except AuthError as exc:
            return render_admin(error=str(exc), status_code=400)

        log_audit("admin_update_user", f"Updated user id {user_id}.")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/users/<int:user_id>/delete")
    @admin_required
    def admin_delete_user(user_id: int):
        active_user = current_user()
        if int(active_user["id"]) == user_id:
            log_audit("admin_delete_blocked", "Admin attempted to delete own account.")
            return render_admin(error="You cannot delete your own account.", status_code=400)

        account = get_user(app.config["DATABASE"], user_id)
        if account is None:
            return render_admin(error="User not found.", status_code=404)

        if account["is_admin"] and admin_stats(app.config["DATABASE"])["admins"] <= 1:
            return render_admin(error="At least one admin account is required.", status_code=400)

        email = str(account["email"])
        delete_user(app.config["DATABASE"], user_id)
        log_audit("admin_delete_user", f"Deleted user {email}.")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/users/<int:user_id>/unlock")
    @admin_required
    def admin_unlock_user(user_id: int):
        unlock_user(app.config["DATABASE"], user_id)
        log_audit("admin_unlock_user", f"Unlocked user id {user_id}.")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/users/<int:user_id>/role")
    @admin_required
    def admin_set_user_role(user_id: int):
        role = request.form.get("role", "user")
        if int(current_user()["id"]) == user_id and role != "admin":
            log_audit("admin_role_change_blocked", "Admin attempted to remove own admin role.")
            return redirect(url_for("admin_dashboard"))

        if role != "admin" and admin_stats(app.config["DATABASE"])["admins"] <= 1:
            existing_user = get_user(app.config["DATABASE"], user_id)
            if existing_user and existing_user["is_admin"]:
                return redirect(url_for("admin_dashboard"))

        try:
            set_user_role(app.config["DATABASE"], user_id, role)
        except AuthError:
            return redirect(url_for("admin_dashboard"))

        log_audit("admin_role_changed", f"Changed user id {user_id} to {role}.")
        return redirect(url_for("admin_dashboard"))

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
        log_audit("tool_unlock", f"Unlocked {filename}.")

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
        log_audit("tool_split", f"Split {filename} with pages {page_ranges}.")

        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response

        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/merge")
    @login_required
    def merge():
        uploaded_files = request.files.getlist("pdfs")
        
        if not uploaded_files or all(f.filename == "" for f in uploaded_files):
            return error_response("Choose at least one PDF file.", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpdf-merger-"))
        input_paths = []
        
        try:
            for idx, uploaded_file in enumerate(uploaded_files):
                if uploaded_file.filename == "":
                    continue
                
                filename = secure_filename(uploaded_file.filename)
                if not filename.lower().endswith(".pdf"):
                    shutil.rmtree(work_dir, ignore_errors=True)
                    return error_response("Only PDF files are supported.", 400)
                
                input_path = work_dir / f"{idx:02d}-{uuid4()}-{filename}"
                uploaded_file.save(input_path)
                input_paths.append(input_path)
            
            if not input_paths:
                shutil.rmtree(work_dir, ignore_errors=True)
                return error_response("Choose at least one PDF file.", 400)
            
            output_name = "merged.pdf"
            output_path = work_dir / output_name
            
            merge_pdfs(input_paths, output_path, overwrite=True)
            log_audit("tool_merge", f"Merged {len(input_paths)} PDF file(s).")
        except PdfMergeError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)
        except Exception as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response("Could not merge PDFs.", 400)
        
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/compress")
    @login_required
    def compress():
        uploaded_file = request.files.get("pdf")
        level = request.form.get("level", "medium")
        
        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a PDF file first.", 400)
        
        filename = secure_filename(uploaded_file.filename)
        if not filename.lower().endswith(".pdf"):
            return error_response("Only PDF files are supported.", 400)
        
        if level not in ("low", "medium", "high"):
            return error_response("Invalid compression level.", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpdf-compress-"))
        input_path = work_dir / f"{uuid4()}-{filename}"
        output_name = f"{Path(filename).stem}-compressed.pdf"
        output_path = work_dir / output_name
        uploaded_file.save(input_path)
        
        try:
            compress_pdf(input_path, output_path, level=level, overwrite=True)
        except PdfCompressError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)
        log_audit("tool_compress", f"Compressed {filename} at {level} level.")
        
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/pdf-to-images")
    @login_required
    def pdf_to_images_route():
        uploaded_file = request.files.get("pdf")
        dpi = request.form.get("dpi", "150")
        
        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a PDF file first.", 400)
        
        filename = secure_filename(uploaded_file.filename)
        if not filename.lower().endswith(".pdf"):
            return error_response("Only PDF files are supported.", 400)
        
        try:
            dpi = int(dpi)
        except ValueError:
            return error_response("DPI must be a number between 72 and 300.", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpdf-pdf2img-"))
        input_path = work_dir / f"{uuid4()}-{filename}"
        images_dir = work_dir / "images"
        uploaded_file.save(input_path)
        
        try:
            pdf_to_images(input_path, images_dir, dpi=dpi)
            
            # Create ZIP file with all images
            zip_path = work_dir / "images.zip"
            import zipfile
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for img_path in sorted(images_dir.glob("*.jpg")):
                    zf.write(img_path, arcname=img_path.name)
            
            output_name = f"{Path(filename).stem}-images.zip"
            log_audit("tool_pdf_to_images", f"Converted {filename} to images at {dpi} DPI.")
        except ImageConversionError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)
        
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(zip_path, as_attachment=True, download_name=output_name)

    @app.post("/images-to-pdf")
    @login_required
    def images_to_pdf_route():
        uploaded_files = request.files.getlist("images")
        
        if not uploaded_files or all(f.filename == "" for f in uploaded_files):
            return error_response("Choose at least one image file.", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpdf-img2pdf-"))
        input_paths = []
        
        try:
            for idx, uploaded_file in enumerate(uploaded_files):
                if uploaded_file.filename == "":
                    continue
                
                filename = secure_filename(uploaded_file.filename)
                if not filename.lower().split(".")[-1] in ("jpg", "jpeg", "png", "gif", "bmp"):
                    shutil.rmtree(work_dir, ignore_errors=True)
                    return error_response("Only image files are supported (JPG, PNG, GIF, BMP).", 400)
                
                input_path = work_dir / f"{idx:02d}-{uuid4()}-{filename}"
                uploaded_file.save(input_path)
                input_paths.append(input_path)
            
            if not input_paths:
                shutil.rmtree(work_dir, ignore_errors=True)
                return error_response("Choose at least one image file.", 400)
            
            output_name = "images.pdf"
            output_path = work_dir / output_name
            
            images_to_pdf(input_paths, output_path, overwrite=True)
            log_audit("tool_images_to_pdf", f"Created PDF from {len(input_paths)} image file(s).")
        except ImageConversionError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)
        
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/pdf-to-word")
    @login_required
    def pdf_to_word_route():
        uploaded_file = request.files.get("pdf")
        
        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a PDF file first.", 400)
        
        filename = secure_filename(uploaded_file.filename)
        if not filename.lower().endswith(".pdf"):
            return error_response("Only PDF files are supported.", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpdf-pdf2word-"))
        input_path = work_dir / f"{uuid4()}-{filename}"
        output_name = f"{Path(filename).stem}.docx"
        output_path = work_dir / output_name
        uploaded_file.save(input_path)
        
        try:
            pdf_to_word(input_path, output_path, overwrite=True)
        except PdfConversionError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)
        log_audit("tool_pdf_to_word", f"Converted {filename} to Word.")
        
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/pdf-to-powerpoint")
    @login_required
    def pdf_to_powerpoint_route():
        uploaded_file = request.files.get("pdf")
        
        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a PDF file first.", 400)
        
        filename = secure_filename(uploaded_file.filename)
        if not filename.lower().endswith(".pdf"):
            return error_response("Only PDF files are supported.", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpdf-pdf2ppt-"))
        input_path = work_dir / f"{uuid4()}-{filename}"
        output_name = f"{Path(filename).stem}.pptx"
        output_path = work_dir / output_name
        uploaded_file.save(input_path)
        
        try:
            pdf_to_powerpoint(input_path, output_path, overwrite=True)
        except PdfConversionError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)
        log_audit("tool_pdf_to_powerpoint", f"Converted {filename} to PowerPoint.")
        
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/pdf-to-excel")
    @login_required
    def pdf_to_excel_route():
        uploaded_file = request.files.get("pdf")
        
        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a PDF file first.", 400)
        
        filename = secure_filename(uploaded_file.filename)
        if not filename.lower().endswith(".pdf"):
            return error_response("Only PDF files are supported.", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpdf-pdf2excel-"))
        input_path = work_dir / f"{uuid4()}-{filename}"
        output_name = f"{Path(filename).stem}.xlsx"
        output_path = work_dir / output_name
        uploaded_file.save(input_path)
        
        try:
            pdf_to_excel(input_path, output_path, overwrite=True)
        except PdfConversionError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)
        log_audit("tool_pdf_to_excel", f"Converted {filename} to Excel.")
        
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/office-to-pdf")
    @login_required
    def office_to_pdf_route():
        uploaded_file = request.files.get("document")
        
        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a document file first.", 400)
        
        filename = secure_filename(uploaded_file.filename)
        extension = filename.lower().split(".")[-1]
        if extension not in ("docx", "doc", "xlsx", "xls", "pptx", "ppt"):
            return error_response("Supported formats: DOCX, DOC, XLSX, XLS, PPTX, PPT", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpdf-office2pdf-"))
        input_path = work_dir / f"{uuid4()}-{filename}"
        output_name = f"{Path(filename).stem}.pdf"
        output_path = work_dir / output_name
        uploaded_file.save(input_path)
        
        try:
            office_to_pdf(input_path, output_path, overwrite=True)
        except OfficeConversionError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)
        log_audit("tool_office_to_pdf", f"Converted {filename} to PDF.")
        
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/rotate-pdf")
    @login_required
    def rotate_pdf():
        uploaded_file = request.files.get("pdf")
        page_ranges = request.form.get("page_ranges", "")
        angle = request.form.get("angle", "90")
        
        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a PDF file first.", 400)
        
        filename = secure_filename(uploaded_file.filename)
        if not filename.lower().endswith(".pdf"):
            return error_response("Only PDF files are supported.", 400)
        
        try:
            angle = int(angle)
        except ValueError:
            return error_response("Rotation angle must be 90, 180, 270, or -90.", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpdf-rotate-"))
        input_path = work_dir / f"{uuid4()}-{filename}"
        output_name = f"{Path(filename).stem}-rotated.pdf"
        output_path = work_dir / output_name
        uploaded_file.save(input_path)
        
        try:
            rotate_pdf_pages(input_path, output_path, page_ranges, angle, overwrite=True)
        except PdfEditError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)
        log_audit("tool_rotate_pdf", f"Rotated {filename} by {angle} degrees.")
        
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/delete-pdf-pages")
    @login_required
    def delete_pdf_pages_route():
        uploaded_file = request.files.get("pdf")
        page_ranges = request.form.get("page_ranges", "")
        
        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a PDF file first.", 400)
        
        filename = secure_filename(uploaded_file.filename)
        if not filename.lower().endswith(".pdf"):
            return error_response("Only PDF files are supported.", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpdf-delete-"))
        input_path = work_dir / f"{uuid4()}-{filename}"
        output_name = f"{Path(filename).stem}-pages-deleted.pdf"
        output_path = work_dir / output_name
        uploaded_file.save(input_path)
        
        try:
            delete_pdf_pages(input_path, output_path, page_ranges, overwrite=True)
        except PdfEditError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)
        log_audit("tool_delete_pages", f"Deleted pages {page_ranges} from {filename}.")
        
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
