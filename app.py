import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_from_directory,
    abort,
)
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from config import Config
from models import (
    db,
    Student,
    Course,
    Enrollment,
    CourseMaterial,
    Quiz,
    Question,
    QuizAttempt,
    Assignment,
    AssignmentSubmission,
    AssignmentUnlock,
    EmailOutbox,
)
from utils import (
    validate_password,
    generate_temp_password,
    generate_registration_number,
    send_email,
)

app = Flask(__name__)
app.config.from_object(Config)

for folder in (
    app.config["PASSPORT_FOLDER"],
    app.config["MATERIAL_FOLDER"],
    app.config["SUBMISSION_FOLDER"],
):
    os.makedirs(folder, exist_ok=True)

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."


class AdminUser:
    """A single, non-persisted admin account backed by env-var
    credentials (ADMIN_USERNAME / ADMIN_PASSWORD)."""

    is_authenticated = True
    is_active = True
    is_anonymous = False

    def get_id(self):
        return "admin"


@login_manager.user_loader
def load_user(user_id):
    if user_id == "admin":
        return AdminUser()
    if user_id.startswith("student:"):
        return Student.query.get(int(user_id.split(":", 1)[1]))
    return None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or current_user.get_id() != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def student_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not isinstance(
            current_user, Student
        ):
            flash("Please log in as a student.", "danger")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png"}
ALLOWED_DOC_EXT = {"pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "zip", "txt", "jpg", "jpeg", "png"}


def _ext_ok(filename, allowed):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


# ---------------------------------------------------------------- welcome --
@app.route("/")
def welcome():
    students = Student.query.order_by(Student.created_at.desc()).limit(8).all()
    courses = Course.query.all()
    return render_template("welcome.html", students=students, courses=courses)


# ------------------------------------------------------------------ login --
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if username == app.config["ADMIN_USERNAME"]:
            if password == app.config["ADMIN_PASSWORD"]:
                login_user(AdminUser())
                return redirect(url_for("admin_dashboard"))
            flash("Incorrect admin password.", "danger")
            return redirect(url_for("login"))

        student = Student.query.filter_by(username=username).first()
        if student and check_password_hash(student.password_hash, password):
            login_user(student)
            if student.must_change_password:
                flash("You're using a temporary password — please change it now.", "warning")
                return redirect(url_for("change_password"))
            return redirect(url_for("student_dashboard"))

        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("welcome"))


