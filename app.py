import os
import io
import base64
import numpy as np
import qrcode
import matplotlib
import pandas as pd
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_file
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from PyPDF2 import PdfReader

# Configure Matplotlib for headless server (Render/Linux)
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ------------------------------------------------
# FLASK CONFIG
# ------------------------------------------------

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-123")

# Handle Render's PostgreSQL URL format
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL or "sqlite:///smartdoc.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

db = SQLAlchemy(app)

# Use /tmp for ephemeral storage on Render
UPLOAD_FOLDER = "/tmp/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ------------------------------------------------
# DATABASE MODELS
# ------------------------------------------------

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Upload(db.Model):
    __tablename__ = "uploads"
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200))
    upload_time = db.Column(db.DateTime, server_default=db.func.now())
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

with app.app_context():
    db.create_all()

# ------------------------------------------------
# AUTHENTICATION
# ------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        if User.query.filter_by(username=username).first():
            flash("Username already exists")
            return redirect(url_for("signup"))

        user = User(username=username, email=email, password=password)
        db.session.add(user)
        db.session.commit()
        flash("Account created successfully!")
        return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            session["username"] = user.username
            return redirect(url_for("dashboard"))
        flash("Invalid credentials")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ------------------------------------------------
# DASHBOARD & ACCOUNT
# ------------------------------------------------

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html", username=session["username"])

@app.route("/my_account")
def my_account():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user = User.query.get(session["user_id"])
    return render_template("account.html", username=user.username, email=user.email)

@app.route("/upload_history")
def upload_history():
    if "user_id" not in session:
        return redirect(url_for("login"))
    uploads = Upload.query.filter_by(user_id=session["user_id"]).all()
    return render_template("history.html", uploads=uploads)

# ------------------------------------------------
# PDF CHAT
# ------------------------------------------------

@app.route("/pdf_chat", methods=["GET", "POST"])
def pdf_chat():
    extracted_text, summary, answer, action = "", "", "", None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "extract":
            pdf = request.files.get("pdf")
            if pdf:
                reader = PdfReader(pdf)
                for page in reader.pages:
                    text = page.extract_text()
                    if text: extracted_text += text
                if "user_id" in session:
                    db.session.add(Upload(filename=pdf.filename, user_id=session["user_id"]))
                    db.session.commit()
        elif action == "summarize":
            extracted_text = request.form.get("extracted_text", "")
            summary = extracted_text[:1500] + "..." if len(extracted_text) > 1500 else extracted_text
        elif action == "ask":
            extracted_text = request.form.get("extracted_text", "")
            question = request.form.get("question")
            answer = f"I found the following related to '{question}': [Simulated AI Response]"

    return render_template("pdf_chat.html", extracted_text=extracted_text, summary=summary, answer=answer, action=action)

# ------------------------------------------------
# QR GENERATOR
# ------------------------------------------------

@app.route("/text_to_qr", methods=["GET", "POST"])
def text_to_qr():
    qr_image = None
    if request.method == "POST":
        text = request.form.get("text", "")
        try:
            img = qrcode.make(text)
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            qr_image = base64.b64encode(buffer.getvalue()).decode()
        except:
            flash("QR generation failed")
    return render_template("qr_generator.html", qr_image=qr_image)

# ------------------------------------------------
# OCR (Using simple logic for Free Tier)
# ------------------------------------------------

@app.route("/ocr_extract", methods=["GET", "POST"])
def ocr_extract():
    raw_text = ""
    if request.method == "POST":
        file = request.files.get("file")
        if file:
            # Render/Linux safe path
            filepath = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(filepath)
            raw_text = f"Successfully uploaded {file.filename}. (OCR requires Tesseract binary to be installed on server)."
    return render_template("ocr_extract.html", raw_text=raw_text)

# ------------------------------------------------
# EQUATION PLOT
# ------------------------------------------------

@app.route("/plot_equation", methods=["GET", "POST"])
def plot_equation():
    plot_url = None
    if request.method == "POST":
        try:
            equations = request.form.get("equation", "x")
            x_start, x_end = float(request.form.get("x_start", -10)), float(request.form.get("x_end", 10))
            y_start, y_end = float(request.form.get("y_start", -10)), float(request.form.get("y_end", 10))
            
            session["last_equation"] = equations # Store for download
            x = np.linspace(x_start, x_end, 400)
            safe_dict = {"x": x, "np": np, "sin": np.sin, "cos": np.cos, "tan": np.tan, "log": np.log, "exp": np.exp}
            
            fig, ax = plt.subplots()
            for eq in [e.strip() for e in equations.split(";")]:
                y = eval(eq, {"__builtins__": None}, safe_dict)
                ax.plot(x, y, label=eq)
            
            ax.set_xlim(x_start, x_end); ax.set_ylim(y_start, y_end)
            ax.axhline(0, color='black', lw=1); ax.axvline(0, color='black', lw=1)
            ax.legend(); ax.grid(True)
            
            buf = io.BytesIO()
            fig.savefig(buf, format="png")
            plot_url = base64.b64encode(buf.getvalue()).decode()
            plt.close(fig)
        except Exception:
            flash("Invalid equation format.")
    return render_template("plot_equation.html", plot_url=plot_url)

@app.route("/download_equation_plot")
def download_equation_plot():
    eq = session.get("last_equation", "x")
    x = np.linspace(-10, 10, 400)
    y = eval(eq.split(';')[0], {"__builtins__": None}, {"x": x, "np": np, "sin": np.sin})
    fig, ax = plt.subplots()
    ax.plot(x, y)
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    buf.seek(0)
    plt.close(fig)
    return send_file(buf, mimetype="image/png", as_attachment=True, download_name="plot.png")

# ------------------------------------------------
# PLOTSPAN (EXCEL PLOTTING)
# ------------------------------------------------

@app.route("/plotspan_choice")
def plotspan_choice():
    return render_template("plotspan_choice.html")

@app.route("/step1_upload", methods=["GET", "POST"])
def step1_upload():
    if request.method == "POST":
        file = request.files.get("file")
        if file and file.filename.endswith(('.csv', '.xlsx')):
            path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(path)
            df = pd.read_csv(path) if path.endswith('.csv') else pd.read_excel(path)
            session['temp_csv'] = path
            session['columns'] = df.columns.tolist()
            return redirect(url_for("step2_chart"))
    return render_template("plot_step1_upload.html")

@app.route("/step2_chart", methods=["GET", "POST"])
def step2_chart():
    if request.method == "POST":
        session['chart_type'] = request.form.get("chart_type")
        return redirect(url_for("step3_select"))
    return render_template("plot_step2_chart.html")

@app.route("/step3_select", methods=["GET", "POST"])
def step3_select():
    cols = session.get('columns', [])
    plot_url = None
    if request.method == "POST":
        x_axis, y_axis = request.form.get("x_axis"), request.form.get("y_axis")
        df = pd.read_csv(session['temp_csv'])
        plt.figure(figsize=(8,5))
        if session.get('chart_type') == "bar":
            df.plot(kind='bar', x=x_axis, y=y_axis)
        else:
            df.plot(kind='line', x=x_axis, y=y_axis)
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        plot_url = base64.b64encode(buf.getvalue()).decode()
        plt.close()
    return render_template("plot_step3_select.html", columns=cols, plot_url=plot_url)

# ------------------------------------------------
# SOLVER
# ------------------------------------------------

@app.route("/solve_equation", methods=["POST"])
def solve_equation():
    eq = request.form["solve_equation"]
    return render_template("solve_result.html", result=f"Processed: {eq}. Solution: [Result]")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
