import argparse
import os
import shutil
import tempfile
from datetime import datetime
from functools import wraps
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse

from flask import Flask, abort, after_this_request, g, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.utils import secure_filename

from SwiftProPDF.auth import (
    AuthError,
    admin_stats,
    authenticate_user,
    create_user,
    create_user_session,
    create_user_with_role,
    delete_user_session,
    delete_user,
    get_user,
    get_user_by_email,
    init_db,
    is_user_session_active,
    list_audit_events,
    list_users,
    log_audit_event,
    set_user_security_questions,
    set_user_role,
    unlock_user,
    update_user,
    update_user_password,
    validate_security_answers,
    validate_registration_details,
    verify_user_password,
    verify_user_security_answers,
    get_setting,
    set_setting,
    ensure_default_settings,
    reset_all_weekly_usage,
    get_total_usage,
    get_weekly_total_usage,
    record_tool_usage,
)
from SwiftProPDF.core import (
    PdfSplitError, PdfUnlockError, PdfLockError, split_pdf, unlock_pdf, lock_pdf,
    PdfMergeError, merge_pdfs,
    PdfCompressError, compress_pdf, compress_image,
    ImageConversionError, pdf_to_images, images_to_pdf,
    PdfConversionError, pdf_to_word, pdf_to_powerpoint, pdf_to_excel,
    OfficeConversionError, office_to_pdf,
    PdfEditError, QrCodeError, generate_qr_code, rotate_pdf_pages, delete_pdf_pages,
)
from SwiftProPDF.database import using_postgres
from SwiftProPDF.web_app.job_service import async_tools_enabled, enqueue_tool_job, job_result, jobs_root
from SwiftProPDF.web_app.tool_catalog import TOOLS, TOOLS_BY_PATH, TOOL_BY_POST_PATH, TOOL_PATHS



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
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "200"))
    app.config["MAX_CONTENT_LENGTH"] = max_upload_mb * 1024 * 1024
    package_root = Path(app.root_path).parent
    package_instance = package_root / "instance"
    legacy_instance = package_root.parent / "instance"
    app.config["INSTANCE_PATH"] = package_instance
    app.config["DATABASE"] = package_instance / "swiftpropdf.sqlite3"

    legacy_database = legacy_instance / "swiftpropdf.sqlite3"
    if not using_postgres() and not app.config["DATABASE"].exists() and legacy_database.exists():
        app.config["DATABASE"].parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_database, app.config["DATABASE"])

    app.secret_key = os.environ.get("SWIFTPROPDF_SECRET_KEY", "dev-change-this-secret-key")
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SWIFTPROPDF_COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
    )
    init_db(app.config["DATABASE"])
    ensure_default_settings(app.config["DATABASE"])

    @app.context_processor
    def inject_globals():
        return {
            "current_year": datetime.now().year,
            "user": current_user(),
            "remaining_quota": get_remaining_quota(),
            "usage_limit": get_usage_limit(),
            "quota_message": get_quota_message(),
        }

    tools = TOOLS
    tools_by_path = TOOLS_BY_PATH
    tool_paths = TOOL_PATHS
    tool_by_post_path = TOOL_BY_POST_PATH

    def get_request_ip() -> str:
        return request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()

    @app.before_request
    def ensure_anonymous_id():
        g.anonymous_id = request.cookies.get("anonymous_id")
        if not g.anonymous_id:
            g.anonymous_id = str(uuid4())
        g.request_ip = get_request_ip()

    @app.after_request
    def persist_anonymous_id(response):
        if hasattr(g, "anonymous_id") and request.cookies.get("anonymous_id") != g.anonymous_id:
            response.set_cookie(
                "anonymous_id",
                g.anonymous_id,
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                samesite="Lax",
            )
        return response

    def wants_json() -> bool:
        return request.headers.get("X-Requested-With") == "fetch"

    def current_user():
        user_id = session.get("user_id")
        session_token = session.get("session_token")
        if user_id is None:
            return None
        if not session_token or not is_user_session_current(int(user_id), str(session_token)):
            session.clear()
            return None
        return get_user(app.config["DATABASE"], int(user_id))

    def is_user_session_current(user_id: int, session_token: str) -> bool:
        return is_user_session_active(app.config["DATABASE"], user_id, session_token)

    def start_user_session(user_id: int) -> None:
        session_token = uuid4().hex
        create_user_session(
            app.config["DATABASE"],
            user_id,
            session_token,
            user_agent=request.headers.get("User-Agent", ""),
            ip_address=get_request_ip(),
        )
        session.clear()
        session["user_id"] = user_id
        session["session_token"] = session_token
        session.permanent = True

    def get_usage_limit() -> int:
        user = current_user()
        if user is None:
            return int(get_setting(app.config["DATABASE"], "guest_weekly_limit", "5") or 5)
        if user["is_admin"] or user["is_premium"]:
            return 0
        return int(get_setting(app.config["DATABASE"], "free_weekly_limit", "10") or 10)

    def get_current_usage() -> int:
        user = current_user()
        if user:
            return get_total_usage(app.config["DATABASE"], user_id=int(user["id"]))
        return get_total_usage(app.config["DATABASE"], anonymous_id=g.anonymous_id, ip_address=g.request_ip)

    def get_remaining_quota() -> int | None:
        limit = get_usage_limit()
        if limit <= 0:
            return None
        return max(0, limit - get_current_usage())

    def get_quota_message() -> str:
        limit = get_usage_limit()
        if limit <= 0:
            return "Unlimited conversions are available for your plan."

        remaining = get_remaining_quota()
        if remaining is None or remaining <= 0:
            if current_user():
                return "You have used all of your weekly conversions. Upgrade to Premium or contact support for more."
            return "You have used all guest weekly conversions. Create a free account to continue."
        return f"{remaining} free conversion{'s' if remaining != 1 else ''} remaining this week."

    def track_tool_usage(tool_name: str) -> None:
        user = current_user()
        if user:
            record_tool_usage(
                app.config["DATABASE"],
                tool_name,
                user_id=int(user["id"]),
                ip_address=g.request_ip,
            )
        else:
            record_tool_usage(
                app.config["DATABASE"],
                tool_name,
                anonymous_id=g.anonymous_id,
                ip_address=g.request_ip,
            )

    def current_actor() -> dict:
        user = current_user()
        if user:
            return {
                "user_id": int(user["id"]),
                "anonymous_id": "",
                "ip_address": g.request_ip,
            }
        return {
            "user_id": None,
            "anonymous_id": g.anonymous_id,
            "ip_address": g.request_ip,
        }

    @app.before_request
    def enforce_usage_limit():
        if request.method != "POST":
            return None
        path = request.path.lstrip("/")
        if path not in tool_by_post_path:
            return None
        limit = get_usage_limit()
        if limit <= 0:
            return None
        total = get_current_usage()
        if total >= limit:
            if current_user():
                message = "You have used all of your weekly conversions. Upgrade to Premium or contact support."
            else:
                message = "You have used all guest weekly conversions. Create a free account to continue."
            return error_response(message, 429)

    @app.before_request
    def enqueue_async_tool_request():
        if request.method != "POST" or not async_tools_enabled() or not wants_json():
            return None
        path = request.path.lstrip("/")
        tool_name = tool_by_post_path.get(path)
        if tool_name is None:
            return None
        try:
            job_id, _payload = enqueue_tool_job(
                tool_name,
                request.form,
                request.files,
                app.config["INSTANCE_PATH"],
                app.config["DATABASE"],
                current_actor(),
            )
        except Exception:
            app.logger.exception("Could not queue background tool job")
            return jsonify({"error": "Could not start the background job. Please try again."}), 503
        return jsonify(
            {
                "job_id": job_id,
                "status_url": url_for("job_status", job_id=job_id),
                "message": "Your file is being processed.",
            }
        ), 202

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
                return render_template("public/index.html", error="Admin access is required.", user=user), 403
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
        tool_path = request.path.lstrip("/")
        if tool_path in tools_by_path:
            return render_tool_page(tools_by_path[tool_path], error=message), status_code
        return render_template("public/index.html", error=message, user=current_user()), status_code

    @app.errorhandler(RequestEntityTooLarge)
    def handle_upload_too_large(exc):
        max_size_mb = max(1, app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024))
        return error_response(f"File is too large. Upload files up to {max_size_mb} MB.", 413)

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc):
        message = exc.description if isinstance(exc.description, str) else exc.name
        return error_response(message, exc.code or 500)

    @app.errorhandler(Exception)
    def handle_unexpected_exception(exc):
        app.logger.exception("Unhandled error while processing request")
        return error_response("The server hit an unexpected error while processing this file.", 500)

    def render_register(error: str = "", **values):
        return render_template("auth/register.html", error=error, **values)

    def render_admin(error: str = "", success: str = "", status_code: int = 200):
        users = list_users(app.config["DATABASE"])
        premium_users = sum(1 for account in users if account["is_premium"])
        weekly_conversions = get_weekly_total_usage(app.config["DATABASE"])
        return render_template(
            "admin/dashboard.html",
            user=current_user(),
            users=users,
            stats=admin_stats(app.config["DATABASE"]),
            audit_events=list_audit_events(app.config["DATABASE"], limit=75),
            premium_users=premium_users,
            weekly_conversions=weekly_conversions,
            guest_weekly_limit=get_setting(app.config["DATABASE"], "guest_weekly_limit", "5"),
            free_weekly_limit=get_setting(app.config["DATABASE"], "free_weekly_limit", "10"),
            premium_weekly_limit=get_setting(app.config["DATABASE"], "premium_weekly_limit", "0"),
            error=error,
            success=success,
        ), status_code

    def render_tool_page(tool: dict, error: str = "") -> str:
        return render_template(
            "tools/tool.html",
            tool=tool,
            tools=tools,
            tools_by_path=tools_by_path,
            remaining_quota=get_remaining_quota(),
            usage_limit=get_usage_limit(),
            quota_message=get_quota_message(),
            error=error,
        )

    @app.get("/")
    def index():
        return render_template("public/home.html", tools=tools)

    @app.get("/about")
    def about():
        return render_template(
            "public/about.html",
            tools=tools,
        )

    @app.get("/pricing")
    def pricing():
        return render_template(
            "public/pricing.html",
            tools=tools,
        )

    @app.get("/contact")
    def contact():
        return render_template(
            "public/contact.html",
            tools=tools,
        )

    @app.get("/faq")
    def faq():
        return render_template(
            "public/faq.html",
            tools=tools,
        )
    @app.get('/guides')
    def guides():
        return render_template(
            'public/guides.html',
            tools=tools,
            )

    @app.get("/privacy")
    def privacy():
        return render_template(
            "public/privacy.html",
            tools=tools,
        )

    @app.get("/terms")
    def terms():
        return render_template(
            "public/terms.html",
            tools=tools,
        )

    @app.get("/account")
    def account():
        user = current_user()
        if user is None:
            return redirect(url_for("login"))

        usage = get_total_usage(app.config["DATABASE"], user_id=int(user["id"]))
        remaining_quota = get_remaining_quota()
        return render_template(
            "account/profile.html",
            user=user,
            usage=usage,
            remaining_quota=remaining_quota,
            usage_limit=get_usage_limit(),
            quota_message=get_quota_message(),
            plan=user["role"].title(),
            security_success="Security questions updated." if request.args.get("security_updated") else "",
        )

    @app.post("/account/security-questions")
    @login_required
    def update_security_questions():
        user = current_user()
        current_password = request.form.get("current_password", "")
        date_of_birth = request.form.get("date_of_birth", "")
        current_city = request.form.get("current_city", "")

        try:
            verify_user_password(app.config["DATABASE"], int(user["id"]), current_password)
            set_user_security_questions(app.config["DATABASE"], int(user["id"]), date_of_birth, current_city)
        except AuthError as exc:
            usage = get_total_usage(app.config["DATABASE"], user_id=int(user["id"]))
            log_audit("security_questions_update_failed", str(exc), int(user["id"]))
            return render_template(
                "account/profile.html",
                user=current_user(),
                usage=usage,
                remaining_quota=get_remaining_quota(),
                usage_limit=get_usage_limit(),
                quota_message=get_quota_message(),
                plan=user["role"].title(),
                security_error=str(exc),
            ), 400

        log_audit("security_questions_updated", "User updated password recovery security answers.", int(user["id"]))
        return redirect(url_for("account", security_updated="1"))

    @app.get("/profile")
    def profile():
        return redirect(url_for("account"))

    @app.get("/jobs/<job_id>")
    def job_status(job_id: str):
        result = job_result(job_id)
        state = result.state

        if state in ("PENDING", "RECEIVED", "STARTED"):
            return jsonify({"state": state.lower(), "message": "Your file is still processing."})

        if state == "PROGRESS":
            info = result.info if isinstance(result.info, dict) else {}
            return jsonify({"state": "processing", "message": info.get("message", "Your file is still processing.")})

        if state == "SUCCESS":
            payload = result.result or {}
            if payload.get("status") == "error":
                return jsonify({"state": "failed", "error": payload.get("error", "Could not process the file.")}), 400
            return jsonify(
                {
                    "state": "finished",
                    "download_url": url_for("job_download", job_id=job_id),
                    "download_name": payload.get("download_name", "download"),
                }
            )

        if state == "FAILURE":
            return jsonify({"state": "failed", "error": "The background job failed."}), 500

        return jsonify({"state": state.lower(), "message": "Your file is still processing."})

    @app.get("/jobs/<job_id>/download")
    def job_download(job_id: str):
        result = job_result(job_id)
        if result.state != "SUCCESS":
            return error_response("This file is not ready to download yet.", 404)

        payload = result.result or {}
        if payload.get("status") == "error":
            return error_response(payload.get("error", "Could not process the file."), 400)

        output_path = Path(payload.get("output_path", ""))
        allowed_root = jobs_root(app.config["INSTANCE_PATH"]).resolve()
        try:
            resolved_output = output_path.resolve()
            resolved_output.relative_to(allowed_root)
        except Exception:
            return error_response("The generated file is not available.", 404)

        if not resolved_output.exists():
            return error_response("The generated file is no longer available.", 404)

        return send_file(
            resolved_output,
            as_attachment=True,
            download_name=payload.get("download_name", resolved_output.name),
        )

    @app.get("/<tool_name>")
    def tool_page(tool_name: str):
        tool = tools_by_path.get(tool_name)
        if tool is None:
            return abort(404)
        return render_tool_page(tool)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "GET":
            return render_template("auth/register.html")

        first_name = request.form.get("first_name", "")
        last_name = request.form.get("last_name", "")
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        date_of_birth = request.form.get("date_of_birth", "")
        current_city = request.form.get("current_city", "")

        def register_values() -> dict[str, str]:
            return {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "date_of_birth": date_of_birth,
                "current_city": current_city,
            }

        if password != confirm_password:
            return render_register(
                error="Passwords do not match.",
                **register_values(),
            ), 400

        try:
            validate_registration_details(app.config["DATABASE"], first_name, last_name, email.strip().lower(), password)
            validate_security_answers(date_of_birth, current_city)
        except AuthError as exc:
            return render_register(
                error=str(exc),
                **register_values(),
            ), 400

        try:
            user_id = create_user(
                app.config["DATABASE"],
                first_name,
                last_name,
                email.strip().lower(),
                password,
            )
            set_user_security_questions(app.config["DATABASE"], user_id, date_of_birth, current_city)
        except AuthError as exc:
            return render_register(
                error=str(exc),
                **register_values(),
            ), 400

        start_user_session(user_id)
        log_audit("register", f"Account registered for {email.strip().lower()}.", user_id)
        return redirect(url_for("index"))



    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_template("auth/login.html")

        email = request.form.get("email", "")
        password = request.form.get("password", "")

        try:
            user = authenticate_user(app.config["DATABASE"], email, password)
        except AuthError as exc:
            log_audit("login_failed", f"Failed login for {email}.")
            return render_template("auth/login.html", error=str(exc), email=email), 400

        try:
            start_user_session(int(user["id"]))
        except AuthError as exc:
            log_audit("login_denied", str(exc), int(user["id"]))
            return render_template("auth/login.html", error=str(exc), email=email), 400
        log_audit("login", "User logged in.", int(user["id"]))
        return redirect(url_for("index"))


    @app.route("/forgot-password", methods=["GET", "POST"])
    def forgot_password():
        if request.method == "GET":
            session.pop("pending_password_reset", None)
            return render_template("auth/forgot_password.html", step="account")

        step = request.form.get("step", "account")

        if step == "account":
            email = request.form.get("email", "").strip().lower()
            account = get_user_by_email(app.config["DATABASE"], email)
            log_audit("password_reset_requested", f"Password reset requested for {email}.", int(account["id"]) if account else None)
            if account is None:
                return render_template("auth/forgot_password.html", step="account", error="Account not found.", email=email), 404
            if not account.get("security_questions_configured"):
                return render_template(
                    "auth/forgot_password.html",
                    step="account",
                    error="Security questions are not configured for this account. Contact an administrator or update Account Settings after login.",
                    email=email,
                ), 400

            session["pending_password_reset"] = {
                "user_id": int(account["id"]),
                "email": str(account["email"]),
                "answers_verified": False,
            }
            return render_template("auth/forgot_password.html", step="questions", email=account["email"])

        pending = session.get("pending_password_reset")
        if not pending:
            return redirect(url_for("forgot_password"))

        if step == "questions":
            date_of_birth = request.form.get("date_of_birth", "")
            current_city = request.form.get("current_city", "")
            try:
                verify_user_security_answers(
                    app.config["DATABASE"],
                    int(pending["user_id"]),
                    date_of_birth,
                    current_city,
                )
            except AuthError as exc:
                log_audit("password_reset_failed", str(exc), int(pending["user_id"]))
                return render_template(
                    "auth/forgot_password.html",
                    step="questions",
                    error=str(exc),
                    email=pending["email"],
                    date_of_birth=date_of_birth,
                    current_city=current_city,
                ), 400

            pending["answers_verified"] = True
            session["pending_password_reset"] = pending
            return render_template("auth/forgot_password.html", step="reset", email=pending["email"])

        if step == "reset":
            if not pending.get("answers_verified"):
                return redirect(url_for("forgot_password"))
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            if password != confirm_password:
                return render_template(
                    "auth/forgot_password.html",
                    step="reset",
                    error="Passwords do not match.",
                    email=pending["email"],
                ), 400

            try:
                update_user_password(app.config["DATABASE"], str(pending["email"]), password)
            except AuthError as exc:
                return render_template(
                    "auth/forgot_password.html",
                    step="reset",
                    error=str(exc),
                    email=pending["email"],
                ), 400

            log_audit("password_reset_success", f"Password reset completed for {pending['email']}.", int(pending["user_id"]))
            session.clear()
            return render_template("auth/login.html", status="Password reset complete. Please log in with your new password.", email=pending["email"])

        return redirect(url_for("forgot_password"))





    @app.post("/logout")
    def logout():
        user_id = session.get("user_id")
        session_token = session.get("session_token")
        user = current_user()
        if user_id and session_token:
            delete_user_session(app.config["DATABASE"], int(user_id), str(session_token))
        if user:
            log_audit("logout", "User logged out.", int(user["id"]))
        session.clear()
        return redirect(url_for("login"))

    @app.get("/admin")
    @admin_required
    def admin_dashboard():
        return render_admin()

    # Debug route to inspect current session and computed user (temporary)
    @app.get("/__whoami")
    def debug_whoami():
        u = current_user()
        resp = {
            "session_keys": list(session.keys()),
            "session_user_id": session.get("user_id"),
            "user": u,
        }
        return jsonify(resp)

    def normalize_admin_role(role: str) -> str:
        role_value = role.strip().lower()
        if role_value in ("user", "free"):
            return "FREE"
        if role_value == "premium":
            return "PREMIUM"
        if role_value == "admin":
            return "ADMIN"
        return "FREE"

    @app.post("/admin/users")
    @admin_required
    def admin_create_user():
        first_name = request.form.get("first_name", "")
        last_name = request.form.get("last_name", "")
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        role = normalize_admin_role(request.form.get("role", "user"))

        try:
            user_id = create_user_with_role(
                app.config["DATABASE"],
                first_name,
                last_name,
                email,
                password,
                role,
                request.form.get("premium_valid_from", ""),
                request.form.get("premium_valid_until", ""),
            )
        except AuthError as exc:
            return render_admin(error=str(exc), status_code=400)

        log_audit("admin_create_user", f"Created user id {user_id} ({email}) with role {role}.")
        return render_admin(success="User added successfully")

    @app.post("/admin/users/<int:user_id>")
    @admin_required
    def admin_update_user(user_id: int):
        active_user = current_user()
        role = normalize_admin_role(request.form.get("role", "user"))

        if int(active_user["id"]) == user_id and role != "ADMIN":
            log_audit("admin_role_change_blocked", "Admin attempted to remove own admin role.")
            return render_admin(error="You cannot remove your own admin role.", status_code=400)

        if role != "ADMIN" and admin_stats(app.config["DATABASE"])["admins"] <= 1:
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
                request.form.get("status", "ACTIVE"),
                request.form.get("password", ""),
                request.form.get("premium_valid_from", ""),
                request.form.get("premium_valid_until", ""),
                request.form.get("clear_premium_validity") == "on",
            )
        except AuthError as exc:
            return render_admin(error=str(exc), status_code=400)

        log_audit("admin_update_user", f"Updated user id {user_id}.")
        return render_admin(success="User updated successfully")

    @app.post("/admin/settings")
    @admin_required
    def admin_update_settings():
        guest_limit = request.form.get("guest_weekly_limit", "5").strip() or "0"
        free_limit = request.form.get("free_weekly_limit", "10").strip() or "0"
        premium_limit = request.form.get("premium_weekly_limit", "0").strip() or "0"
        reset_quota = request.form.get("reset_quota") == "on"

        try:
            int(guest_limit)
            int(free_limit)
            int(premium_limit)
        except ValueError:
            return render_admin(error="Weekly limits must be integers." , status_code=400)

        set_setting(app.config["DATABASE"], "guest_weekly_limit", guest_limit)
        set_setting(app.config["DATABASE"], "free_weekly_limit", free_limit)
        set_setting(app.config["DATABASE"], "premium_weekly_limit", premium_limit)

        if reset_quota:
            reset_all_weekly_usage(app.config["DATABASE"])
            success = "Weekly quotas updated and reset."
        else:
            success = "Weekly quotas updated."

        log_audit("admin_update_settings", f"Updated weekly quota settings.")
        return render_admin(success=success)

    @app.post("/admin/users/<int:user_id>/delete")
    @admin_required
    def admin_delete_user(user_id: int):
        active_user = current_user()
        if int(active_user["id"]) == user_id:
            log_audit("admin_delete_blocked", "Admin attempted to delete own account.")
            return render_admin(error="You cannot delete your own administrator account.", status_code=400)

        account = get_user(app.config["DATABASE"], user_id)
        if account is None:
            return render_admin(error="User not found.", status_code=404)

        if account["is_admin"] and admin_stats(app.config["DATABASE"])["admins"] <= 1:
            return render_admin(error="At least one active administrator account must remain.", status_code=400)

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
        role = normalize_admin_role(request.form.get("role", "user"))
        if int(current_user()["id"]) == user_id and role != "ADMIN":
            log_audit("admin_role_change_blocked", "Admin attempted to remove own admin role.")
            return redirect(url_for("admin_dashboard"))

        if role != "ADMIN" and admin_stats(app.config["DATABASE"])["admins"] <= 1:
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
    def unlock():
        uploaded_file = request.files.get("pdf")
        password = request.form.get("password", "")

        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a PDF file first.", 400)

        filename = secure_filename(uploaded_file.filename)
        if not filename.lower().endswith(".pdf"):
            return error_response("Only PDF files are supported.", 400)

        work_dir = Path(tempfile.mkdtemp(prefix="swiftpropdf-"))
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
        track_tool_usage("unlock")

        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response

        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/lock")
    def lock():
        uploaded_file = request.files.get("pdf")
        password = request.form.get("password", "")

        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a PDF file first.", 400)

        if not password:
            return error_response("Enter a password to lock the PDF.", 400)

        filename = secure_filename(uploaded_file.filename)
        if not filename.lower().endswith(".pdf"):
            return error_response("Only PDF files are supported.", 400)

        work_dir = Path(tempfile.mkdtemp(prefix="swiftpropdf-lock-"))
        input_path = work_dir / f"{uuid4()}-{filename}"
        output_name = f"{Path(filename).stem}-locked.pdf"
        output_path = work_dir / output_name
        uploaded_file.save(input_path)

        try:
            lock_pdf(input_path, output_path, password=password, overwrite=True)
            log_audit("tool_lock", f"Locked {filename}.")
            track_tool_usage("lock")
        except PdfLockError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)

        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response

        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/split")
    def split():
        uploaded_file = request.files.get("pdf")
        page_ranges = request.form.get("page_ranges", "")

        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a PDF file first.", 400)

        filename = secure_filename(uploaded_file.filename)
        if not filename.lower().endswith(".pdf"):
            return error_response("Only PDF files are supported.", 400)

        work_dir = Path(tempfile.mkdtemp(prefix="swiftpropdf-splitter-"))
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
        track_tool_usage("split")

        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response

        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/merge")
    def merge():
        uploaded_files = request.files.getlist("pdfs")
        
        if not uploaded_files or all(f.filename == "" for f in uploaded_files):
            return error_response("Choose at least one PDF file.", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpropdf-merger-"))
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
            track_tool_usage("merge")
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
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpropdf-compress-"))
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
        track_tool_usage("compress")
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response

        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/compress-image")
    def compress_image_route():
        uploaded_file = request.files.get("image")
        level = request.form.get("level", "medium")

        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose an image file first.", 400)

        filename = secure_filename(uploaded_file.filename)
        suffix = Path(filename).suffix.lower()
        if suffix not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"):
            return error_response("Only JPG, PNG, WEBP, GIF, and BMP image files are supported.", 400)

        if level not in ("low", "medium", "high"):
            return error_response("Invalid compression level.", 400)

        work_dir = Path(tempfile.mkdtemp(prefix="swiftpropdf-image-compress-"))
        input_path = work_dir / f"{uuid4()}-{filename}"
        output_name = f"{Path(filename).stem}-compressed{suffix}"
        output_path = work_dir / output_name
        uploaded_file.save(input_path)

        try:
            compress_image(input_path, output_path, level=level, overwrite=True)
        except ImageConversionError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)

        log_audit("tool_compress_image", f"Compressed {filename} at {level} level.")
        track_tool_usage("compress-image")

        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response

        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/pdf-to-images")
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
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpropdf-pdf2img-"))
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
            track_tool_usage("pdf-to-images")
        except ImageConversionError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)
        
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(zip_path, as_attachment=True, download_name=output_name)

    @app.post("/images-to-pdf")
    def images_to_pdf_route():
        uploaded_files = request.files.getlist("images")
        
        if not uploaded_files or all(f.filename == "" for f in uploaded_files):
            return error_response("Choose at least one image file.", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpropdf-img2pdf-"))
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
            track_tool_usage("images-to-pdf")
        except ImageConversionError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)
        
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/pdf-to-word")
    def pdf_to_word_route():
        uploaded_file = request.files.get("pdf")
        
        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a PDF file first.", 400)
        
        filename = secure_filename(uploaded_file.filename)
        if not filename.lower().endswith(".pdf"):
            return error_response("Only PDF files are supported.", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpropdf-pdf2word-"))
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
        track_tool_usage("pdf-to-word")
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/pdf-to-powerpoint")
    def pdf_to_powerpoint_route():
        uploaded_file = request.files.get("pdf")
        
        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a PDF file first.", 400)
        
        filename = secure_filename(uploaded_file.filename)
        if not filename.lower().endswith(".pdf"):
            return error_response("Only PDF files are supported.", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpropdf-pdf2ppt-"))
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
        track_tool_usage("pdf-to-powerpoint")
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/pdf-to-excel")
    def pdf_to_excel_route():
        uploaded_file = request.files.get("pdf")
        
        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a PDF file first.", 400)
        
        filename = secure_filename(uploaded_file.filename)
        if not filename.lower().endswith(".pdf"):
            return error_response("Only PDF files are supported.", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpropdf-pdf2excel-"))
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
        track_tool_usage("pdf-to-excel")
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/office-to-pdf")
    def office_to_pdf_route():
        uploaded_file = request.files.get("document")
        
        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a document file first.", 400)
        
        filename = secure_filename(uploaded_file.filename)
        extension = filename.lower().split(".")[-1]
        if extension not in ("docx", "doc", "xlsx", "xls", "pptx", "ppt"):
            return error_response("Supported formats: DOCX, DOC, XLSX, XLS, PPTX, PPT", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpropdf-office2pdf-"))
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
        track_tool_usage("office-to-pdf")
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/qr-code")
    def qr_code_route():
        url_value = request.form.get("url", "").strip()
        if not url_value:
            return error_response("Enter a website URL to generate a QR code.", 400)

        normalized_url = url_value
        parsed_url = urlparse(normalized_url)
        if not parsed_url.scheme:
            normalized_url = f"https://{normalized_url}"
            parsed_url = urlparse(normalized_url)

        if not parsed_url.netloc:
            return error_response("Enter a valid website URL.", 400)

        work_dir = Path(tempfile.mkdtemp(prefix="swiftpropdf-qr-"))
        output_name = "qr-code.png"
        output_path = work_dir / output_name

        try:
            generate_qr_code(normalized_url, output_path, overwrite=True)
        except QrCodeError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return error_response(str(exc), 400)

        log_audit("tool_qr_code", f"Generated QR code for {normalized_url}.")
        track_tool_usage("qr-code")

        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response

        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/rotate-pdf")
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
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpropdf-rotate-"))
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
        track_tool_usage("rotate-pdf")
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(output_path, as_attachment=True, download_name=output_name)

    @app.post("/delete-pdf-pages")
    def delete_pdf_pages_route():
        uploaded_file = request.files.get("pdf")
        page_ranges = request.form.get("page_ranges", "")
        
        if uploaded_file is None or uploaded_file.filename == "":
            return error_response("Choose a PDF file first.", 400)
        
        filename = secure_filename(uploaded_file.filename)
        if not filename.lower().endswith(".pdf"):
            return error_response("Only PDF files are supported.", 400)
        
        work_dir = Path(tempfile.mkdtemp(prefix="swiftpropdf-delete-"))
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
        track_tool_usage("delete-pdf-pages")
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
            return response
        
        return send_file(output_path, as_attachment=True, download_name=output_name)

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swiftpropdf-ui",
        description="Start the local SwiftProPDF web interface.",
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
