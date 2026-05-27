import os
import json
import uuid
from flask import Flask, render_template, request, jsonify, session
from groq import Groq
from PyPDF2 import PdfReader
from docx import Document
from dotenv import load_dotenv
import docx 
import pdfplumber
from flask import render_template
import os, json, csv
from datetime import datetime
from flask import session, render_template



BASE_DIR = os.path.dirname(__file__)
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DATA_FILES_FOLDER = BASE_DIR  # project root (adjust if different)

QUIZ_RESULTS_PATHS = [
    os.path.join(DATA_FILES_FOLDER, "quiz_results.json"),
    os.path.join(DATA_FILES_FOLDER, "quiz_results.csv"),
    os.path.join(DATA_FILES_FOLDER, "quiz_results.txt"),
    os.path.join(UPLOAD_FOLDER, "quiz_results.json"),
    os.path.join(UPLOAD_FOLDER, "quiz_results.csv"),
    os.path.join(UPLOAD_FOLDER, "quiz_results.txt"),
]

# ---------------- Helper utilities for dashboard ----------------
def get_uploads_for_user(user_id=None, limit=50):
    items = []
    if not os.path.isdir(UPLOAD_FOLDER):
        return items
    # show newest first
    all_files = sorted(os.listdir(UPLOAD_FOLDER), key=lambda f: os.path.getmtime(os.path.join(UPLOAD_FOLDER,f)), reverse=True)
    for fname in all_files:
        fpath = os.path.join(UPLOAD_FOLDER, fname)
        if not os.path.isfile(fpath):
            continue
        stat = os.stat(fpath)
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%b %d, %Y %H:%M")
        size_kb = stat.st_size // 1024
        _, ext = os.path.splitext(fname.lower())
        ftype = ext.replace(".", "") or "file"
        items.append({
            "title": fname,
            "filename": fname,
            "path": fpath,
            "date": mtime,
            "size_kb": size_kb,
            "type": ftype,
            "score": None,
            "kind": "upload"
        })
        if len(items) >= limit:
            break
    return items


def parse_quiz_results_from_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    results = []
    if isinstance(data, dict):
        # flatten possible lists inside dict
        for v in data.values():
            if isinstance(v, list):
                results.extend(v)
    elif isinstance(data, list):
        results = data
    normalized = []
    for r in results:
        title = r.get("title") or r.get("quiz") or r.get("name") or "Quiz"
        score = r.get("score")
        date = r.get("date") or r.get("timestamp") or r.get("time")
        if isinstance(date, (int, float)):
            try:
                date = datetime.fromtimestamp(date).strftime("%b %d, %Y")
            except Exception:
                date = ""
        normalized.append({"title": title, "score": score, "date": date, "kind": "quiz"})
    return normalized


