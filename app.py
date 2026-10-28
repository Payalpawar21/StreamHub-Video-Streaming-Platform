import os
import uuid
import subprocess
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    send_from_directory,
    abort,
)
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


# --------------------------------------------------
# 1. Application Configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)

app.config["ADMIN_EMAIL"] = os.getenv("ADMIN_EMAIL", "").strip().lower()
app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "development-key-change-before-deployment",
)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "sqlite:///videos.db",
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

UPLOAD_FOLDER = BASE_DIR / "uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

ALLOWED_EXTENSIONS = {"mp4", "webm", "ogg", "mov"}

LOCAL_APP_DATA = os.getenv("LOCALAPPDATA", "")
FFMPEG_PATH = (
    Path(LOCAL_APP_DATA)
    / "Microsoft"
    / "WinGet"
    / "Packages"
    / "Gyan.FFmpeg.Shared_Microsoft.Winget.Source_8wekyb3d8bbwe"
    / "ffmpeg-9.0.2-full_build-shared"
    / "bin"
    / "ffmpeg.exe"
)

THUMBNAIL_FOLDER = BASE_DIR / "static" / "thumbnails"
THUMBNAIL_FOLDER.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# 2. Initialize Extensions
# --------------------------------------------------

db = SQLAlchemy(app)
csrf = CSRFProtect(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "info"


# --------------------------------------------------
# 3. Database Models
# --------------------------------------------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    videos = db.relationship(
        "Video",
        backref="owner",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, default="")
    filename = db.Column(db.String(255), nullable=False)
    storage_type = db.Column(db.String(20), default="local", nullable=False)
    s3_key = db.Column(db.String(500), nullable=True)
    thumbnail = db.Column(db.String(255), nullable=True)
    created_at = db.Column(
        db.DateTime,
        server_default=db.func.current_timestamp(),
        nullable=False,
    )
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


# --------------------------------------------------
# 4. Helper Functions and Login Manager
# --------------------------------------------------