# --------------------------------------------------------- registration ---
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone_number = request.form.get("phone_number", "").strip()
        whatsapp_number = request.form.get("whatsapp_number", "").strip()
        state = request.form.get("state", "").strip()
        lga = request.form.get("lga", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        passport = request.files.get("passport")

        errors = []
        if not all([full_name, email, phone_number, whatsapp_number, state, lga, username, password]):
            errors.append("Please fill in every field.")
        if Student.query.filter_by(email=email).first():
            errors.append("That email is already registered.")
        if Student.query.filter_by(username=username).first():
            errors.append("That username is taken — choose another.")
        pwd_error = validate_password(password)
        if pwd_error:
            errors.append(pwd_error)
        if not passport or passport.filename == "":
            errors.append("A passport photograph is required.")
        elif not _ext_ok(passport.filename, ALLOWED_IMAGE_EXT):
            errors.append("Passport photo must be a JPG or PNG image.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("register.html", form=request.form)

        reg_number = generate_registration_number()
        filename = secure_filename(f"{reg_number.replace('/', '-')}_{passport.filename}")
        passport.save(os.path.join(app.config["PASSPORT_FOLDER"], filename))

        student = Student(
            registration_number=reg_number,
            full_name=full_name,
            email=email,
            phone_number=phone_number,
            whatsapp_number=whatsapp_number,
            state=state,
            lga=lga,
            username=username,
            password_hash=generate_password_hash(password),
            passport_filename=filename,
        )
        db.session.add(student)
        db.session.commit()

        flash(
            f"Registration successful! Your registration number is {reg_number}. "
            "You can now log in.",
            "success",
        )
        return redirect(url_for("login"))

    return render_template("register.html", form={})


# ----------------------------------------------------------- forgot pwd ---
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        student = Student.query.filter_by(email=email).first()
        if student:
            temp_password = generate_temp_password()
            student.password_hash = generate_password_hash(temp_password)
            student.must_change_password = True
            db.session.commit()
            send_email(
                to_email=student.email,
                subject="WASKO Virtual Academy — Password Reset",
                body=(
                    f"Hello {student.full_name},\n\n"
                    f"Your temporary password is: {temp_password}\n"
                    f"Username: {student.username}\n\n"
                    "Please log in and change this password immediately.\n\n"
                    "WASKO Virtual Academy & Cyber Cafe, Sokoto State."
                ),
            )
        # Same message either way so we don't reveal which emails are registered.
        flash(
            "If that email is registered, a temporary password has been sent to it.",
            "info",
        )
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/change-password", methods=["GET", "POST"])
@student_required
def change_password():
    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        error = validate_password(new_password)
        if error:
            flash(error, "danger")
        elif new_password != confirm:
            flash("Passwords do not match.", "danger")
        else:
            current_user.password_hash = generate_password_hash(new_password)
            current_user.must_change_password = False
            db.session.commit()
            flash("Password updated.", "success")
            return redirect(url_for("student_dashboard"))
    return render_template("student/change_password.html")


# ------------------------------------------------------- student portal ---
@app.route("/dashboard")
@student_required
def student_dashboard():
    return render_template("student/dashboard.html", student=current_user)


@app.route("/courses")
@student_required
def course_catalog():
    courses = Course.query.all()
    my_enrollments = {e.course_id: e for e in current_user.enrollments}
    return render_template(
        "student/courses.html", courses=courses, my_enrollments=my_enrollments
    )


@app.route("/courses/<int:course_id>/enroll", methods=["POST"])
@student_required
def enroll_course(course_id):
    course = Course.query.get_or_404(course_id)
    existing = Enrollment.query.filter_by(
        student_id=current_user.id, course_id=course.id
    ).first()
    if existing:
        flash("You have already requested this course.", "info")
    else:
        db.session.add(Enrollment(student_id=current_user.id, course_id=course.id))
        db.session.commit()
        flash(
            f"Course registration submitted for '{course.title}'. It will stay "
            f"pending until your NGN{Config.COURSE_FEE:,} payment is confirmed by "
            "the admin.",
            "success",
        )
    return redirect(url_for("course_catalog"))


@app.route("/courses/<int:course_id>")
@student_required
def course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    enrollment = Enrollment.query.filter_by(
        student_id=current_user.id, course_id=course.id
    ).first()
    if not enrollment or enrollment.status != "active":
        flash("Your access to this course is pending payment confirmation.", "warning")
        return redirect(url_for("course_catalog"))

    my_submissions = {
        s.assignment_id: s
        for s in current_user.submissions
        if s.assignment.course_id == course.id
    }
    my_attempts = {
        a.quiz_id: a for a in current_user.quiz_attempts if a.quiz.course_id == course.id
    }
    return render_template(
        "student/course_detail.html",
        course=course,
        my_submissions=my_submissions,
        my_attempts=my_attempts,
        now=datetime.utcnow(),
    )


@app.route("/materials/<int:material_id>/download")
@student_required
def download_material(material_id):
    material = CourseMaterial.query.get_or_404(material_id)
    enrollment = Enrollment.query.filter_by(
        student_id=current_user.id, course_id=material.course_id, status="active"
    ).first()
    if not enrollment:
        abort(403)
    return send_from_directory(
        app.config["MATERIAL_FOLDER"], material.filename, as_attachment=True
    )


@app.route("/assignments/<int:assignment_id>/download")
@student_required
def download_assignment_file(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    if not assignment.filename:
        abort(404)
    enrollment = Enrollment.query.filter_by(
        student_id=current_user.id, course_id=assignment.course_id, status="active"
    ).first()
    if not enrollment:
        abort(403)
    return send_from_directory(
        app.config["MATERIAL_FOLDER"], assignment.filename, as_attachment=True
    )


@app.route("/quizzes/<int:quiz_id>", methods=["GET", "POST"])
@student_required
def take_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    enrollment = Enrollment.query.filter_by(
        student_id=current_user.id, course_id=quiz.course_id, status="active"
    ).first()
    if not enrollment:
        abort(403)

    if request.method == "POST":
        score = 0
        for q in quiz.questions:
            chosen = request.form.get(f"q{q.id}")
            if chosen and chosen.upper() == q.correct_option:
                score += 1
        attempt = QuizAttempt(
            quiz_id=quiz.id, student_id=current_user.id, score=score, total=len(quiz.questions)
        )
        db.session.add(attempt)
        db.session.commit()
        return render_template("student/quiz_result.html", quiz=quiz, attempt=attempt)

    return render_template("student/quiz.html", quiz=quiz)


@app.route("/assignments/<int:assignment_id>/submit", methods=["POST"])
@student_required
def submit_assignment(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    enrollment = Enrollment.query.filter_by(
        student_id=current_user.id, course_id=assignment.course_id, status="active"
    ).first()
    if not enrollment:
        abort(403)

    if assignment.is_locked_for(current_user.id):
        flash(
            f"The 48-hour window has closed. Pay NGN{Config.ASSIGNMENT_LATE_FEE:,} to "
            f"{Config.BANK_NAME}, Acct {Config.BANK_ACCOUNT_NUMBER} "
            f"({Config.BANK_ACCOUNT_NAME}), then email proof of payment with your "
            f"registration number to {Config.LATE_FEE_EVIDENCE_EMAIL} to get unlocked.",
            "danger",
        )
        return redirect(url_for("course_detail", course_id=assignment.course_id))

    file = request.files.get("submission_file")
    if not file or file.filename == "":
        flash("Please attach a file to submit.", "danger")
        return redirect(url_for("course_detail", course_id=assignment.course_id))
    if not _ext_ok(file.filename, ALLOWED_DOC_EXT):
        flash("Unsupported file type.", "danger")
        return redirect(url_for("course_detail", course_id=assignment.course_id))

    filename = secure_filename(
        f"{current_user.registration_number.replace('/', '-')}_{assignment.id}_{file.filename}"
    )
    file.save(os.path.join(app.config["SUBMISSION_FOLDER"], filename))

    existing = AssignmentSubmission.query.filter_by(
        assignment_id=assignment.id, student_id=current_user.id
    ).first()
    if existing:
        existing.filename = filename
        existing.submitted_at = datetime.utcnow()
    else:
        db.session.add(
            AssignmentSubmission(
                assignment_id=assignment.id,
                student_id=current_user.id,
                filename=filename,
            )
        )
    db.session.commit()
    flash("Assignment submitted successfully.", "success")
    return redirect(url_for("course_detail", course_id=assignment.course_id))


# ---------------------------------------------------------- admin portal --
@app.route("/admin")
@admin_required
def admin_dashboard():
    stats = {
        "students": Student.query.count(),
        "courses": Course.query.count(),
        "pending_payments": Enrollment.query.filter_by(status="pending").count(),
        "locked_assignments": sum(
            1
            for a in Assignment.query.all()
            for s in Student.query.all()
            if Enrollment.query.filter_by(
                student_id=s.id, course_id=a.course_id, status="active"
            ).first()
            and a.is_locked_for(s.id)
        ),
    }
    return render_template("admin/dashboard.html", stats=stats)


@app.route("/admin/students")
@admin_required
def admin_students():
    students = Student.query.order_by(Student.created_at.desc()).all()
    return render_template("admin/students.html", students=students)


@app.route("/admin/students/<int:student_id>/delete", methods=["POST"])
@admin_required
def admin_delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    db.session.delete(student)
    db.session.commit()
    flash(f"Deleted student {student.full_name}.", "success")
    return redirect(url_for("admin_students"))


@app.route("/admin/students/<int:student_id>/reg-number", methods=["POST"])
@admin_required
def admin_edit_reg_number(student_id):
    student = Student.query.get_or_404(student_id)
    new_number = request.form.get("registration_number", "").strip()
    if new_number:
        student.registration_number = new_number
        db.session.commit()
        flash("Registration number updated.", "success")
    return redirect(url_for("admin_students"))


@app.route("/admin/courses", methods=["GET", "POST"])
@admin_required
def admin_courses():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        if title:
            db.session.add(Course(title=title, description=description))
            db.session.commit()
            flash("Course created.", "success")
        return redirect(url_for("admin_courses"))
    courses = Course.query.all()
    return render_template("admin/courses.html", courses=courses)


@app.route("/admin/payments")
@admin_required
def admin_payments():
    pending = Enrollment.query.filter_by(status="pending").all()
    active = Enrollment.query.filter_by(status="active").order_by(
        Enrollment.confirmed_at.desc()
    ).limit(20).all()
    return render_template("admin/payments.html", pending=pending, active=active)


@app.route("/admin/payments/<int:enrollment_id>/confirm", methods=["POST"])
@admin_required
def admin_confirm_payment(enrollment_id):
    enrollment = Enrollment.query.get_or_404(enrollment_id)
    enrollment.status = "active"
    enrollment.confirmed_at = datetime.utcnow()
    db.session.commit()
    flash(
        f"Payment confirmed — {enrollment.student.full_name} now has access to "
        f"'{enrollment.course.title}'.",
        "success",
    )
    return redirect(url_for("admin_payments"))


@app.route("/admin/materials", methods=["GET", "POST"])
@admin_required
def admin_materials():
    courses = Course.query.all()
    if request.method == "POST":
        course_id = request.form.get("course_id")
        title = request.form.get("title", "").strip()
        file = request.files.get("material_file")
        if not course_id or not title or not file or file.filename == "":
            flash("Course, title and file are all required.", "danger")
        elif not _ext_ok(file.filename, ALLOWED_DOC_EXT):
            flash("Unsupported file type.", "danger")
        else:
            filename = secure_filename(f"{course_id}_{datetime.utcnow().timestamp()}_{file.filename}")
            file.save(os.path.join(app.config["MATERIAL_FOLDER"], filename))
            db.session.add(
                CourseMaterial(course_id=course_id, title=title, filename=filename)
            )
            db.session.commit()
            flash("Material uploaded.", "success")
        return redirect(url_for("admin_materials"))
    materials = CourseMaterial.query.order_by(CourseMaterial.uploaded_at.desc()).all()
    return render_template("admin/materials.html", courses=courses, materials=materials)


@app.route("/admin/materials/<int:material_id>/delete", methods=["POST"])
@admin_required
def admin_delete_material(material_id):
    material = CourseMaterial.query.get_or_404(material_id)
    db.session.delete(material)
    db.session.commit()
    flash("Material removed.", "success")
    return redirect(url_for("admin_materials"))


@app.route("/admin/quizzes", methods=["GET", "POST"])
@admin_required
def admin_quizzes():
    courses = Course.query.all()
    if request.method == "POST":
        course_id = request.form.get("course_id")
        title = request.form.get("title", "").strip()
        is_exam = request.form.get("is_exam") == "on"
        if course_id and title:
            quiz = Quiz(course_id=course_id, title=title, is_exam=is_exam)
            db.session.add(quiz)
            db.session.commit()
            flash("Quiz/exam created — now add its questions.", "success")
            return redirect(url_for("admin_quiz_detail", quiz_id=quiz.id))
        flash("Course and title are required.", "danger")
        return redirect(url_for("admin_quizzes"))
    quizzes = Quiz.query.order_by(Quiz.created_at.desc()).all()
    return render_template("admin/quizzes.html", courses=courses, quizzes=quizzes)


@app.route("/admin/quizzes/<int:quiz_id>", methods=["GET", "POST"])
@admin_required
def admin_quiz_detail(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        a = request.form.get("option_a", "").strip()
        b = request.form.get("option_b", "").strip()
        c = request.form.get("option_c", "").strip()
        d = request.form.get("option_d", "").strip()
        correct = request.form.get("correct_option", "").strip().upper()
        if all([text, a, b, c, d]) and correct in {"A", "B", "C", "D"}:
            db.session.add(
                Question(
                    quiz_id=quiz.id,
                    text=text,
                    option_a=a,
                    option_b=b,
                    option_c=c,
                    option_d=d,
                    correct_option=correct,
                )
            )
            db.session.commit()
            flash("Question added.", "success")
        else:
            flash("Please fill in the question, all four options, and pick the correct one.", "danger")
        return redirect(url_for("admin_quiz_detail", quiz_id=quiz.id))
    return render_template("admin/quiz_detail.html", quiz=quiz)


@app.route("/admin/assignments", methods=["GET", "POST"])
@admin_required
def admin_assignments():
    courses = Course.query.all()
    if request.method == "POST":
        course_id = request.form.get("course_id")
        title = request.form.get("title", "").strip()
        instructions = request.form.get("instructions", "").strip()
        file = request.files.get("assignment_file")
        filename = None
        if file and file.filename:
            if not _ext_ok(file.filename, ALLOWED_DOC_EXT):
                flash("Unsupported file type.", "danger")
                return redirect(url_for("admin_assignments"))
            filename = secure_filename(f"{course_id}_{datetime.utcnow().timestamp()}_{file.filename}")
            file.save(os.path.join(app.config["MATERIAL_FOLDER"], filename))
        if course_id and title:
            db.session.add(
                Assignment(
                    course_id=course_id,
                    title=title,
                    instructions=instructions,
                    filename=filename,
                    window_hours=app.config["ASSIGNMENT_WINDOW_HOURS"],
                )
            )
            db.session.commit()
            flash(
                f"Assignment posted — students have {app.config['ASSIGNMENT_WINDOW_HOURS']} hours to submit.",
                "success",
            )
        return redirect(url_for("admin_assignments"))
    assignments = Assignment.query.order_by(Assignment.created_at.desc()).all()
    now = datetime.utcnow()
    return render_template(
        "admin/assignments.html", courses=courses, assignments=assignments, now=now
    )


@app.route("/admin/assignments/<int:assignment_id>")
@admin_required
def admin_assignment_detail(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    enrollments = Enrollment.query.filter_by(
        course_id=assignment.course_id, status="active"
    ).all()
    submitted_ids = {s.student_id for s in assignment.submissions}
    rows = []
    for e in enrollments:
        rows.append(
            {
                "student": e.student,
                "submitted": e.student_id in submitted_ids,
                "locked": assignment.is_locked_for(e.student_id),
            }
        )
    return render_template(
        "admin/assignment_detail.html",
        assignment=assignment,
        rows=rows,
        now=datetime.utcnow(),
    )


@app.route(
    "/admin/assignments/<int:assignment_id>/unlock/<int:student_id>", methods=["POST"]
)
@admin_required
def admin_unlock_assignment(assignment_id, student_id):
    unlock = AssignmentUnlock.query.filter_by(
        assignment_id=assignment_id, student_id=student_id
    ).first()
    if unlock:
        unlock.unlocked = True
        unlock.unlocked_at = datetime.utcnow()
    else:
        db.session.add(
            AssignmentUnlock(assignment_id=assignment_id, student_id=student_id)
        )
    db.session.commit()
    flash("Submission window re-opened for this student.", "success")
    return redirect(url_for("admin_assignment_detail", assignment_id=assignment_id))


@app.route("/admin/email-outbox")
@admin_required
def admin_email_outbox():
    emails = EmailOutbox.query.order_by(EmailOutbox.created_at.desc()).limit(100).all()
    return render_template("admin/email_outbox.html", emails=emails)


@app.route("/admin/submissions/<filename>")
@admin_required
def admin_download_submission(filename):
    return send_from_directory(
        app.config["SUBMISSION_FOLDER"], filename, as_attachment=True
    )


@app.route("/admin/materials-file/<filename>")
@admin_required
def admin_download_material_file(filename):
    return send_from_directory(
        app.config["MATERIAL_FOLDER"], filename, as_attachment=True
    )


# --------------------------------------------------------------- errors ---
@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, message="Access denied."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Page not found."), 404


# ------------------------------------------------------------- CLI/init ---
@app.cli.command("init-db")
def init_db():
    """Creates all tables. Run with: flask --app app init-db"""
    db.create_all()
    print("Database tables created.")


@app.cli.command("seed-demo")
def seed_demo():
    """Adds a couple of sample courses so there's something to click on.
    Run with: flask --app app seed-demo"""
    if Course.query.count() == 0:
        db.session.add_all(
            [
                Course(title="Computer Basics", description="Typing, MS Office, internet basics."),
                Course(title="Web Design (HTML/CSS)", description="Build and publish real web pages."),
                Course(title="Graphics Design", description="CorelDRAW & Photoshop for beginners."),
            ]
        )
        db.session.commit()
        print("Seeded 3 demo courses.")
    else:
        print("Courses already exist — nothing to seed.")


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)