def parse_quiz_results_from_csv(path):
    out = []
    try:
        with open(path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                title = row.get("title") or row.get("quiz") or row.get("name") or row.get("quiz_name") or "Quiz"
                score = row.get("score") or row.get("marks")
                date = row.get("date") or row.get("timestamp")
                try:
                    score = int(score) if score and str(score).isdigit() else score
                except Exception:
                    pass
                out.append({"title": title, "score": score, "date": date, "kind": "quiz"})
    except Exception:
        pass
    return out


def parse_quiz_results_from_simple_txt(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if "|" in line:
                    parts = [p.strip() for p in line.split("|")]
                elif "," in line:
                    parts = [p.strip() for p in line.split(",")]
                else:
                    parts = [line]
                title = parts[0]
                score = None
                date = None
                if len(parts) >= 2:
                    score = parts[1]
                if len(parts) >= 3:
                    date = parts[2]
                try:
                    score = int(score) if score and str(score).isdigit() else score
                except Exception:
                    pass
                out.append({"title": title, "score": score, "date": date, "kind": "quiz"})
    except Exception:
        pass
    return out


def gather_quiz_results():
    all_results = []
    for p in QUIZ_RESULTS_PATHS:
        if not os.path.isfile(p):
            continue
        _, ext = os.path.splitext(p.lower())
        if ext == ".json":
            all_results.extend(parse_quiz_results_from_json(p))
        elif ext == ".csv":
            all_results.extend(parse_quiz_results_from_csv(p))
        else:
            all_results.extend(parse_quiz_results_from_simple_txt(p))
    # also scan uploads/ for quiz files
    if os.path.isdir(UPLOAD_FOLDER):
        for fname in os.listdir(UPLOAD_FOLDER):
            if "quiz" in fname.lower() and fname.lower().endswith((".json", ".csv", ".txt")):
                p = os.path.join(UPLOAD_FOLDER, fname)
                _, ext = os.path.splitext(fname.lower())
                if ext == ".json":
                    all_results.extend(parse_quiz_results_from_json(p))
                elif ext == ".csv":
                    all_results.extend(parse_quiz_results_from_csv(p))
                else:
                    all_results.extend(parse_quiz_results_from_simple_txt(p))

    # best-effort sort by date
    def parse_date_safe(d):
        if not d:
            return datetime.min
        if isinstance(d, datetime):
            return d
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%b %d, %Y", "%b %d %Y", "%d %b %Y", "%Y/%m/%d", "%b %d, %Y %H:%M"):
            try:
                return datetime.strptime(d, fmt)
            except Exception:
                continue
        try:
            return datetime.fromisoformat(str(d))
        except Exception:
            return datetime.min
    for r in all_results:
        if not r.get("date"):
            r["date"] = ""
    all_results = sorted(all_results, key=lambda x: parse_date_safe(x.get("date")), reverse=True)
    return all_results
# ---------------- end utilities ----------------

# Load environment variables
load_dotenv()

app = Flask(__name__)

# --- MySQL / SQLAlchemy setup (added) ---
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from urllib.parse import quote_plus
import pymysql

DB_USER = os.getenv("MYSQL_USER")
DB_PASS = os.getenv("MYSQL_PASSWORD")
DB_HOST = os.getenv("MYSQL_HOST", "127.0.0.1").strip()
DB_PORT = os.getenv("MYSQL_PORT", "3306")
DB_NAME = os.getenv("MYSQL_DB", "vidyapath")

if os.getenv("DATABASE_URL"):
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
else:
    db_pass_quoted = quote_plus(DB_PASS) if DB_PASS is not None else ""
    app.config["SQLALCHEMY_DATABASE_URI"] = f"mysql+pymysql://{DB_USER}:{db_pass_quoted}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# import models (separate file). If import fails (initial run), we set placeholders.
try:
    from models import Upload, QuizResult
except Exception:
    Upload = None
    QuizResult = None
# --- end SQLAlchemy setup ---

# add near the top where you define app
from flask_cors import CORS
import os

app.secret_key = os.getenv("FLASK_SECRET", "supersecretkey")

# Cookie settings — pick safe defaults for local dev; adjust for production
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    # For same-origin local dev use "Lax". If your frontend uses a different origin
    # and you test over HTTPS in production, use "None" + Secure=True
    SESSION_COOKIE_SAMESITE=os.getenv("SESSION_COOKIE_SAMESITE", "Lax"),
    SESSION_COOKIE_SECURE=(os.getenv("FLASK_ENV") == "production"),
)

# If your frontend runs on another port/origin, enable CORS for that origin and allow credentials.
# Replace the origins list with the exact origin(s) of your frontend (do NOT use '*' in production).
frontend_origins = os.getenv("CORS_ORIGINS", "*")
# Example: "http://localhost:3000" or a comma separated list
if frontend_origins == "*":
    CORS(app, supports_credentials=True, origins="*")
else:
    origins = [o.strip() for o in frontend_origins.split(",")]
    CORS(app, supports_credentials=True, origins=origins)


from functools import wraps
from flask import jsonify

def login_required_json(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            app.logger.info("login_required: blocked (no user_id in session)")
            return jsonify({"ok": False, "error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return wrapped

from auth import bp as auth_bp
app.register_blueprint(auth_bp)

# --- Authentication pages (serve signup/login templates) ---
@app.route("/signup.html")
def signup_page():
    return render_template("signup.html")

@app.route("/signup")
def signup_short():
    return render_template("signup.html")

@app.route("/login.html")
def login_page():
    return render_template("login.html")

@app.route("/login")
def login_short():
    return render_template("login.html")
def get_quizzes_for_user(user_id=None, limit=50):
    items = []
    try:
        if user_id is None:
            user_id = str(session.get("user_id") or session.get("username"))
        if QuizResult is not None:
            rows = QuizResult.query.filter_by(user_id=str(user_id)).order_by(QuizResult.created_at.desc()).limit(limit).all()
            for r in rows:
                items.append(r.to_dict())
    except Exception as e:
        current_app.logger.debug("DB quizzes lookup failed: %s", e)
    return items


@app.route("/dashboard")
def dashboard():
    # require login — adapt to your setup
    full_name = session.get("full_name", session.get("username", "User"))
    user_id = session.get("user_id")

    uploads = get_uploads_for_user(user_id=user_id, limit=200)
    quizzes = gather_quiz_results()

    merged = uploads + quizzes
    # Already have 'kind' set for each item
    # sort by date if possible (we used the utilities to add date)
    def parse_dt_safe(x):
        d = x.get("date")
        try:
            return datetime.fromisoformat(d) if isinstance(d, str) and "T" in d else datetime.strptime(d, "%b %d, %Y %H:%M")
        except Exception:
            try:
                return datetime.strptime(d, "%b %d, %Y")
            except Exception:
                return datetime.min
    try:
        merged_sorted = sorted(merged, key=lambda x: parse_dt_safe(x), reverse=True)
    except Exception:
        merged_sorted = merged

    totals = {
        "documents_uploaded": len([u for u in uploads if u]),
        "quizzes_taken": len(quizzes)
    }

    login_time = session.get("login_time", "")  # set at login
    return render_template("dashboard.html",
                           full_name=full_name,
                           recent=merged_sorted,
                           totals=totals,
                           login_time=login_time)

@app.route("/whoami")
def whoami():
    return jsonify({
        "has_session": bool(session),
        "user_id": session.get("user_id"),
        "full_name": session.get("full_name"),
        "email": session.get("email"),
        "login_time": session.get("login_time")
    })

@app.route("/code2.html")
def code2_html_route():
    return render_template("code2.html", show_upload_warning=False)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
DOC_CACHE = ""
TEMP_FILE = "last_upload.txt"  # to persist last uploaded doc

# ============ Helper ============
def read_file_content(path):
    ext = os.path.splitext(path)[1].lower()
    text = ""
    if ext == ".pdf":
        reader = PdfReader(path)
        text = "\n".join([p.extract_text() or "" for p in reader.pages])
    elif ext == ".docx":
        doc = Document(path)
        text = "\n".join([p.text for p in doc.paragraphs])
    elif ext == ".txt":
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    return text[:15000]

# ============ Routes ============
@app.route("/")
def index():
    return render_template("code2.html", show_upload_warning=False)

@app.route("/mindmap")
def mindmap():
    global DOC_CACHE
    if not DOC_CACHE and os.path.exists(TEMP_FILE):
        with open(TEMP_FILE, "r", encoding="utf-8") as tmp:
            DOC_CACHE = tmp.read()
    if not DOC_CACHE:
        return render_template("code2.html", show_upload_warning=True)
    return render_template("mindmap.html")

@app.route("/upload", methods=["POST"])
@login_required_json
def upload_file():
    global DOC_CACHE
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file provided"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"ok": False, "error": "No filename"}), 400

    # user identification (make sure session has user_id set at login)
    user_id = str(session.get("user_id") or session.get("username") or "anon")
    from werkzeug.utils import secure_filename
    import time

    orig_name = secure_filename(f.filename)
    ts = int(time.time())
    stored_name = f"{user_id}_{ts}_{orig_name}"
    save_dir = app.config.get("UPLOAD_FOLDER", UPLOAD_FOLDER)
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, stored_name)
    f.save(save_path)

    # try to update DOC_CACHE if readable
    try:
        DOC_CACHE = read_file_content(save_path)
        with open(TEMP_FILE, "w", encoding="utf-8") as tmp:
            tmp.write(DOC_CACHE)
    except Exception:
        pass

    # Save metadata to MySQL via SQLAlchemy if models exist
    try:
        if Upload is not None:
            size = os.path.getsize(save_path)
            up = Upload(
                user_id=user_id,
                stored_filename=stored_name,
                original_filename=orig_name,
                content_type=getattr(f, 'content_type', '') or '',
                size=size
            )
            db.session.add(up)
            db.session.commit()
    except Exception as e:
        current_app.logger.exception("Failed saving upload to DB: %s", e)
        try:
            db.session.rollback()
        except Exception:
            pass

    # Return both programmatic and friendly keys so frontend won't get `undefined`
    return jsonify({
        "ok": True,
        "stored": stored_name,
        "original": orig_name,
        "size": os.path.getsize(save_path),
        "name": stored_name,        # friendly key many frontends expect
        "message": "File uploaded"
    })

from flask import send_from_directory

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config.get("UPLOAD_FOLDER", UPLOAD_FOLDER), filename, as_attachment=False)


@app.route("/save_quiz_result", methods=["POST"])
@login_required_json
def save_quiz_result():
    user_id = str(session.get("user_id") or session.get("username") or "anon")
    try:
        app.logger.info("SAVE_QUIZ called — user_id=%s payload=%s", user_id, data)
        print("SAVE_QUIZ called — user_id=", user_id, " payload=", data)

        data = request.get_json(force=True)
    except Exception:
        return jsonify({"ok": False, "error": "Invalid JSON"}), 400

    title = data.get("title") or data.get("quiz") or "Quiz"
    try:
        score = float(data.get("score")) if data.get("score") is not None else None
    except Exception:
        score = None

    try:
        if QuizResult is not None:
            qr = QuizResult(user_id=user_id, title=title, score=score, raw_json=json.dumps(data, ensure_ascii=False))
            db.session.add(qr)
            db.session.commit()
    except Exception as e:
        current_app.logger.exception("Failed saving quiz to DB: %s", e)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"ok": False, "error": "DB error"}), 500

    return jsonify({"ok": True, "quiz_id": getattr(qr, 'id', None)})


