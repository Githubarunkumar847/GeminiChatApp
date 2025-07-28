from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
import os
from dotenv import load_dotenv
from datetime import datetime
import markdown2

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# Configure Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.0-flash")

# In-memory user storage (use DB for production)
users = {}

@app.before_request
def init_chat():
    if 'chat' not in session:
        session['chat'] = []

@app.route("/")
def index():
    if "username" not in session:
        return redirect(url_for("auth"))
    history_html = [
        {
            'role': msg['role'],
            'html': markdown2.markdown(msg['text']),
            'timestamp': msg['timestamp']
        } for msg in session['chat']
    ]
    return render_template("chat.html", history=history_html, username=session["username"])

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

    chat_instance = model.start_chat(history=[{'role': m['role'], 'parts': [m['text']]} for m in session['chat']])
    response = chat_instance.send_message(user_message)

    user_entry = {'role': 'user', 'text': user_message, 'timestamp': timestamp}
    bot_entry = {'role': 'model', 'text': response.text, 'timestamp': timestamp}

    session['chat'].extend([user_entry, bot_entry])
    session.modified = True

    return jsonify({"response": response.text})

@app.route("/reset")
def reset():
    session['chat'] = []
    return "Chat reset."

if __name__ == "__main__":
    print("Flask app starting on http://127.0.0.1:5000")
    app.run(debug=True)
