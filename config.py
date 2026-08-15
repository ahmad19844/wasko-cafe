import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _fix_db_url(url: str) -> str:
    # Render (and some providers) hand out "postgres://" but SQLAlchemy
    # needs "postgresql://" — patch it automatically.
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    _default_sqlite = "sqlite:///" + os.path.join(BASE_DIR, "app.db")
    SQLALCHEMY_DATABASE_URI = _fix_db_url(
        os.environ.get("DATABASE_URL", _default_sqlite)
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Passport photos are meant to be publicly viewable (they show on the
    # welcome page), so they live inside static/. Course materials and
    # assignment submissions are NOT meant to be public — they live outside
    # static/ and are only ever served through access-controlled routes in
    # app.py (download_material / admin_download_submission etc.), which
    # check enrollment/payment status before handing back a file.
    PASSPORT_FOLDER = os.path.join(BASE_DIR, "static", "uploads", "passports")
    PROTECTED_UPLOAD_FOLDER = os.path.join(BASE_DIR, "protected_uploads")
    MATERIAL_FOLDER = os.path.join(PROTECTED_UPLOAD_FOLDER, "materials")
    SUBMISSION_FOLDER = os.path.join(PROTECTED_UPLOAD_FOLDER, "submissions")
    MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15 MB per upload

    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@1984")

    # Course payment (fixed per the academy's instructions)
    COURSE_FEE = 10000
    ASSIGNMENT_LATE_FEE = 1000
    BANK_NAME = "FIRST BANK"
    BANK_ACCOUNT_NUMBER = "3032996242"
    BANK_ACCOUNT_NAME = "MUHAMMAD AHMAD"
    LATE_FEE_EVIDENCE_EMAIL = "amy33375@gmail.com"

    ASSIGNMENT_WINDOW_HOURS = 48

    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "no-reply@waskoacademy.com")