# ============ New: Fetch file list ============
@app.route("/path_data")
def path_data():
    files = os.listdir(UPLOAD_FOLDER)
    files = [f for f in files if not f.startswith('.')]
    return jsonify({"files": files})

# ============ New: Select file ============
@app.route("/select_file", methods=["POST"])
def select_file():
    global DOC_CACHE
    filename = request.json.get("filename", "")
    if not filename:
        return jsonify({"ok": False, "error": "Missing filename"})

    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(file_path):
        return jsonify({"ok": False, "error": "File not found"})

    DOC_CACHE = read_file_content(file_path)
    with open(TEMP_FILE, "w", encoding="utf-8") as tmp:
        tmp.write(DOC_CACHE)

    return jsonify({"ok": True, "message": "File selected"})

# ============ Mindmap Generation ============
@app.route("/generate", methods=["POST"])
def generate_mindmap():
    global DOC_CACHE
    if not DOC_CACHE and os.path.exists(TEMP_FILE):
        with open(TEMP_FILE, "r", encoding="utf-8") as tmp:
            DOC_CACHE = tmp.read()

    topic = request.json.get("topic", "")
    if not DOC_CACHE:
        return jsonify({"ok": False, "error": "No document uploaded"})
    if topic == "__check__":
        return jsonify({"ok": True, "message": "File loaded"})
    if not topic:
        return jsonify({"ok": False, "error": "Missing topic"})

    prompt = f"""
You are a mindmap generator. 
From the given document text, build a clear hierarchical JSON mindmap for the topic "{topic}".
Return only JSON of this structure:
{{
 "root": {{"id":"root","label":"{topic}" }},
 "children": [
    {{"id":"n1","label":"Main Idea","children":[{{"id":"n1a","label":"Subtopic"}}]}}
 ]
}}
Text:
\"\"\"{DOC_CACHE[:7000]}\"\"\""""

    try:
        res = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",

            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        raw = res.choices[0].message.content.strip()
        start, end = raw.find("{"), raw.rfind("}") + 1
        data = json.loads(raw[start:end]) if start != -1 else {
            "root": {"id": "root", "label": topic},
            "children": [],
        }
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

    return jsonify({"ok": True, "mindmap": data})

@app.route("/expand", methods=["POST"])
def expand_node():
    global DOC_CACHE
    if not DOC_CACHE and os.path.exists(TEMP_FILE):
        with open(TEMP_FILE, "r", encoding="utf-8") as tmp:
            DOC_CACHE = tmp.read()

    node_label = request.json.get("label", "")
    if not node_label:
        return jsonify({"ok": False, "error": "Missing node label"})
    if not DOC_CACHE:
        return jsonify({"ok": False, "error": "No document uploaded"})

    prompt = f"""
From the document below, list 4–6 detailed subtopics directly related to "{node_label}".
Return only JSON array of strings, e.g. ["Subtopic A","Subtopic B"].
Text:
\"\"\"{DOC_CACHE[:7000]}\"\"\""""

    try:
        res = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        raw = res.choices[0].message.content.strip()
        start, end = raw.find("["), raw.rfind("]") + 1
        arr = json.loads(raw[start:end])
        children = [{"id": f"{node_label}_{i}", "label": lbl} for i, lbl in enumerate(arr)]
    except Exception:
        children = []

    return jsonify({"ok": True, "children": children})



