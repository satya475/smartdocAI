import os
import io
import base64
import qrcode
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from PyPDF2 import PdfReader

load_dotenv()

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "devkey")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

with app.app_context():
    db.create_all()

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# -----------------------------
# DATABASE MODELS
# -----------------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))


class Upload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200))
    upload_time = db.Column(db.DateTime, server_default=db.func.now())
    user_id = db.Column(db.Integer)


# -----------------------------
# INDEX
# -----------------------------

@app.route("/")
def index():
    return render_template("index.html")


# -----------------------------
# AUTH
# -----------------------------

@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        username = request.form["username"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        user = User(username=username, email=email, password=password)

        db.session.add(user)
        db.session.commit()

        flash("Account created successfully")
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


# -----------------------------
# DASHBOARD
# -----------------------------

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        username=session["username"]
    )


@app.route("/my_account")
def my_account():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])

    return render_template(
        "account.html",
        username=user.username,
        email=user.email
    )


# -----------------------------
# HISTORY
# -----------------------------

@app.route("/upload_history")
def upload_history():

    if "user_id" not in session:
        return redirect(url_for("login"))

    uploads = Upload.query.filter_by(user_id=session["user_id"]).all()

    return render_template("history.html", uploads=uploads)


# -----------------------------
# PDF CHAT
# -----------------------------

@app.route("/pdf_chat", methods=["GET", "POST"])
def pdf_chat():

    extracted_text = ""
    summary = ""
    answer = ""

    if request.method == "POST":

        pdf = request.files.get("pdf")

        if pdf:
            reader = PdfReader(pdf)

            for page in reader.pages:
                text = page.extract_text()
                if text:
                    extracted_text += text

        action = request.form.get("action")

        if action == "summarize":
            summary = extracted_text[:1500]  # simple summary placeholder

        if action == "ask":
            question = request.form.get("question")
            answer = f"Question received: {question}"

    return render_template(
        "pdf_chat.html",
        extracted_text=extracted_text,
        summary=summary,
        answer=answer
    )


@app.route("/clear_pdf_session")
def clear_pdf_session():
    return redirect(url_for("pdf_chat"))


# -----------------------------
# OCR
# -----------------------------

@app.route("/ocr_extract", methods=["GET", "POST"])
def ocr_extract():

    raw_text = ""
    handwritten_text = ""
    structured_output = ""

    if request.method == "POST":

        file = request.files["file"]

        if file:
            filepath = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(filepath)
            raw_text = "OCR placeholder text"

    return render_template(
        "ocr_extract.html",
        raw_text=raw_text,
        handwritten_text=handwritten_text,
        structured_output=structured_output
    )


# -----------------------------
# QR GENERATOR
# -----------------------------

@app.route("/text_to_qr", methods=["GET", "POST"])
def text_to_qr():

    qr_image = None
    qr_filename = None

    if request.method == "POST":

        text = request.form["text"]

        img = qrcode.make(text)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")

        qr_image = base64.b64encode(buffer.getvalue()).decode()
        qr_filename = "qr.png"

    return render_template(
        "qr_generator.html",
        qr_image=qr_image,
        qr_filename=qr_filename
    )


# -----------------------------
# EQUATION PLOT
# -----------------------------

@app.route("/plot_equation", methods=["GET", "POST"])
def plot_equation():

    plot_url = None

    if request.method == "POST":

        equation = request.form["equation"]
        x_start = float(request.form["x_start"])
        x_end = float(request.form["x_end"])

        x = np.linspace(x_start, x_end, 400)

        try:
            y = eval(equation)

            plt.figure()
            plt.plot(x, y)

            buf = io.BytesIO()
            plt.savefig(buf, format="png")
            buf.seek(0)

            plot_url = base64.b64encode(buf.getvalue()).decode()

        except:
            flash("Invalid equation")

    return render_template(
        "plot_equation.html",
        plot_url=plot_url
    )


# -----------------------------
# PLOTSPAN ROUTES
# -----------------------------

@app.route("/plotspan_choice")
def plotspan_choice():
    return render_template("plotspan_choice.html")


@app.route("/step1_upload")
def step1_upload():
    return render_template("plot_step1_upload.html")


@app.route("/step2_chart")
def step2_chart():
    return render_template("plot_step2_chart.html")


@app.route("/step3_select")
def step3_select():
    return render_template("plot_step3_select.html")


# -----------------------------
# EQUATION SOLVER RESULT PAGE
# -----------------------------

@app.route("/solve_equation", methods=["POST"])
def solve_equation():

    eq = request.form["solve_equation"]

    result = f"Equation received: {eq}"

    return render_template("solve_result.html", result=result)


# -----------------------------
# START SERVER
# -----------------------------

if __name__ == "__main__":

    with app.app_context():
        db.create_all()

    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port)
