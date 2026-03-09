import os
import io
import base64
import qrcode
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pytesseract
import cv2

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from PyPDF2 import PdfReader

load_dotenv()

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

API_KEY = os.getenv("API_KEY")

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# -------------------------
# DATABASE
# -------------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))

class Upload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200))
    upload_time = db.Column(db.DateTime, server_default=db.func.now())
    user_id = db.Column(db.Integer)

# -------------------------
# INDEX
# -------------------------

@app.route("/")
def index():
    return render_template("index.html")

# -------------------------
# AUTH
# -------------------------

@app.route("/signup", methods=["GET","POST"])
def signup():

    if request.method == "POST":

        username = request.form["username"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        user = User(username=username,email=email,password=password)

        db.session.add(user)
        db.session.commit()

        flash("Account created")
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password,password):

            session["user_id"] = user.id
            session["username"] = user.username

            return redirect(url_for("dashboard"))

        flash("Invalid credentials")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# -------------------------
# DASHBOARD
# -------------------------

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template("dashboard.html",
                           username=session["username"])

# -------------------------
# ACCOUNT
# -------------------------

@app.route("/my_account")
def my_account():

    user = User.query.get(session["user_id"])

    return render_template(
        "account.html",
        username=user.username,
        email=user.email
    )

# -------------------------
# HISTORY
# -------------------------

@app.route("/upload_history")
def upload_history():

    uploads = Upload.query.filter_by(user_id=session["user_id"]).all()

    return render_template("history.html",uploads=uploads)

# -------------------------
# PDF CHAT
# -------------------------

def summarize_text(text):

    url = "https://api.openai.com/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4o-mini",
        "messages":[
            {"role":"user","content":f"Summarize this text:\n{text}"}
        ]
    }

    r = requests.post(url,json=payload,headers=headers)

    return r.json()["choices"][0]["message"]["content"]


@app.route("/pdf_chat", methods=["GET","POST"])
def pdf_chat():

    extracted_text=""
    summary=""
    answer=""

    if request.method == "POST":

        pdf = request.files.get("pdf")

        if pdf:

            reader = PdfReader(pdf)

            for page in reader.pages:
                extracted_text += page.extract_text()

        action = request.form.get("action")

        if action == "summarize":
            summary = summarize_text(extracted_text)

        if action == "ask":

            question = request.form["question"]

            answer = summarize_text(
                extracted_text + "\n\nQuestion:" + question
            )

    return render_template(
        "pdf_chat.html",
        extracted_text=extracted_text,
        summary=summary,
        answer=answer
    )

# -------------------------
# OCR (TESSERACT)
# -------------------------

@app.route("/ocr_extract", methods=["GET","POST"])
def ocr_extract():

    raw_text = ""

    if request.method == "POST":

        file = request.files["file"]

        filepath = os.path.join(UPLOAD_FOLDER,file.filename)

        file.save(filepath)

        image = cv2.imread(filepath)

        raw_text = pytesseract.image_to_string(image)

    return render_template(
        "ocr_extract.html",
        raw_text=raw_text,
        handwritten_text="",
        structured_output=""
    )

# -------------------------
# QR GENERATOR
# -------------------------

@app.route("/text_to_qr", methods=["GET","POST"])
def text_to_qr():

    qr_image=None

    if request.method=="POST":

        text=request.form["text"]

        img=qrcode.make(text)

        buffer=io.BytesIO()

        img.save(buffer,format="PNG")

        qr_image=base64.b64encode(buffer.getvalue()).decode()

    return render_template("qr_generator.html",qr_image=qr_image)

# -------------------------
# EQUATION PLOT
# -------------------------

@app.route("/plot_equation", methods=["GET","POST"])
def plot_equation():

    plot_url=None

    if request.method=="POST":

        eq=request.form["equation"]

        x_start=float(request.form["x_start"])
        x_end=float(request.form["x_end"])

        x=np.linspace(x_start,x_end,400)

        y=eval(eq)

        plt.figure()
        plt.plot(x,y)

        buf=io.BytesIO()

        plt.savefig(buf,format="png")

        plot_url=base64.b64encode(buf.getvalue()).decode()

    return render_template(
        "plot_equation.html",
        plot_url=plot_url
    )

# -------------------------
# RUN
# -------------------------

if __name__ == "__main__":

    with app.app_context():
        db.create_all()

    app.run(debug=True)