#------------------- ADAPTIVE QUIZ FEATURE -------------------


UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
DOC_CACHE = ""
TEMP_FILE = "last_upload.txt"

# ---------- Helper ----------




# ---------- Adaptive Quiz ----------
# ---------- ADAPTIVE QUIZ FEATURE ----------
# ---------- ADAPTIVE QUIZ FEATURE (Final JSON-Stable Version) ----------
@app.route("/adaptive")
def adaptive_page():
    global DOC_CACHE

    # Load cached document
    if not DOC_CACHE and os.path.exists(TEMP_FILE):
        with open(TEMP_FILE, "r", encoding="utf-8") as tmp:
            DOC_CACHE = tmp.read()

    if not DOC_CACHE:
        return render_template("code2.html", show_upload_warning=True)

    return render_template("adaptive.html")

topic={}
print(f"📄 Loaded DOC_CACHE length: {len(DOC_CACHE)} | Topic: {topic}")
 


@app.route("/generate_adaptive_quiz_api", methods=["POST"])
def generate_adaptive_quiz_api():
    global DOC_CACHE
    data = request.get_json(force=True, silent=True) or {}
    topic = (data.get("topic") or "").strip()

    if not topic:
        return jsonify({"ok": False, "error": "Missing topic"})
    if not DOC_CACHE:
        if os.path.exists(TEMP_FILE):
            with open(TEMP_FILE, "r", encoding="utf-8") as tmp:
                DOC_CACHE = tmp.read()
    if not DOC_CACHE:
        return jsonify({"ok": False, "error": "No document uploaded"})
    if len(DOC_CACHE.strip()) < 100:
            return jsonify({"ok": False, "error": "Uploaded PDF has no readable text. Please upload a text-based PDF."})


    # ===== Prompt =====
    import re, json, uuid
    session_id = str(uuid.uuid4())[:8]  # unique random ID for variety

    #  STRONGER PROMPT
    prompt = f"""
You are an expert educational content generator.

Create exactly 15 *unique, topic-specific* multiple choice questions (MCQs)
based ONLY on the document text below.

Topic: "{topic}"

Rules:
- Each question MUST relate directly to "{topic}" and NOT be generic.
- Use facts or context from the document only.
- Include 4 clear options for each question.
- Include one correct "answer" that exactly matches one of the options.
- The answer must be logically correct based on the document.
- Do not add explanations, markdown, or extra text.

Return ONLY a valid JSON array like this:
[
  {{
    "question": "What is ...?",
    "options": ["A", "B", "C", "D"],
    "answer": "A"
  }}
]

Session ID: {session_id}

Document excerpt:
\"\"\"{DOC_CACHE[:9000]}\"\"\"
"""

    try:
        res = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # lower = more accurate and less random
        )

        raw = res.choices[0].message.content.strip()
        print("\n---- RAW AI RESPONSE ----\n", raw, "\n--------------------------")

        clean = raw.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\[[\s\S]*\]", clean)
        if not match:
            return jsonify({"ok": False, "error": "AI did not return JSON", "raw": clean})

        json_text = match.group(0)
        json_text = (
            json_text.replace("“", '"')
            .replace("”", '"')
            .replace("‘", "'")
            .replace("’", "'")
            .replace("\\'", "'")
            .replace("\n", "")
            .replace("\r", "")
        )

        # Try parsing JSON safely
        try:
            quiz = json.loads(json_text)
        except json.JSONDecodeError:
            fixed = re.sub(r",\s*]", "]", json_text)
            fixed = re.sub(r",\s*}", "}", fixed)
            quiz = json.loads(fixed)

        #  Ensure each "answer" is actually one of its options
        for q in quiz:
            if "answer" not in q or q["answer"] not in q.get("options", []):
                q["answer"] = q.get("options", [""])[0]

        return jsonify({"ok": True, "questions": quiz})

    except Exception as e:
        import traceback
        traceback.print_exc()
        if "rate_limit" in str(e).lower() or "429" in str(e):
            return jsonify({
                "ok": False,
                "error": "Rate limit reached — please wait and try again."
            })
        return jsonify({"ok": False, "error": f"Server crashed: {e}"})
    

# ==================================================
# ===============  CHATBOT FEATURE  =================
# ==================================================
@app.route("/chat")
def chat_page():
    global DOC_CACHE
    if not DOC_CACHE and os.path.exists(TEMP_FILE):
        with open(TEMP_FILE, "r", encoding="utf-8") as tmp:
            DOC_CACHE = tmp.read()

    if not DOC_CACHE:
        return render_template("code2.html", show_upload_warning=True)

    return render_template("chatbot.html")


