import os
import io
import base64
import numpy as np
import qrcode
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from PyPDF2 import PdfReader

# ------------------------------------------------
# FLASK CONFIG
# ------------------------------------------------

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

db = SQLAlchemy(app)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ------------------------------------------------
# DATABASE MODELS
# ------------------------------------------------

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))


class Upload(db.Model):
    __tablename__ = "uploads"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200))
    upload_time = db.Column(db.DateTime, server_default=db.func.now())
    user_id = db.Column(db.Integer)


with app.app_context():
    db.create_all()

# ------------------------------------------------
# INDEX
# ------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ------------------------------------------------
# AUTHENTICATION
# ------------------------------------------------

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


# ------------------------------------------------
# DASHBOARD
# ------------------------------------------------

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


# ------------------------------------------------
# UPLOAD HISTORY
# ------------------------------------------------

@app.route("/upload_history")
def upload_history():

    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        uploads = Upload.query.filter_by(user_id=session["user_id"]).all()
    except:
        uploads = []

    return render_template("history.html", uploads=uploads)


# ------------------------------------------------
# PDF CHAT
# ------------------------------------------------

@app.route("/pdf_chat", methods=["GET", "POST"])
def pdf_chat():

    extracted_text = ""
    summary = ""
    answer = ""
    action = None

    if request.method == "POST":

        action = request.form.get("action")

        if action == "extract":

            pdf = request.files.get("pdf")

            if pdf:

                reader = PdfReader(pdf)

                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        extracted_text += text

                if "user_id" in session:
                    upload = Upload(
                        filename=pdf.filename,
                        user_id=session["user_id"]
                    )
                    db.session.add(upload)
                    db.session.commit()

        elif action == "summarize":

            extracted_text = request.form.get("extracted_text", "")
            summary = extracted_text[:1500]

        elif action == "ask":

            extracted_text = request.form.get("extracted_text", "")
            question = request.form.get("question")

            answer = f"Question received: {question}"

    return render_template(
        "pdf_chat.html",
        extracted_text=extracted_text,
        summary=summary,
        answer=answer,
        action=action
    )


@app.route("/clear_pdf_session")
def clear_pdf_session():
    return redirect(url_for("pdf_chat"))


# ------------------------------------------------
# QR GENERATOR
# ------------------------------------------------

@app.route("/text_to_qr", methods=["GET", "POST"])
def text_to_qr():

    qr_image = None
    qr_filename = None

    if request.method == "POST":

        text = request.form.get("text", "")

        try:

            if len(text) > 2000:
                flash("Text too long for QR code")
                return render_template("qr_generator.html")

            img = qrcode.make(text)

            buffer = io.BytesIO()
            img.save(buffer, format="PNG")

            qr_image = base64.b64encode(buffer.getvalue()).decode()
            qr_filename = "qr.png"

        except:
            flash("QR generation failed")

    return render_template(
        "qr_generator.html",
        qr_image=qr_image,
        qr_filename=qr_filename
    )


# ------------------------------------------------
# OCR PAGE
# ------------------------------------------------

@app.route("/ocr_extract", methods=["GET", "POST"])
def ocr_extract():

    raw_text = ""
    handwritten_text = ""
    structured_output = ""

    if request.method == "POST":

        file = request.files.get("file")

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


# ------------------------------------------------
# EQUATION PLOT
# ------------------------------------------------

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


# ------------------------------------------------
# PLOTSPAN PAGES
# ------------------------------------------------

@app.route("/plotspan_choice")
def plotspan_choice():
    return render_template("plotspan_choice.html")


@app.route("/step1_upload", methods=["GET", "POST"])
def step1_upload():
    return render_template("plot_step1_upload.html")


@app.route("/step2_chart", methods=["GET", "POST"])
def step2_chart():
    return render_template("plot_step2_chart.html")


@app.route("/step3_select", methods=["GET", "POST"])
def step3_select():
    return render_template("plot_step3_select.html")


# ------------------------------------------------
# EQUATION SOLVER RESULT
# ------------------------------------------------

@app.route("/solve_equation", methods=["POST"])
def solve_equation():

    eq = request.form["solve_equation"]
    result = f"Equation received: {eq}"

    return render_template("solve_result.html", result=result)


# ------------------------------------------------
# RUN APP (FOR LOCAL)
# ------------------------------------------------

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )
