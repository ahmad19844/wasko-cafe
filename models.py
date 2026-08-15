from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class Student(UserMixin, db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    registration_number = db.Column(db.String(30), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone_number = db.Column(db.String(30), nullable=False)
    whatsapp_number = db.Column(db.String(30), nullable=False)
    state = db.Column(db.String(80), nullable=False)
    lga = db.Column(db.String(80), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    passport_filename = db.Column(db.String(255))
    must_change_password = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    enrollments = db.relationship(
        "Enrollment", backref="student", cascade="all, delete-orphan"
    )
    submissions = db.relationship(
        "AssignmentSubmission", backref="student", cascade="all, delete-orphan"
    )
    quiz_attempts = db.relationship(
        "QuizAttempt", backref="student", cascade="all, delete-orphan"
    )

    def get_id(self):
        # Prefixed so the Flask-Login user_loader can tell a student apart
        # from the single admin account.
        return f"student:{self.id}"


class Course(db.Model):
    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    materials = db.relationship(
        "CourseMaterial", backref="course", cascade="all, delete-orphan"
    )
    quizzes = db.relationship("Quiz", backref="course", cascade="all, delete-orphan")
    assignments = db.relationship(
        "Assignment", backref="course", cascade="all, delete-orphan"
    )
    enrollments = db.relationship(
        "Enrollment", backref="course", cascade="all, delete-orphan"
    )


class Enrollment(db.Model):
    """A student's registration onto a course, gated behind admin payment
    confirmation of the NGN10,000 course fee."""

    __tablename__ = "enrollments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending / active
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    confirmed_at = db.Column(db.DateTime)

    __table_args__ = (
        db.UniqueConstraint("student_id", "course_id", name="uq_student_course"),
    )


class CourseMaterial(db.Model):
    __tablename__ = "course_materials"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


class Quiz(db.Model):
    __tablename__ = "quizzes"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    is_exam = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    questions = db.relationship(
        "Question", backref="quiz", cascade="all, delete-orphan"
    )
    attempts = db.relationship(
        "QuizAttempt", backref="quiz", cascade="all, delete-orphan"
    )


class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(255), nullable=False)
    option_b = db.Column(db.String(255), nullable=False)
    option_c = db.Column(db.String(255), nullable=False)
    option_d = db.Column(db.String(255), nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)  # A/B/C/D


class QuizAttempt(db.Model):
    __tablename__ = "quiz_attempts"

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Integer, nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)


class Assignment(db.Model):
    __tablename__ = "assignments"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    instructions = db.Column(db.Text)
    filename = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    window_hours = db.Column(db.Integer, default=48)

    submissions = db.relationship(
        "AssignmentSubmission", backref="assignment", cascade="all, delete-orphan"
    )
    unlocks = db.relationship(
        "AssignmentUnlock", backref="assignment", cascade="all, delete-orphan"
    )

    @property
    def deadline(self):
        return self.created_at + timedelta(hours=self.window_hours)

    def is_locked_for(self, student_id):
        """Locked once the 48-hour window has passed, unless the student has
        already submitted or an admin has explicitly unlocked it after the
        NGN1,000 late fee evidence was verified."""
        already_submitted = any(
            s.student_id == student_id for s in self.submissions
        )
        if already_submitted:
            return False
        if datetime.utcnow() <= self.deadline:
            return False
        unlocked = any(
            u.student_id == student_id and u.unlocked for u in self.unlocks
        )
        return not unlocked


class AssignmentSubmission(db.Model):
    __tablename__ = "assignment_submissions"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(
        db.Integer, db.ForeignKey("assignments.id"), nullable=False
    )
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)


class AssignmentUnlock(db.Model):
    """Created when a student's late-fee payment evidence has been
    verified by the admin, re-opening the submit button for that student."""

    __tablename__ = "assignment_unlocks"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(
        db.Integer, db.ForeignKey("assignments.id"), nullable=False
    )
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    unlocked = db.Column(db.Boolean, default=True)
    unlocked_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Student")

    __table_args__ = (
        db.UniqueConstraint(
            "assignment_id", "student_id", name="uq_assignment_student_unlock"
        ),
    )


class EmailOutbox(db.Model):
    """Every 'sent' email is logged here. If real SMTP credentials aren't
    configured (e.g. during local testing) this is the only place the
    password-reset email will show up — see the admin dashboard's
    'Email Outbox' link."""

    __tablename__ = "email_outbox"

    id = db.Column(db.Integer, primary_key=True)
    to_email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    sent_via_smtp = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