@app.route("/chat_api", methods=["POST"])
def chat_api():
    try:
        global DOC_CACHE
        data = request.get_json(force=True, silent=True) or {}
        messages = data.get("messages", [])[:12]
        client_session = data.get("session_id") or session.get("chat_session") or str(uuid.uuid4())[:8]
        session["chat_session"] = client_session

        #  Ensure document exists
        if not DOC_CACHE and os.path.exists(TEMP_FILE):
            with open(TEMP_FILE, "r", encoding="utf-8") as tmp:
                DOC_CACHE = tmp.read()

        if not DOC_CACHE:
            return jsonify({"ok": False, "error": "No document uploaded. Please upload before chatting."}), 400

        if not messages or not any(m.get("role") == "user" for m in messages):
            return jsonify({"ok": False, "error": "Missing user message(s)."}), 400

        #  Build prompt
        system_prompt = f"""
You are a helpful assistant that answers questions using ONLY the provided document.
If the document lacks the info, reply: "I don't know — the document doesn't provide that information."

Document excerpt:
\"\"\"{DOC_CACHE[:12000]}\"\"\"
"""

        model_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            role = m.get("role", "user")
            model_messages.append({"role": role, "content": m.get("content", "")})

        #  Call Groq API
        res = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=model_messages,
            temperature=0.0,
            max_tokens=512,
        )
        reply = res.choices[0].message.content.strip()
        return jsonify({"ok": True, "reply": reply, "session_id": client_session})

    except Exception as e:
        err_text = str(e)
        print("Chatbot error:", err_text)  # log for debugging
        if "401" in err_text or "api_key" in err_text.lower():
            return jsonify({"ok": False, "error": "Groq API key is invalid or missing."}), 500
        elif "rate" in err_text.lower() or "429" in err_text:
            return jsonify({"ok": False, "error": "Rate limit reached — try again later."}), 429
        else:
            return jsonify({"ok": False, "error": f"Unexpected error: {err_text}"}), 500


# --- Summarizer routes (add to app.py near other feature routes) ---
@app.route("/summarize")
def summarize_page():
    """Render summarizer UI (requires uploaded document)."""
    global DOC_CACHE
    if not DOC_CACHE and os.path.exists(TEMP_FILE):
        with open(TEMP_FILE, "r", encoding="utf-8") as tmp:
            DOC_CACHE = tmp.read()
    if not DOC_CACHE:
        return render_template("code2.html", show_upload_warning=True)
    return render_template("summary.html")


@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    """
    Produce a QuillBot-like summary for the uploaded document only.
    Accepts JSON: { "mode": "short"|"detailed"|"bullets" } (optional)
    Returns JSON: { ok: True, summary: { short: "...", bullets: [...], key_points: "..." } }
    """
    global DOC_CACHE
    data = request.get_json(force=True, silent=True) or {}
    mode = (data.get("mode") or "short").lower()

    # ensure DOC_CACHE loaded
    if not DOC_CACHE and os.path.exists(TEMP_FILE):
        with open(TEMP_FILE, "r", encoding="utf-8") as tmp:
            DOC_CACHE = tmp.read()
    if not DOC_CACHE:
        return jsonify({"ok": False, "error": "No document uploaded"}), 400

    # Defensive length check
    if len(DOC_CACHE.strip()) < 50:
        return jsonify({"ok": False, "error": "Uploaded file has insufficient readable text."}), 400

    # Build prompt - require the model to use only the document and to return JSON
    excerpt = DOC_CACHE[:12000]  # trim to safe size for prompt
    prompt = f"""
You are a professional summarizer. Use ONLY the document text provided below — do NOT use the web or any outside knowledge.
Produce three outputs in JSON (no extra text): 
1) "short" — a concise 8–10 sentence summary in plain easy English (QuillBot-style: clear, polished, slightly formal).
2) "bullets" — 6–10 clear bullet points summarizing the document's main facts / sections (each 8–18 words).
3) "key_points" — 3 one-line actionable takeaways the learner should remember.

Return EXACTLY valid JSON like:
{{
  "short": "...",
  "bullets": ["...","...", "..."],
  "key_points": ["...","...","..."]
}}

Document:
\"\"\"{excerpt}\"\"\""""

    try:
        res = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=700,
        )
        raw = res.choices[0].message.content.strip()

        # strip code fences and find JSON
        clean = raw.replace("```json", "").replace("```", "").strip()
        import re, json
        m = re.search(r"\{[\s\S]*\}$", clean)
        if not m:
            # try looser search
            m = re.search(r"\{[\s\S]*\}", clean)
        if not m:
            return jsonify({"ok": False, "error": "Model did not return JSON.", "raw": clean}), 500

        json_text = m.group(0)
        payload = json.loads(json_text)

        # Optional: adapt output depending on requested mode
        if mode == "bullets":
            summary_out = {"short": payload.get("short", ""), "bullets": payload.get("bullets", []), "key_points": payload.get("key_points", [])}
        elif mode == "detailed":
            # For 'detailed' we can ask the model again for an expanded paragraph — but to keep simple, return same JSON
            summary_out = {"short": payload.get("short", ""), "bullets": payload.get("bullets", []), "key_points": payload.get("key_points", [])}
        else:
            summary_out = {"short": payload.get("short", ""), "bullets": payload.get("bullets", []), "key_points": payload.get("key_points", [])}

        return jsonify({"ok": True, "summary": summary_out})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500
    










# ------------------ SMART NOTES (paste this whole block into app.py) ------------------
# ------------------ SMART NOTES (robust, drop-in replacement) ------------------
# SmartNotes: helpers + routes (drop-in for app.py)
import re, json, ast, html, os
from flask import render_template, request, jsonify

# ---------- Robust sanitizer + parser helpers ----------

def _strip_code_fences_anywhere(text: str):
    """Remove triple-backtick code fences anywhere and return cleaned text."""
    if not text:
        return text
    # remove fenced code blocks but keep internal content where possible
    text = re.sub(r"```(?:json|text|txt)?\s*\n([\s\S]*?)\n```", r"\1", text, flags=re.IGNORECASE)
    text = text.replace("```", "")
    return text

def _normalize_text(t: str):
    """Normalize smart quotes, non-breaking spaces and control chars, convert python tokens."""
    if t is None:
        return t
    s = t
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    s = s.replace("\u00A0", " ")
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', s)
    # Python-style tokens -> JSON
    s = re.sub(r'\bNone\b', 'null', s)
    s = re.sub(r'\bTrue\b', 'true', s)
    s = re.sub(r'\bFalse\b', 'false', s)
    return s

