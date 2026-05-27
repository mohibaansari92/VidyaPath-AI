# auth.py -- authentication blueprint with email-sending for OTP
import os
import datetime
import random
from dotenv import load_dotenv
from flask import Blueprint, request, jsonify, session, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, BigInteger, String, DateTime, Boolean, text, select, update

load_dotenv()

DB_USER = os.getenv("MYSQL_USER", "vidya_user")
DB_PASS = os.getenv("MYSQL_PASSWORD", "StrongPass123!")
DB_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
DB_NAME = os.getenv("MYSQL_DB", "vidyapath")
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}?charset=utf8mb4"

# Email config
SMTP_PROVIDER = os.getenv("SMTP_PROVIDER", "smtp").lower()  # 'smtp' or 'sendgrid'
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT") or 587)
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER or "no-reply@yourdomain.com")

# Try to import SendGrid client if available (used only if provider=sendgrid)
_sendgrid_available = False
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
    _sendgrid_available = True
except Exception:
    _sendgrid_available = False

# standard library for SMTP
import smtplib
from email.message import EmailMessage

# SQLAlchemy engine
engine = create_engine(DATABASE_URL, echo=False, future=True)
metadata = MetaData()

# Define users table (schema must match DB)
users = Table(
    "users", metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("full_name", String(255), nullable=False),
    Column("email", String(255), nullable=False, unique=True),
    Column("password_hash", String(255)),
    Column("is_verified", Boolean, nullable=False, server_default=text("0")),
    Column("otp_code", String(10)),
    Column("otp_expires", DateTime),
    Column("created_at", DateTime, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", DateTime, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")),
)

bp = Blueprint('auth', __name__)

def _gen_otp():
    return f"{random.randint(100000, 999999)}"

def otp_email_html(full_name, otp):
    return f"""<html>
  <body style="font-family: Arial, sans-serif; color: #111;">
    <p>Hi {full_name},</p>
    <p>Your verification code for <strong>VidyaPath</strong> is:</p>
    <h2 style="letter-spacing:3px;">{otp}</h2>
    <p>This code will expire in 10 minutes.</p>
    <p>If you didn't request this, you can safely ignore this email.</p>
    <br/>
    <p>— VidyaPath team</p>
  </body>
</html>"""

def send_email_smtp(to_email: str, subject: str, body_html: str, body_text: str = None):
    if not SMTP_SERVER:
        raise RuntimeError("SMTP_SERVER not configured in .env")
    msg = EmailMessage()
    msg["From"] = EMAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    text = body_text or "Please view this email in an HTML-capable email client."
    msg.set_content(text)
    msg.add_alternative(body_html, subtype="html")

    current_app.logger.info(f"Connecting to SMTP {SMTP_SERVER}:{SMTP_PORT} as {SMTP_USER or 'anonymous'}")
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as s:
        s.ehlo()
        if SMTP_PORT == 587:
            s.starttls()
            s.ehlo()
        if SMTP_USER and SMTP_PASSWORD:
            s.login(SMTP_USER, SMTP_PASSWORD)
        s.send_message(msg)
    current_app.logger.info("SMTP send_message completed")

def send_email_sendgrid(to_email: str, subject: str, body_html: str, body_text: str = None):
    if not _sendgrid_available:
        raise RuntimeError("sendgrid package is not installed. Run: pip install sendgrid")
    if not SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY not configured in .env")
    message = Mail(
        from_email=EMAIL_FROM,
        to_emails=to_email,
        subject=subject,
        html_content=body_html,
        plain_text_content=body_text or "Please view this email in an HTML capable client."
    )
    sg = SendGridAPIClient(SENDGRID_API_KEY)
    resp = sg.send(message)
    current_app.logger.info(f"SendGrid response: {resp.status_code}")
    return resp.status_code, resp.body, resp.headers

@bp.route("/send-otp", methods=["POST"])
def send_otp():
    try:
        data = request.get_json() or {}
        full_name = data.get("fullName") or data.get("full_name")
        email = data.get("email")
        password = data.get("password")

        if not (full_name and email and password):
            return jsonify({"success": False, "error": "Missing fields"}), 400

        otp = _gen_otp()
        expires = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
        pwd_hash = generate_password_hash(password)

        # DB write inside try/except so failures become JSON responses
        try:
            with engine.begin() as conn:
                sel = select(users).where(users.c.email == email)
                r = conn.execute(sel).first()
                if r:
                    stmt = update(users).where(users.c.email == email).values(
                        otp_code=otp, otp_expires=expires, full_name=full_name, password_hash=pwd_hash
                    )
                    conn.execute(stmt)
                else:
                    ins = users.insert().values(
                        full_name=full_name,
                        email=email,
                        password_hash=pwd_hash,
                        otp_code=otp,
                        otp_expires=expires,
                        is_verified=False
                    )
                    conn.execute(ins)
        except Exception as db_e:
            current_app.logger.exception("DB write failed in send_otp")
            return jsonify({"success": False, "error": "Database error", "exception": str(db_e)}), 500

        # Prepare and send email (existing handling)
        subject = "Your VidyaPath verification code"
        html = otp_email_html(full_name, otp)
        try:
            if SMTP_PROVIDER == "sendgrid":
                send_email_sendgrid(email, subject, html)
            else:
                send_email_smtp(email, subject, html)
        except Exception as e:
            current_app.logger.exception("Failed to send OTP email")
            return jsonify({"success": False, "error": "Failed to send OTP email", "exception": str(e)}), 500

        current_app.logger.info(f"OTP generated and emailed to {email} (not returned to client).")
        return jsonify({"success": True, "message": "OTP sent (check your email)"}), 200

    except Exception as e:
        # Catch any other unexpected errors, always return JSON for easier debugging
        current_app.logger.exception("send_otp top-level exception")
        return jsonify({"success": False, "error": "Internal server error in send_otp", "exception": str(e)}), 500


@bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json() or {}
    email = data.get("email")
    otp = data.get("otp")

    if not (email and otp):
        return jsonify({"success": False, "error": "Missing fields"}), 400

    with engine.begin() as conn:
        sel = select(users).where(users.c.email == email)
        r = conn.execute(sel).first()
        if not r:
            return jsonify({"success": False, "error": "Email not found"}), 404
        otp_expires = r._mapping.get("otp_expires")
        if otp_expires is None or datetime.datetime.utcnow() > otp_expires:
            return jsonify({"success": False, "error": "OTP expired"}), 400
        if str(r._mapping.get("otp_code")) != str(otp):
            return jsonify({"success": False, "error": "Invalid OTP"}), 400
        stmt = update(users).where(users.c.email == email).values(
            is_verified=True, otp_code=None, otp_expires=None
        )
        conn.execute(stmt)

    return jsonify({"success": True, "verified": True, "message": "Email verified"}), 200

# DIAGNOSTIC login route - paste in place of your current /login handler for debugging
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@bp.route("/login", methods=["POST"])
def login():
    # Very defensive / verbose diagnostic wrapper to find the failing step
    try:
        # Parse incoming JSON OR form-data robustly
        try:
            raw = request.get_data(as_text=True)
            data = request.get_json(silent=True) or request.form.to_dict() or {}
        except Exception:
            raw = None
            data = request.form.to_dict() or {}

        logger.info("LOGIN DEBUG: incoming payload keys: %s", list(data.keys()))
        # Support either source for email/password
        email = data.get("email") or request.form.get("email")
        password = data.get("password") or request.form.get("password")

        if not email or not password:
            return jsonify({
                "success": False,
                "stage": "validate_input",
                "error": "Missing email or password",
                "email": bool(email),
                "password": bool(password)
            }), 400

        # quick DB connection test before running real query
        try:
            with engine.connect() as conn:
                row = conn.execute(text("SELECT 1")).fetchone()
            logger.info("DB connectivity test passed: %s", row)
        except Exception as dbconn_err:
            logger.exception("DB connectivity test failed")
            return jsonify({"success": False, "stage": "db_connect", "error": str(dbconn_err)}), 500

        # Now fetch the user row
        try:
            with engine.begin() as conn:
                sel = select(users).where(users.c.email == email)
                r = conn.execute(sel).first()
        except Exception as sel_err:
            logger.exception("DB SELECT failed")
            return jsonify({"success": False, "stage": "db_select", "error": str(sel_err)}), 500

        if not r:
            logger.info("No user row found for email: %s", email)
            return jsonify({"success": False, "stage": "no_user", "error": "Invalid credentials"}), 401

        # try to inspect mapping safely
        try:
            user_map = r._mapping if hasattr(r, "_mapping") else dict(r)
        except Exception as map_err:
            logger.exception("Failed to build user mapping")
            try:
                rrepr = repr(r)
            except Exception:
                rrepr = "<could not repr r>"
            return jsonify({"success": False, "stage": "mapping", "error": str(map_err), "row_repr": rrepr}), 500

        logger.info("User DB row keys: %s", list(user_map.keys()))
        # Log minimal non-sensitive values for debugging
        try:
            logger.info("User sample: id=%s, email=%s, full_name=%s, is_verified=%s",
                        user_map.get("id"), user_map.get("email"), user_map.get("full_name"), user_map.get("is_verified"))
        except Exception:
            pass

        # verification check
        try:
            if not user_map.get("is_verified"):
                return jsonify({"success": False, "stage": "not_verified", "error": "Email not verified"}), 403
        except Exception as e:
            logger.exception("is_verified check failed")
            return jsonify({"success": False, "stage": "is_verified_check", "error": str(e)}), 500

        # password check
        try:
            pwd_hash = user_map.get("password_hash")
            if not pwd_hash or not check_password_hash(pwd_hash, password):
                return jsonify({"success": False, "stage": "password_check", "error": "Invalid credentials"}), 401
        except Exception as pw_err:
            logger.exception("Password hash check failed")
            return jsonify({
                "success": False,
                "stage": "password_exception",
                "error": str(pw_err),
                "pwd_hash_type": type(pwd_hash).__name__ if 'pwd_hash' in locals() else "Unknown"
            }), 500

        # Everything ok — set session values safely
        try:
            from datetime import datetime

            session['user_id'] = user_map.get("id")
            session['email'] = user_map.get("email")

            # Prefer full_name from DB, else fallback to email prefix
            full_name_val = user_map.get("full_name") or (user_map.get("email") or "").split("@")[0]

            # store under both keys, so old code using 'name' still works
            session['full_name'] = full_name_val
            session['name'] = full_name_val

            # store login timestamp for dashboard
            session['login_time'] = datetime.now().strftime("%b %d, %Y %H:%M")

        except Exception as sess_err:
            logger.exception("Session write failed")
            return jsonify({"success": False, "stage": "session", "error": str(sess_err)}), 500

        logger.info("LOGIN SUCCESS for %s", email)
        return jsonify({"success": True, "message": "Logged in (diagnostic)"}), 200

    except Exception as final_e:
        logger.exception("Unexpected error in diagnostic login")
        return jsonify({"success": False, "stage": "unexpected", "error": str(final_e)}), 500




@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out"}), 200
