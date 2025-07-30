from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import google.generativeai as genai
import markdown2
import fitz  # PyMuPDF
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# Configure Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.0-flash")

# In-memory user store (not for production)
users = {}

# File upload config
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"txt", "pdf"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.before_request
def initialize_session():
    session.setdefault("chat", [])
    session.setdefault("context", "")
    session.setdefault("voice_input", True)
    session.setdefault("voice_output", True)
    session.setdefault("theme", "light")

@app.route("/")
def index():
    if "username" not in session:
        return redirect(url_for("auth"))
    history_html = [
        {
            "role": msg["role"],
            "html": markdown2.markdown(msg["text"]),
            "timestamp": msg["timestamp"]
        } for msg in session["chat"]
    ]
    return render_template("chat.html", history=history_html,
                           username=session["username"],
                           voice_input=session["voice_input"],
                           voice_output=session["voice_output"],
                           theme=session["theme"])

@app.route("/auth", methods=["GET", "POST"])
def auth():
    return render_template("auth.html", error="")

@app.route("/signup", methods=["POST"])
def signup():
    username = request.form.get("username")
    password = request.form.get("password")
    if username in users:
        return render_template("auth.html", error="User already exists")
    users[username] = generate_password_hash(password)
    session["username"] = username
    return redirect(url_for("index"))

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")
    if username not in users or not check_password_hash(users[username], password):
        return render_template("auth.html", error="Invalid credentials")
    session["username"] = username
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth"))

@app.route("/send", methods=["POST"])
def send():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_message = request.json.get("message")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    full_context = session.get("context", "")
    complete_input = full_context + "\nUser: " + user_message

    chat_instance = model.start_chat(
        history=[{"role": m["role"], "parts": [m["text"]]} for m in session["chat"]]
    )
    response = chat_instance.send_message(complete_input)

    user_entry = {"role": "user", "text": user_message, "timestamp": timestamp}
    bot_entry = {"role": "model", "text": response.text, "timestamp": timestamp}

    session["chat"].extend([user_entry, bot_entry])
    session.modified = True

    return jsonify({"response": response.text})

@app.route("/reset")
def reset():
    session["chat"] = []
    session["context"] = ""
    return "Chat reset."

@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        extracted_text = ""
        ext = filename.rsplit(".", 1)[1].lower()
        if ext == "txt":
            with open(filepath, "r", encoding="utf-8") as f:
                extracted_text = f.read()
        elif ext == "pdf":
            with fitz.open(filepath) as doc:
                for page in doc:
                    extracted_text += page.get_text()

        session["context"] = extracted_text
        return jsonify({"message": "File uploaded and context added."})
    return jsonify({"error": "Invalid file type. Only .txt and .pdf allowed"}), 400

@app.route("/toggle-theme", methods=["POST"])
def toggle_theme():
    session["theme"] = "dark" if session.get("theme") == "light" else "light"
    return jsonify({"theme": session["theme"]})

@app.route("/toggle-voice", methods=["POST"])
def toggle_voice():
    setting = request.json.get("setting")
    value = not session.get(setting, True)
    session[setting] = value
    return jsonify({setting: value})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Flask app running at http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)