def _remove_trailing_commas_safe(s: str):
    """Repeat removal of trailing commas before } or ] until stable."""
    prev = None
    out = s
    while prev != out:
        prev = out
        out = re.sub(r',\s*(\}|\])', r'\1', out)
    return out

def _find_first_balanced_block(s: str):
    """Scan and return first balanced {...} or [...] substring, or None."""
    if not s:
        return None
    for opener, closer in (("{","}"), ("[","]")):
        start = None
        depth = 0
        for i, ch in enumerate(s):
            if ch == opener and start is None:
                start = i
                depth = 1
                continue
            if start is not None:
                if ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        return s[start:i+1]
    return None

def _generate_candidates(raw: str):
    """
    Yield candidate JSON-like strings to try parsing.
    (balanced block first, then heuristic regex matches, then full cleaned text)
    """
    if raw is None:
        return
    s = _strip_code_fences_anywhere(raw)
    s = _normalize_text(s)

    # 1) balanced block via scanner
    blk = _find_first_balanced_block(s)
    if blk:
        yield blk
        yield blk.replace("'", '"')
        yield _remove_trailing_commas_safe(blk)
        yield _remove_trailing_commas_safe(blk.replace("'", '"'))

    # 2) looser regex (if no balanced or to try alternatives)
    m = re.search(r'(\{[\s\S]{20,}\})', s) or re.search(r'(\[[\s\S]{20,}\])', s)
    if m:
        cand = m.group(1)
        yield cand
        yield cand.replace("'", '"')
        yield _remove_trailing_commas_safe(cand)
        yield _remove_trailing_commas_safe(cand.replace("'", '"'))

    # 3) entire cleaned text as last resort
    yield s
    yield s.replace("'", '"')
    yield _remove_trailing_commas_safe(s)
    yield _remove_trailing_commas_safe(s.replace("'", '"'))

def _try_parse_json_variants(raw: str):
    """
    Aggressively try to parse JSON from raw string.
    Returns (parsed_obj_or_None, error_string_or_None).
    """
    if raw is None:
        return None, "no raw text provided"

    errors = []
    tried_count = 0
    for cand in _generate_candidates(raw):
        if not cand:
            continue
        # avoid repeating identical attempts
        tried_count += 1
        if not any(ch in cand for ch in ('{','[',']','}')):
            continue
        # Try json.loads first
        try:
            parsed = json.loads(cand)
            return parsed, None
        except Exception as je:
            errors.append(f"json.loads: {repr(je)} (len={len(cand)})")
        # Try ast.literal_eval fallback
        try:
            val = ast.literal_eval(cand)
            parsed = json.loads(json.dumps(val))
            return parsed, None
        except Exception as ae:
            errors.append(f"ast.literal_eval: {repr(ae)} (len={len(cand)})")

    # Nothing succeeded
    short_err = " | ".join(errors[:6]) if errors else "No parse attempts made"
    return None, f"All parse attempts failed after {tried_count} candidates. Errors: {short_err}"

# Backwards-compatible alias: keep endpoint calls unchanged
_strip_code_fences = _strip_code_fences_anywhere
# _try_parse_json_variants already defined with that name

# ---------- Page route ----------
@app.route("/smartnotes")
def smartnotes_page():
    global DOC_CACHE, TEMP_FILE
    try:
        if not globals().get("DOC_CACHE") and os.path.exists(globals().get("TEMP_FILE", "last_upload.txt")):
            with open(globals().get("TEMP_FILE", "last_upload.txt"), "r", encoding="utf-8") as f:
                globals()["DOC_CACHE"] = f.read()
    except Exception:
        globals()["DOC_CACHE"] = None

    if not globals().get("DOC_CACHE"):
        try:
            return render_template("code2.html", show_upload_warning=True)
        except Exception:
            return "No uploaded document found. Please upload a document and then open /smartnotes", 400
    return render_template("smartnotes.html")

# ---------- API endpoint ----------
@app.route("/api/smartnotes", methods=["POST"])
def api_smartnotes():
    global DOC_CACHE, TEMP_FILE, groq_client

    # ensure document cache loaded
    try:
        if not globals().get("DOC_CACHE") and os.path.exists(globals().get("TEMP_FILE","last_upload.txt")):
            with open(globals().get("TEMP_FILE","last_upload.txt"), "r", encoding="utf-8") as f:
                globals()["DOC_CACHE"] = f.read()
    except Exception:
        globals()["DOC_CACHE"] = None

    if not globals().get("DOC_CACHE"):
        return jsonify({"ok": False, "error": "No uploaded document found."}), 400

    excerpt = globals()["DOC_CACHE"][:30000]

    prompt = f"""
You are a friendly tutor and note-taking assistant. Use ONLY the document text below — do NOT use the web or outside knowledge.
Produce DETAILED study notes and explanations that help a beginner understand the topic thoroughly. Base everything only on the document.

Return exactly one JSON object with keys:
  - "outline": array of objects with "heading" and "bullets" (short bullets)
  - "explanations": a single string that contains five sub-sections (paragraphs) with headings:
       "Overview", "How it works", "Why it matters", "Common misunderstandings", "One short example or analogy".
  - "q_and_a": array of 6 objects with "q" and "a"
  - "quick_facts": array of 8 one-line factual statements.

Tone: helpful, simple, conversational.
Important rules:
- Use ONLY facts and phrasing from the document excerpt. If not present, say "Not specified in the document." for that item.
- Return ONLY valid JSON. No surrounding commentary, markdown, or code fences.

Document:
\"\"\"{excerpt}\"\"\""""

    if "groq_client" not in globals():
        return jsonify({"ok": False, "error": "Server not configured: groq_client is not defined. Configure your Groq client in app.py"}), 500

    # call Groq API defensively
    try:
        res = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role":"user","content":prompt}],
            temperature=0.12,
            max_tokens=2400
        )
    except Exception as e_call:
        app.logger.exception("Groq API call failed")
        return jsonify({"ok": False, "error": "API call failed: " + str(e_call)}), 500

    # extract text from response defensively
    try:
        raw = None
        if hasattr(res, "choices") and len(res.choices) > 0:
            choice0 = res.choices[0]
            raw = getattr(getattr(choice0, "message", None), "content", None) or getattr(choice0, "text", None)
        if raw is None:
            raw = str(res)
        raw = raw if isinstance(raw, str) else str(raw)
    except Exception as e_extract:
        app.logger.exception("Failed extracting raw from Groq response")
        return jsonify({"ok": False, "error": "Failed to extract model response", "exception": str(e_extract)}), 500

    # short server log for debugging
    try:
        app.logger.info("SMARTNOTES RAW (trim): %s", (raw[:1500] if raw else ""))
    except Exception:
        pass

    # sanitize & parse
    raw_clean = _strip_code_fences(raw) if callable(_strip_code_fences) else (raw or "")
    try:
        payload, parse_err = _try_parse_json_variants(raw_clean)
    except Exception as e_parser:
        app.logger.exception("SmartNotes parser crashed")
        import traceback
        tb = traceback.format_exc()
        return jsonify({
            "ok": False,
            "error": "Parser crashed",
            "exception": str(e_parser),
            "traceback": tb.splitlines()[-20:],
            "raw_preview": raw[:4000]
        }), 500

    if payload is None:
        return jsonify({
            "ok": False,
            "error": "Failed to parse model JSON output.",
            "parse_error": str(parse_err),
            "raw_preview": (raw_clean[:4000] if raw_clean else raw[:4000])
        }), 500

    notes = {
        "outline": payload.get("outline", []),
        "explanations": payload.get("explanations", "") or payload.get("explanation", ""),
        "q_and_a": payload.get("q_and_a", []) or payload.get("q&a", []) or payload.get("qa", []),
        "quick_facts": payload.get("quick_facts", []) or payload.get("quickfacts", [])
    }

    return jsonify({"ok": True, "notes": notes})

