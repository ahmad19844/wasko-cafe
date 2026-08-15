# WASKO Virtual Academy & Cyber Cafe — Web Platform

A student-registration, course-delivery and quiz/assignment portal for WASKO
Virtual Academy & Cyber Cafe, Sokoto State — built with **Flask +
SQLAlchemy + Flask-Login**, ready to deploy on **Render.com**.

## What's included

- Public welcome page (student photo wall + course list)
- Student self-registration (name, email, phone, WhatsApp, state/LGA,
  username, 12-character password, passport photo) → auto-issued unique
  registration number (e.g. `WASKO/2026/0001`)
- Shared login page for the single admin account and all students
- "Forgot password" → emails (or logs, see below) a temporary password
- Student dashboard: photo + name always shown, course catalog, course
  registration that stays **pending** until the admin confirms the
  NGN10,000 bank payment
- Course dashboard: downloadable materials, quizzes/exams, assignments
- Assignments open for **48 hours** from posting; after that the submit
  button **locks** until the admin unlocks it (once the student has paid
  the NGN1,000 late fee and emailed proof to `amy33375@gmail.com`)
- Admin dashboard: view/delete students, confirm course payments, upload
  materials, create quizzes/exams with auto-graded multiple choice
  questions, post assignments, unlock late submissions per student

## Stack & why

| Piece | Choice | Why |
|---|---|---|
| Backend | Flask | Small enough to read in one sitting, huge ecosystem |
| DB (dev) | SQLite | Zero setup |
| DB (prod) | PostgreSQL | Render's free Postgres add-on — the app auto-switches via `DATABASE_URL` |
| Auth | Flask-Login | One session mechanism for both the admin account and students |
| Files | Local disk | Simplest for a prototype — see **Known limitation** below |
| Deploy | Render (`render.yaml`) | You asked for Render specifically |

## Run it locally

```bash
cd wasko
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

flask --app app init-db         # creates the tables (app.db)
flask --app app seed-demo       # optional: adds 3 sample courses

python app.py                   # starts on http://127.0.0.1:5000
```

Log in as admin with **username `admin`, password `Admin@1984`** (change
`ADMIN_PASSWORD` before you deploy for real). Open a second browser (or
incognito window) and register as a student to try the student side.

Because no SMTP server is configured by default, "forgot password" emails
are written to **Admin → Email Outbox** instead of actually being sent —
that's where you'll find the temporary password while testing.

## Deploy to Render.com

1. Push this folder to a GitHub repo.
2. In Render: **New → Blueprint**, point it at the repo. Render reads
   `render.yaml` and provisions the web service **and** a free Postgres
   database automatically, wiring `DATABASE_URL` for you.
3. Once it's live, open a Render **Shell** on the service and run:
   ```bash
   flask --app app init-db
   flask --app app seed-demo
   ```
   (or just let the app boot once — `db.create_all()` also runs
   automatically on startup in `app.py`).
4. In the service's **Environment** tab, set `ADMIN_PASSWORD` to something
   only you know, and fill in `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD`
   if you want real password-reset emails (e.g. a Gmail app password, or
   SendGrid/Mailgun SMTP credentials).
5. Done — Render gives you a `https://<your-service>.onrender.com` URL.

## ⚠️ Known limitation you should plan around

**Render's free/standard web service disk is ephemeral** — every deploy
or restart wipes locally-saved files. That's fine for the database
(Postgres lives separately), but passport photos, course materials, and
assignment submissions are currently saved to local disk and **will be
lost on redeploy**. For a real launch, the first thing to change is
swapping local file storage for:
- Render's **persistent disk** add-on (simplest — just mounts a volume), or
- **Cloudinary** (great for passport photos) / **AWS S3** or
  **Backblaze B2** (great for documents) via a small storage helper in
  `utils.py`.

## What I'd extend next, in order

1. **Move file storage off local disk** (see above) — highest priority,
   everything else is cosmetic by comparison.
2. **Automated payment verification** — right now, both the NGN10,000
   course fee and the NGN1,000 late fee rely on the admin manually
   checking their bank alert and clicking "confirm"/"unlock". A Paystack
   or Flutterwave integration (both are popular with Nigerian banks,
   support NGN natively, and have simple REST APIs) would let the
   platform confirm payments automatically and instantly.
3. **Real transactional email** — plug in SendGrid/Mailgun/Postmark so
   forgot-password and "your course was approved" emails actually land in
   inboxes, not just the Email Outbox page.
4. **Per-course quiz/exam time limits and one-attempt locking** — right
   now a student can retake a quiz as many times as they like; add a
   `max_attempts` and a countdown timer for real exam conditions.
5. **Admin ability to grade assignments in-app** (currently they can only
   download submissions) — add a grade/feedback field on
   `AssignmentSubmission`.
6. **Bulk actions & search** on the students table once you have more than
   a page's worth of registrants.
7. **Rate-limit `/forgot-password` and `/login`** (e.g. Flask-Limiter) so
   the app isn't easy to brute-force or spam once it's public.
8. **Add CSRF protection** (Flask-WTF) to every form — this prototype
   skips it for simplicity, but it's a must before going live.

## Project layout

```
wasko/
├── app.py              # routes
├── models.py            # SQLAlchemy models
├── config.py             # env-driven settings (bank details, fees, folders)
├── utils.py               # password rules, temp-password + reg-number generation, email
├── requirements.txt
├── render.yaml            # Render blueprint (web service + Postgres)
├── Procfile
├── templates/
│   ├── base.html, welcome.html, login.html, register.html, forgot_password.html
│   ├── student/          # dashboard, courses, course_detail, quiz, quiz_result, change_password
│   └── admin/             # dashboard, students, courses, payments, materials, quizzes, assignments
└── static/
    ├── css/style.css
    ├── img/founder.jpg    # from your upload — shown on the welcome page
    └── uploads/passports/ # student passport photos (publicly shown by design)
```
