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
from SwiftPDF.core import (
    PdfSplitError, PdfUnlockError, split_pdf, unlock_pdf,
    PdfMergeError, merge_pdfs,
    PdfCompressError, compress_pdf,
    ImageConversionError, pdf_to_images, images_to_pdf,
    PdfConversionError, pdf_to_word, pdf_to_powerpoint, pdf_to_excel,
    OfficeConversionError, office_to_pdf,
    PdfEditError, rotate_pdf_pages, delete_pdf_pages,
)


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