# ------------------ END SMART NOTES block ------------------




# ------------------ END Smart Notes block ------------------




















# ---------- FLASHCARDS FEATURE (server-side) ----------
# ---------------- Robust Flashcards feature (drop-in) ----------------
import re, json, ast, uuid as _uuid
from flask import session, request, jsonify, render_template

# session keys
FLASH_SESSION_KEY = "flashcards_deck"
FLASH_INDEX_KEY = "flashcards_index"
FLASH_ID_KEY = "flashcards_session_id"

# Helper: safe sentence splitter (very simple)
def _sentences_from_text(text, max_sentences=50):
    if not text or not isinstance(text, str):
        return []
    s = re.sub(r'\s+', ' ', text).strip()
    parts = re.split(r'(?<=[.!?])\s+', s)
    parts = [p.strip() for p in parts if len(p.strip()) > 20]
    return parts[:max_sentences]

# Fallback deck generator (safe, no external API)
def generate_cards_fallback(document_text, count=20):
    sents = _sentences_from_text(document_text, max_sentences=count*2)
    cards = []
    if not sents:
        for i in range(min(count, 6)):
            cards.append({"q": f"Sample question {i+1}", "a": "Content was not available in the uploaded document."})
        return cards
    for i in range(0, min(len(sents), count*2), 2):
        q = sents[i] if i < len(sents) else ""
        a = sents[i+1] if (i+1) < len(sents) else "Not specified in the document."
        if q:
            cards.append({"q": q[:300], "a": a[:600]})
        if len(cards) >= count:
            break
    i = 0
    while len(cards) < count and i < len(sents):
        cards.append({"q": sents[i][:300], "a": "Not specified in the document."})
        i += 1
    return cards

# Robust JSON parsing helper (re-usable)
def _try_parse_json_variants(raw):
    if raw is None:
        return None, "no raw"
    try:
        clean = re.sub(r"```(?:json|text)?\s*", "", raw)
        clean = clean.replace("```", "")
        clean = clean.replace('\u00A0', ' ')
    except Exception as e:
        return None, f"clean_failed:{e}"
    try:
        return json.loads(clean), None
    except Exception:
        pass
    m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", clean)
    if m:
        cand = m.group(1)
        try:
            return json.loads(cand), None
        except Exception:
            try:
                val = ast.literal_eval(cand)
                return json.loads(json.dumps(val)), None
            except Exception as e2:
                return None, f"json_cand_failed:{e2}"
    try:
        val = ast.literal_eval(clean)
        return json.loads(json.dumps(val)), None
    except Exception as e3:
        return None, f"parse_failed:{e3}"

# Route: serve flashcards page
@app.route("/flashcards")
def flashcards_page():
    return render_template("flashcards.html")