def allowed_video(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def valid_video_signature(file):
    """Check common video container signatures before saving."""
    header = file.stream.read(16)
    file.stream.seek(0)

    is_mp4_or_mov = len(header) >= 12 and header[4:8] == b"ftyp"
    is_webm = header.startswith(b"\x1a\x45\xdf\xa3")
    is_ogg = header.startswith(b"OggS")
    return is_mp4_or_mov or is_webm or is_ogg


def generate_thumbnail(video_path, thumbnail_name):
    """Generate a JPEG thumbnail using FFmpeg."""
    thumbnail_path = THUMBNAIL_FOLDER / thumbnail_name

    if not FFMPEG_PATH.is_file():
        app.logger.warning("FFmpeg executable was not found at %s", FFMPEG_PATH)
        return None

    try:
        command = [
            str(FFMPEG_PATH),
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-ss", "1",
            "-i", str(video_path),
            "-frames:v", "1",
            "-vf", "scale=640:-1",
            "-q:v", "3",
            str(thumbnail_path),
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        if result.returncode == 0 and thumbnail_path.is_file():
            return thumbnail_name

        app.logger.warning(
            "Thumbnail generation failed: %s",
            result.stderr[-2000:],
        )
    except (OSError, subprocess.TimeoutExpired):
        app.logger.exception("FFmpeg thumbnail generation failed")

    thumbnail_path.unlink(missing_ok=True)
    return None


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (ValueError, TypeError):
        return None


def is_admin_user(user):
    admin_email = app.config.get("ADMIN_EMAIL", "").strip().lower()
    user_email = (getattr(user, "email", "") or "").strip().lower()
    return bool(admin_email and user_email and user_email == admin_email)


def admin_required(view_function):
    @wraps(view_function)
    @login_required
    def wrapped_view(*args, **kwargs):
        if not is_admin_user(current_user):
            abort(403)
        return view_function(*args, **kwargs)

    return wrapped_view


# --------------------------------------------------
# 5. Home Page - Search, Filter and Sort
# --------------------------------------------------

@app.route("/")
def index():
    search_query = request.args.get("q", "").strip()[:150]
    scope = request.args.get("scope", "all")
    sort = request.args.get("sort", "newest")

    query = Video.query

    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.filter(
            db.or_(
                Video.title.ilike(search_pattern),
                Video.description.ilike(search_pattern),
            )
        )

    if scope == "mine" and current_user.is_authenticated:
        query = query.filter_by(user_id=current_user.id)
    else:
        scope = "all"

    if sort == "oldest":
        query = query.order_by(Video.created_at.asc())
    else:
        sort = "newest"
        query = query.order_by(Video.created_at.desc())

    videos = query.all()

    return render_template(
        "index.html",
        videos=videos,
        search_query=search_query,
        scope=scope,
        sort=sort,
    )


# --------------------------------------------------
# 6. User Registration
# --------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(
            url_for("admin_dashboard") if is_admin_user(current_user)
            else url_for("dashboard")
        )

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("Please fill in all fields.", "error")
            return redirect(url_for("register"))

        if len(username) > 80 or len(email) > 120:
            flash("Username or email is too long.", "error")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
            return redirect(url_for("register"))

        existing_user = User.query.filter(
            db.or_(User.username == username, User.email == email)
        ).first()

        if existing_user:
            flash("Username or email already exists.", "error")
            return redirect(url_for("register"))

        user = User(username=username, email=email)
        user.set_password(password)

        try:
            db.session.add(user)
            db.session.commit()
            flash("Account created successfully. Please log in.", "success")
            return redirect(url_for("login"))
        except Exception:
            db.session.rollback()
            app.logger.exception("Registration failed")
            flash("Registration failed. Please try again.", "error")

    return render_template("register.html")


# --------------------------------------------------
# 7. User Login
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(
            url_for("admin_dashboard") if is_admin_user(current_user)
            else url_for("dashboard")
        )

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            flash("Welcome back!", "success")
            return redirect(
                url_for("admin_dashboard") if is_admin_user(user)
                else url_for("dashboard")
            )

        flash("Invalid email or password.", "error")

    return render_template("login.html")


# --------------------------------------------------
# 8. Admin Dashboard
# --------------------------------------------------

@app.route("/admin")
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    total_videos = Video.query.count()

    recent_videos = (
        Video.query.order_by(Video.created_at.desc()).limit(5).all()
    )
    users = User.query.order_by(User.id.desc()).all()

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        total_videos=total_videos,
        recent_videos=recent_videos,
        users=users,
    )


# --------------------------------------------------
# 9. User Dashboard
# --------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    videos = (
        Video.query.filter_by(user_id=current_user.id)
        .order_by(Video.created_at.desc())
        .all()
    )
    return render_template("dashboard.html", videos=videos)


# --------------------------------------------------
# 10. Upload Video
# --------------------------------------------------

@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload_video():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        file = request.files.get("video")

        if not title:
            flash("Please enter a video title.", "error")
            return redirect(url_for("upload_video"))

        if len(title) > 150:
            flash("Title must be 150 characters or fewer.", "error")
            return redirect(url_for("upload_video"))

        if len(description) > 5000:
            flash("Description must be 5000 characters or fewer.", "error")
            return redirect(url_for("upload_video"))

        if not file or not file.filename:
            flash("Please select a video file.", "error")
            return redirect(url_for("upload_video"))

        safe_name = secure_filename(file.filename)
        if not safe_name or not allowed_video(safe_name):
            flash("Unsupported file extension. Use MP4, WebM, OGG or MOV.", "error")
            return redirect(url_for("upload_video"))

        if not valid_video_signature(file):
            flash("The file does not appear to be a supported video.", "error")
            return redirect(url_for("upload_video"))

        extension = safe_name.rsplit(".", 1)[1].lower()
        stored_name = f"{uuid.uuid4().hex}.{extension}"
        destination = UPLOAD_FOLDER / stored_name

        try:
            file.save(destination)
            thumbnail_name = generate_thumbnail(
                destination,
                f"{Path(stored_name).stem}.jpg",
            )

            video = Video(
                title=title,
                description=description,
                filename=stored_name,
                storage_type="local",
                thumbnail=thumbnail_name,
                user_id=current_user.id,
            )
            db.session.add(video)
            db.session.commit()

            flash("Video uploaded successfully!", "success")
            return redirect(url_for("dashboard"))
        except Exception:
            db.session.rollback()
            destination.unlink(missing_ok=True)
            app.logger.exception("Video upload failed")
            flash("Upload failed. Please try again.", "error")
            return redirect(url_for("upload_video"))

    return render_template("upload.html")


