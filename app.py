from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
import sqlite3
import os
import webbrowser
from werkzeug.security import generate_password_hash, check_password_hash
import requests

project_root = os.path.dirname(os.path.abspath(__file__))
template_folder = os.path.join(project_root, "template")
if not os.path.isfile(os.path.join(template_folder, "index.html")):
    template_folder = project_root

static_folder = os.path.join(project_root, "static")
if not os.path.isfile(os.path.join(static_folder, "style.css")):
    static_folder = project_root

app = Flask(
    __name__,
    template_folder=template_folder,
    static_folder=static_folder,
)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "dev-only-change-this-secret"
)

if os.environ.get("RENDER"):
    DATABASE_PATH = os.environ.get(
        "DATABASE_PATH", "/tmp/student-portal/database.db"
    )
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", "/tmp/student-portal/uploads"
    )
else:
    DATABASE_PATH = os.environ.get(
        "DATABASE_PATH", os.path.join(app.root_path, "instance", "database.db")
    )
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", os.path.join(app.root_path, "uploads")
    )

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --------------------------------------------------
# DATABASE CONNECTION
# --------------------------------------------------

def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------
# CREATE DATABASE
# --------------------------------------------------

def init_db():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            duration TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER,
            title TEXT,
            filename TEXT,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER,
            title TEXT,
            url TEXT,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER,
            question TEXT,
            option1 TEXT,
            option2 TEXT,
            option3 TEXT,
            option4 TEXT,
            answer TEXT,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            course_id INTEGER,
            score INTEGER,
            total INTEGER,
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(course_id) REFERENCES courses(id)
        )
    """)

    # Default admin
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")

    admin = cursor.execute(
        "SELECT * FROM admins WHERE username=?",
        (admin_username,)
    ).fetchone()

    if not admin:
        cursor.execute(
            "INSERT INTO admins(username,password) VALUES(?,?)",
            (admin_username, generate_password_hash(admin_password))
        )

    conn.commit()
    conn.close()


init_db()


@app.before_request
def ensure_database():
    """Create the SQLite schema if the deployment starts with a new volume."""
    init_db()


# --------------------------------------------------
# HOME
# --------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# --------------------------------------------------
# STUDENT REGISTER
# --------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        hashed_password = generate_password_hash(password)

        conn = get_db()

        try:
            conn.execute(
                """
                INSERT INTO students(name,email,password)
                VALUES(?,?,?)
                """,
                (name, email, hashed_password)
            )

            conn.commit()
            conn.close()

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:

            conn.close()

            return "Email already registered."

    return render_template("register.html")


# --------------------------------------------------
# STUDENT LOGIN
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()

        student = conn.execute(
            "SELECT * FROM students WHERE email=?",
            (email,)
        ).fetchone()

        conn.close()

        if student and check_password_hash(
            student["password"], password
        ):

            session["student_id"] = student["id"]
            session["student_name"] = student["name"]

            return redirect(url_for("student_dashboard"))

        return render_template(
            "login.html",
            error="Invalid email or password"
        )

    return render_template("login.html")


# --------------------------------------------------
# STUDENT DASHBOARD
# --------------------------------------------------

@app.route("/std/dashbrd")
def student_dashboard():

    if "student_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    courses = conn.execute(
        "SELECT * FROM courses"
    ).fetchall()

    conn.close()

    return render_template(
        "std_dashbrd.html",
        courses=courses
    )


# --------------------------------------------------
# COURSES
# --------------------------------------------------

@app.route("/courses")
def courses():

    if "student_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    courses = conn.execute(
        "SELECT * FROM courses"
    ).fetchall()

    conn.close()

    return render_template(
        "courses.html",
        courses=courses
    )


# --------------------------------------------------
# COURSE DETAILS
# --------------------------------------------------

@app.route("/course/<int:course_id>")
def course(course_id):

    if "student_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    course_data = conn.execute(
        "SELECT * FROM courses WHERE id=?",
        (course_id,)
    ).fetchone()

    materials = conn.execute(
        "SELECT * FROM materials WHERE course_id=?",
        (course_id,)
    ).fetchall()

    videos = conn.execute(
        "SELECT * FROM videos WHERE course_id=?",
        (course_id,)
    ).fetchall()

    quiz_count = conn.execute(
        "SELECT COUNT(*) AS count FROM quizzes WHERE course_id=?",
        (course_id,)
    ).fetchone()["count"]

    conn.close()

    return render_template(
        "course.html",
        course=course_data,
        materials=materials,
        videos=videos,
        quiz_count=quiz_count
    )


# --------------------------------------------------
# DOWNLOAD MATERIAL
# --------------------------------------------------

@app.route("/download/<filename>")
def download(filename):

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename,
        as_attachment=True
    )


# --------------------------------------------------
# QUIZ
# --------------------------------------------------

@app.route("/quiz/<int:course_id>", methods=["GET", "POST"])
def quiz(course_id):

    if "student_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    questions = conn.execute(
        "SELECT * FROM quizzes WHERE course_id=?",
        (course_id,)
    ).fetchall()

    if request.method == "POST":

        score = 0

        for question in questions:

            answer = request.form.get(
                "question_" + str(question["id"])
            )

            if answer == question["answer"]:
                score += 1

        total = len(questions)

        conn.execute(
            """
            INSERT INTO results
            (student_id,course_id,score,total)
            VALUES(?,?,?,?)
            """,
            (
                session["student_id"],
                course_id,
                score,
                total
            )
        )

        conn.commit()
        conn.close()

        return render_template(
            "result.html",
            score=score,
            total=total
        )

    conn.close()

    return render_template(
        "quiz.html",
        questions=questions,
        course_id=course_id
    )


# --------------------------------------------------
# STUDENT RESULTS
# --------------------------------------------------

@app.route("/quiz-result")
def my_results():

    if "student_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    results = conn.execute("""
        SELECT results.*, courses.title
        FROM results
        JOIN courses ON results.course_id = courses.id
        WHERE results.student_id=?
    """, (session["student_id"],)).fetchall()

    conn.close()

    return render_template(
        "result.html",
        results=results
    )


# --------------------------------------------------
# ADMIN LOGIN
# --------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()

        admin = conn.execute(
            "SELECT * FROM admins WHERE username=?",
            (username,)
        ).fetchone()

        conn.close()

        if admin and check_password_hash(
            admin["password"], password
        ):

            session["admin"] = username

            return redirect(
                url_for("admin_dashboard")
            )

        return render_template(
            "admin_login.html",
            error="Invalid admin username or password"
        )

    return render_template("admin_login.html")


# --------------------------------------------------
# ADMIN DASHBOARD
# --------------------------------------------------

@app.route("/admin/dashbrd")
def admin_dashboard():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db()

    students = conn.execute(
        "SELECT COUNT(*) AS count FROM students"
    ).fetchone()["count"]

    courses_count = conn.execute(
        "SELECT COUNT(*) AS count FROM courses"
    ).fetchone()["count"]

    results = conn.execute(
        "SELECT COUNT(*) AS count FROM results"
    ).fetchone()["count"]

    courses = conn.execute(
        "SELECT * FROM courses ORDER BY id DESC"
    ).fetchall()

    conn.close()

    return render_template(
        "admin_dashbrd.html",
        students=students,
        courses=courses_count,
        results=results,
        course_list=courses
    )


# --------------------------------------------------
# ADD COURSE
# --------------------------------------------------

@app.route("/admin/add-course", methods=["GET", "POST"])
def add_course():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    if request.method == "POST":

        title = request.form["title"]
        description = request.form["description"]
        duration = request.form["duration"]

        conn = get_db()

        conn.execute(
            """
            INSERT INTO courses(title,description,duration)
            VALUES(?,?,?)
            """,
            (title, description, duration)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("admin_dashboard"))

    return render_template("add_course.html")


# --------------------------------------------------
# DELETE COURSE
# --------------------------------------------------

@app.route("/admin/delete-course/<int:course_id>")
def delete_course(course_id):

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db()

    materials = conn.execute(
        "SELECT filename FROM materials WHERE course_id=?",
        (course_id,)
    ).fetchall()

    for material in materials:
        filename = material["filename"]
        if filename:
            file_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )
            if os.path.exists(file_path):
                os.remove(file_path)

    conn.execute(
        "DELETE FROM results WHERE course_id=?",
        (course_id,)
    )
    conn.execute(
        "DELETE FROM quizzes WHERE course_id=?",
        (course_id,)
    )
    conn.execute(
        "DELETE FROM videos WHERE course_id=?",
        (course_id,)
    )
    conn.execute(
        "DELETE FROM materials WHERE course_id=?",
        (course_id,)
    )
    conn.execute(
        "DELETE FROM courses WHERE id=?",
        (course_id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("admin_dashboard"))


# --------------------------------------------------
# UPLOAD MATERIAL
# --------------------------------------------------

@app.route("/admin/add-material", methods=["GET", "POST"])
def add_material():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db()

    courses = conn.execute(
        "SELECT * FROM courses"
    ).fetchall()

    if request.method == "POST":

        course_id = request.form["course_id"]
        title = request.form["title"]

        file = request.files["file"]

        if file:

            filename = file.filename

            file.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )

            conn.execute(
                """
                INSERT INTO materials
                (course_id,title,filename)
                VALUES(?,?,?)
                """,
                (course_id, title, filename)
            )

            conn.commit()

            conn.close()

            return redirect(
                url_for("admin_dashboard")
            )

    conn.close()

    return render_template(
        "add_materials.html",
        courses=courses
    )


# --------------------------------------------------
# ADD VIDEO
# --------------------------------------------------

@app.route("/admin/add-video", methods=["GET", "POST"])
def add_video():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db()

    courses = conn.execute(
        "SELECT * FROM courses"
    ).fetchall()

    if request.method == "POST":

        course_id = request.form["course_id"]
        title = request.form["title"]
        url = request.form["url"]

        conn.execute(
            """
            INSERT INTO videos(course_id,title,url)
            VALUES(?,?,?)
            """,
            (course_id, title, url)
        )

        conn.commit()
        conn.close()

        return redirect(
            url_for("admin_dashboard")
        )

    conn.close()

    return render_template(
        "add_video.html",
        courses=courses
    )


# --------------------------------------------------
# ADD QUIZ QUESTION
# --------------------------------------------------

@app.route("/admin/add-quiz", methods=["GET", "POST"])
def add_quiz():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db()

    courses = conn.execute(
        "SELECT * FROM courses"
    ).fetchall()

    if request.method == "POST":

        course_id = request.form["course_id"]
        question = request.form["question"]

        option1 = request.form["option1"]
        option2 = request.form["option2"]
        option3 = request.form["option3"]
        option4 = request.form["option4"]

        answer = request.form["answer"]
        answer_options = {
            "1": option1,
            "2": option2,
            "3": option3,
            "4": option4,
        }

        conn.execute(
            """
            INSERT INTO quizzes
            (course_id,question,option1,option2,
             option3,option4,answer)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                course_id,
                question,
                option1,
                option2,
                option3,
                option4,
                answer_options[answer]
            )
        )

        conn.commit()
        conn.close()

        return redirect(
            url_for("admin_dashboard")
        )

    conn.close()

    return render_template(
        "add_quiz.html",
        courses=courses
    )


# --------------------------------------------------
# VIEW STUDENTS
# --------------------------------------------------

@app.route("/admin/registered_students")
def students():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db()

    students = conn.execute(
        "SELECT id,name,email FROM students"
    ).fetchall()

    conn.close()

    return render_template(
        "registered_students.html",
        students=students
    )


# --------------------------------------------------
# VIEW RESULTS
# --------------------------------------------------

@app.route("/admin/results")
def results():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db()

    results = conn.execute("""
        SELECT
            students.name,
            courses.title,
            results.score,
            results.total
        FROM results
        JOIN students
        ON results.student_id = students.id
        JOIN courses
        ON results.course_id = courses.id
    """).fetchall()

    conn.close()

    return render_template(
        "quiz_result.html",
        results=results
    )


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("index"))


# --------------------------------------------------
# RUN APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    pass


def create_app():
    """Application factory for compatibility with run scripts and WSGI servers.

    Initializes the database and returns the Flask `app` instance.
    """
    init_db()
    return app


def open_portal():
    """Open the browser to the local portal when the desktop app is launched."""
    webbrowser.open_new_tab("http://127.0.0.1:5000")


if __name__ == "__main__":
    init_db()
    open_portal()

    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000
    )