# API: flashcards
@app.route("/api/flashcards", methods=["POST"])
def api_flashcards():
    global DOC_CACHE, TEMP_FILE, groq_client

    data = request.get_json(force=True, silent=True) or {}
    action = (data.get("action") or "next").lower()
    try:
        count = int(data.get("count", 20))
    except Exception:
        count = 20

    app.logger.info("Flashcards API called action=%s count=%s session_keys=%s", action, count, list(session.keys()))

    try:
        if not globals().get("DOC_CACHE") and os.path.exists(globals().get("TEMP_FILE", "last_upload.txt")):
            with open(globals().get("TEMP_FILE", "last_upload.txt"), "r", encoding="utf-8") as f:
                globals()["DOC_CACHE"] = f.read()
    except Exception:
        globals()["DOC_CACHE"] = None

    if action == "create":
        if not globals().get("DOC_CACHE"):
            return jsonify({"ok": False, "error": "No uploaded document found. Upload a document then generate flashcards."}), 400

        doc_excerpt = globals()["DOC_CACHE"][:15000]

        # Try to use groq_client if present & configured
        if "groq_client" in globals() and globals().get("groq_client") is not None:
            try:
                prompt = f"""
You are an educational AI. Create exactly {count} FLASHCARDS from the document below.
Return only a JSON array of objects like:
[{{"q": "Question?", "a": "Answer."}}, ...]
Do not add explanation text or markdown — only the array.

Document:
\"\"\"{doc_excerpt}\"\"\""""
                res = groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role":"user","content":prompt}],
                    temperature=0.0,
                    max_tokens=800,
                )
                raw = None
                try:
                    choice0 = res.choices[0]
                    raw = getattr(getattr(choice0, "message", None), "content", None) or getattr(choice0, "text", None)
                except Exception:
                    raw = str(res)
                raw = raw if isinstance(raw, str) else str(raw)

                parsed, perr = _try_parse_json_variants(raw)
                if parsed is None:
                    app.logger.warning("Groq returned unparsable output for flashcards: %s", perr)
                    cards = generate_cards_fallback(doc_excerpt, count=count)
                else:
                    if isinstance(parsed, list):
                        parsed_list = parsed
                    elif isinstance(parsed, dict):
                        for k in ("cards", "flashcards", "data", "items", "results"):
                            if k in parsed and isinstance(parsed[k], list):
                                parsed_list = parsed[k]
                                break
                        else:
                            if any(k in parsed for k in ("q","question","a","answer")):
                                parsed_list = [parsed]
                            else:
                                vals = [v for v in parsed.values() if isinstance(v, dict)]
                                parsed_list = vals if vals else [parsed]
                    else:
                        parsed_list = [parsed] if isinstance(parsed, (str,int)) else []

                    clean_cards = []
                    for item in parsed_list:
                        if isinstance(item, dict):
                            q = str(item.get("q") or item.get("question") or "").strip()
                            a = str(item.get("a") or item.get("answer") or "").strip()
                            if q:
                                clean_cards.append({"q": q, "a": a or "Not specified in the document."})
                        elif isinstance(item, str):
                            txt = item.strip()
                            if txt:
                                clean_cards.append({"q": txt, "a": "Not specified in the document."})
                    if clean_cards:
                        cards = clean_cards[:count]
                    else:
                        app.logger.warning("Groq parsed but produced no usable cards; falling back.")
                        cards = generate_cards_fallback(doc_excerpt, count=count)

            except Exception:
                app.logger.exception("Flashcards groq call/parsing failed — falling back to local generator.")
                cards = generate_cards_fallback(doc_excerpt, count=count)

        else:
            cards = generate_cards_fallback(doc_excerpt, count=count)

        session_id = str(_uuid.uuid4())[:8]
        session[FLASH_SESSION_KEY] = cards
        session[FLASH_INDEX_KEY] = 0
        session[FLASH_ID_KEY] = session_id
        session.modified = True

        first_card = cards[0] if cards else {"q": "No cards", "a": "No data"}
        remaining = max(0, len(cards) - 1)
        return jsonify({"ok": True, "session_id": session_id, "card": first_card, "remaining": remaining, "total": len(cards)}), 200

    elif action == "next":
        deck = session.get(FLASH_SESSION_KEY)
        idx = session.get(FLASH_INDEX_KEY, 0)
        app.logger.info("Flashcards next: session_keys=%s deck_exists=%s idx=%s", list(session.keys()), bool(deck), idx)
        if not deck:
            return jsonify({"ok": False, "error": "No flashcard deck in session. Create one first (action=create)."}), 400
        if idx >= len(deck):
            return jsonify({"ok": False, "error": "No more flashcards.", "finished": True}), 200
        card = deck[idx]
        session[FLASH_INDEX_KEY] = idx + 1
        session.modified = True
        remaining = max(0, len(deck) - (idx + 1))
        return jsonify({"ok": True, "card": card, "remaining": remaining, "index": idx, "total": len(deck)}), 200

    elif action == "status":
        deck = session.get(FLASH_SESSION_KEY, [])
        idx = session.get(FLASH_INDEX_KEY, 0)
        return jsonify({"ok": True, "has_deck": bool(deck), "index": idx, "total": len(deck), "remaining": max(0, len(deck)-idx)}), 200

    elif action == "reset":
        session.pop(FLASH_SESSION_KEY, None)
        session.pop(FLASH_INDEX_KEY, None)
        session.pop(FLASH_ID_KEY, None)
        session.modified = True
        return jsonify({"ok": True, "message": "Flashcards session reset."}), 200

    else:
        return jsonify({"ok": False, "error": f"Unknown action: {action}"}), 400
# ---------------- end flashcards ----------------

# ---------------- end flashcards ----------------














# ---------- BACKWARD COMPATIBILITY CHECK ----------
@app.route("/generate", methods=["POST"])
def generate_check():
    """Used by link.js to verify file presence."""
    global DOC_CACHE
    data = request.get_json(force=True, silent=True) or {}
    topic = data.get("topic", "")
    if topic == "__check__":
        if DOC_CACHE or os.path.exists(TEMP_FILE):
            return jsonify({"ok": True, "message": "File ready"})
        else:
            return jsonify({"ok": False, "error": "No file"})
    return jsonify({"ok": False, "error": "Invalid request"})


import traceback
import logging
# ensure app logger prints INFO+ to console
logging.basicConfig(level=logging.INFO)

@app.errorhandler(Exception)
def handle_uncaught_exception(e):
    # log stack trace
    app.logger.exception("UNHANDLED EXCEPTION:")
    tb = traceback.format_exc()
    # return JSON so front-end can display the error reliably
    return jsonify({
        "ok": False,
        "error": "Internal server error (see exception)",
        "exception": str(e),
        "traceback": tb.splitlines()[-10:]  # last 10 lines to keep response small
    }), 500

# --------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)