# --------------------------------------------------
# 11. Watch Video Page
# --------------------------------------------------

@app.route("/videos/<int:video_id>/watch")
@login_required
def watch_video(video_id):
    video = db.session.get(Video, video_id)
    if video is None:
        abort(404)

    # Owners and admins can watch this video.
    if video.user_id != current_user.id and not is_admin_user(current_user):
        abort(403)

    if video.storage_type != "local":
        abort(404)

    video_path = UPLOAD_FOLDER / video.filename
    if not video_path.is_file():
        abort(404)

    return render_template("watch.html", video=video)


# --------------------------------------------------
# 12. Edit Video
# --------------------------------------------------

@app.route("/videos/<int:video_id>/edit", methods=["GET", "POST"])
@login_required
def edit_video(video_id):
    video = db.session.get(Video, video_id)
    if video is None:
        abort(404)

    if video.user_id != current_user.id and not is_admin_user(current_user):
        abort(403)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()

        if not title:
            flash("Video title is required.", "error")
        elif len(title) > 150:
            flash("Title must be 150 characters or fewer.", "error")
        elif len(description) > 5000:
            flash("Description must be 5000 characters or fewer.", "error")
        else:
            try:
                video.title = title
                video.description = description
                db.session.commit()
                flash("Video updated successfully!", "success")
                return redirect(
                    url_for("admin_dashboard") if is_admin_user(current_user)
                    else url_for("dashboard")
                )
            except Exception:
                db.session.rollback()
                app.logger.exception("Video update failed")
                flash("Could not update the video. Please try again.", "error")

    return render_template("edit_video.html", video=video)


# --------------------------------------------------
# 13. Delete Video
# --------------------------------------------------

@app.route("/videos/<int:video_id>/delete", methods=["POST"])
@login_required
def delete_video(video_id):
    video = db.session.get(Video, video_id)
    if video is None:
        abort(404)

    if video.user_id != current_user.id and not is_admin_user(current_user):
        abort(403)

    if video.storage_type != "local":
        flash("This storage type cannot be deleted by this version.", "error")
        return redirect(
            url_for("admin_dashboard") if is_admin_user(current_user)
            else url_for("dashboard")
        )

    video_path = UPLOAD_FOLDER / video.filename
    thumbnail_path = (
        THUMBNAIL_FOLDER / video.thumbnail if video.thumbnail else None
    )

    try:
        db.session.delete(video)
        db.session.commit()

        video_path.unlink(missing_ok=True)
        if thumbnail_path:
            thumbnail_path.unlink(missing_ok=True)

        flash("Video deleted successfully.", "success")
    except Exception:
        db.session.rollback()
        app.logger.exception("Video deletion failed")
        flash("Could not delete the video. Please try again.", "error")

    return redirect(
        url_for("admin_dashboard") if is_admin_user(current_user)
        else url_for("dashboard")
    )


# --------------------------------------------------
# 14. Stream Video
# --------------------------------------------------

@app.route("/videos/<int:video_id>/stream")
@login_required
def stream_video(video_id):
    video = db.session.get(Video, video_id)
    if video is None:
        abort(404)

    if video.user_id != current_user.id and not is_admin_user(current_user):
        abort(403)

    if video.storage_type != "local":
        abort(404)

    video_path = UPLOAD_FOLDER / video.filename
    if not video_path.is_file():
        abort(404)

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        video.filename,
        conditional=True,
    )


# --------------------------------------------------
# 15. Logout
# --------------------------------------------------

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# --------------------------------------------------
# 16. Create Database Tables
# --------------------------------------------------

with app.app_context():
    db.create_all()


# --------------------------------------------------
# 17. Run Application
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
