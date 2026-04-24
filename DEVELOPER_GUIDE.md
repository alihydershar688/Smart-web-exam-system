# Smart Exam System — Complete Developer Guide

> **Final Year Project (FYP)** — AI-powered university exam platform
> Last Updated: April 2026

---

## 1. WHAT THIS PROJECT DOES

Smart Exam System is a full-stack web application that automates the entire university exam lifecycle using AI. Three user roles, each with a dedicated workflow:

### Admin
- Creates and manages user accounts (teachers, students)
- Approves or rejects new registration requests
- Creates courses and assigns teachers
- Enrolls students into courses
- Views platform-wide analytics and activity

### Teacher
- Uploads course material (PDF, PPTX, DOCX)
- AI generates exam questions automatically from uploaded material
- Reviews and edits generated questions in the Question Editor
- Previews the final exam paper in academic format
- Publishes exams to enrolled students
- Views student submissions and grades them (manual or AI auto-grade)
- Checks for plagiarism across submissions

### Student
- Sees only exams from courses they are enrolled in
- Takes timed exams with a live countdown timer
- Submits answers (MCQ auto-graded, subjective sent for AI/teacher grading)
- Views results and feedback after teacher finalizes

---

## 2. TECH STACK

| Layer | Technology |
|---|---|
| Frontend | Static HTML + Vanilla JS + CSS |
| Backend | Python Flask (port 5000) |
| Database | Supabase (PostgreSQL) |
| Auth | Supabase Auth (JWT) |
| AI — Question Generation | Ollama (llama3.2:3b-instruct-q5_K_M) |
| AI — Essay Grading | Sentence-BERT (all-mpnet-base-v2) |
| AI — Code Understanding | CodeBERT (microsoft/codebert-base) |
| AI — Subject Detection | DistilBERT classifier (fine-tuned) |
| AI — Chatbot | Grok (xAI API) + Ollama fallback |
| File Serving | npx serve (port 5500) |

---

## 3. PROJECT STRUCTURE

```
Smart web exam system/
│
├── backend/
│   ├── app.py                      # Main Flask app — all API routes
│   ├── .env                        # Backend environment variables
│   ├── requirements.txt            # Python dependencies
│   ├── pdf_export.py               # PDF generation for exam results
│   ├── uploads/                    # Uploaded PDF/PPTX/DOCX files
│   ├── models/
│   │   ├── question_generator.py   # Core question generation logic
│   │   ├── model_access.py         # Ollama API communication layer
│   │   ├── essay_grader.py         # Sentence-BERT essay grading
│   │   └── topic_extractor.py      # Subject/topic detection
│   └── utils/
│       ├── supabase_client.py      # Supabase DB connection
│       ├── rbac.py                 # Role-based access control
│       ├── exam_operations.py      # Exam CRUD blueprint
│       ├── pdf_processor.py        # PDF/PPTX/DOCX text extraction
│       ├── session_lock.py         # Single-device session enforcement
│       ├── admin_control.py        # Admin authorization logic
│       └── email_notify.py         # SMTP email notifications
│
├── frontend/
│   ├── index.html                  # Landing page
│   ├── login.html                  # Login page
│   ├── signup.html                 # Registration page
│   ├── dashboard-admin.html        # Admin dashboard
│   ├── dashboard-teacher.html      # Teacher dashboard
│   ├── dashboard-student.html      # Student dashboard
│   ├── create-exam.html            # Exam creation + file upload
│   ├── question-editor.html        # Edit generated questions
│   ├── exam-preview.html           # Preview + publish exam
│   ├── take-exam.html              # Student exam taking interface
│   ├── exam-results.html           # Results viewer
│   ├── manage-users.html           # Admin user management
│   ├── analytics.html              # Analytics dashboard
│   ├── js/
│   │   ├── app-config.js           # Supabase config + auth headers
│   │   ├── session-manager.js      # Session timeout + lock logic
│   │   ├── chatbot.js              # Grok AI chatbot widget
│   │   ├── supabase.min.js         # Supabase JS library (local copy)
│   │   └── ...other JS modules
│   └── css/
│       ├── ui-system.css           # Global design system
│       ├── dashboard-shell.css     # Dashboard layout
│       └── ...other stylesheets
│
├── datasets/                       # AI training datasets
├── .venv/                          # Python virtual environment
├── .env                            # Root environment variables
├── DATABASE_SCHEMA.sql             # SQL schema patches
├── DEVELOPER_GUIDE.md              # This file — complete guide
└── MODEL_SPECIFICATIONS.md         # AI model training details
```

---

## 4. AI MODELS — WHAT EACH ONE DOES

### 4.1 Ollama — Question Generation (PRIMARY)
- **Model:** `llama3.2:3b-instruct-q5_K_M`
- **Runs on:** Local machine via Ollama at `http://localhost:11434`
- **What it does:** Generates MCQ, Short Answer, and Long Answer questions from uploaded course material. Each question draws from a different section of the document so questions vary across the paper.
- **Settings:** temperature 0.85, top_p 0.92, repeat_penalty 1.15
- **Calls per run:** 8 on CPU, 12 on GPU (configurable)
- **File:** `backend/models/model_access.py`

### 4.2 CodeBERT — Code Understanding
- **Model:** `microsoft/codebert-base` (335 MB)
- **Runs on:** CPU/GPU via HuggingFace Transformers
- **What it does:** When uploaded material contains code, CodeBERT extracts function names, class names, and variables to enrich question generation context. Ensures code-specific questions reference actual functions from the material.
- **File:** `backend/models/question_generator.py` → `analyze_code_with_codebert()`

### 4.3 Sentence-BERT — Essay Grading
- **Model:** `sentence-transformers/all-mpnet-base-v2` (438 MB)
- **Runs on:** CPU
- **What it does:** Grades subjective answers by computing semantic similarity between student answer and model answer. Score = similarity × max_marks. If similarity ≥ `AI_CONFIDENCE_THRESHOLD` (0.65) → auto-graded. Below threshold → teacher review.
- **Rubric:**
  - 0.80–1.00 → 90–100% (Excellent)
  - 0.65–0.79 → 75–89% (Good)
  - 0.50–0.64 → 60–74% (Satisfactory)
  - 0.30–0.49 → 40–59% (Needs Improvement)
  - < 0.30 → < 40% (Insufficient)
- **File:** `backend/models/essay_grader.py`

### 4.4 DistilBERT — Subject Detection
- **Model:** Fine-tuned DistilBERT classifier (local: `models/subject_classifier`)
- **Runs on:** CPU
- **What it does:** Reads extracted PDF text and classifies the subject (database, python, OOP, web, software engineering). Determines question style and vocabulary for generation.
- **Fallback:** Keyword matching if local model not found
- **File:** `backend/models/topic_extractor.py`

### 4.5 Grok (xAI) — AI Chatbot
- **Model:** Grok via xAI API
- **Runs on:** Remote (xAI cloud)
- **Fallback:** Ollama (local) if xAI API unavailable or no credits
- **What it does:** Powers the floating chat assistant on all dashboards. Role-aware responses for students (study help), teachers (exam design), admins (system help).
- **File:** `frontend/js/chatbot.js` + `backend/app.py` → `/api/chatbot`

### 4.6 HuggingFace Space (Optional Remote GPU)
- **URL:** `https://ali-hyder2019-smart-exam-question-gen.hf.space`
- **What it does:** Remote GPU-accelerated question generation. First priority if available. Falls back to local Ollama if space is down.
- **Set in:** `backend/.env` → `HF_SPACE_URL`

---

## 5. SUPPORTED SUBJECTS

| Subject Key | Recognized Course Names |
|---|---|
| `database_fundamentals` | Database, DBMS, SQL, Database Management |
| `python_programming` | Python, Python Basics, Python Programming |
| `object_oriented_programming` | OOP, Object-Oriented, OOP Basics |
| `web_development` | Web Dev, HTML, CSS, JavaScript, Frontend |
| `software_engineering` | SE, Software Engineering, Software Design |
| `general` | Any other course (fallback) |

Subject detection priority:
1. Course name keyword match
2. DistilBERT classifier on uploaded text
3. Keyword scan of extracted text
4. Falls back to `general`

---

## 6. PREREQUISITES

```
Python 3.10 or 3.11 (recommended)
Node.js 18+ and npm
Ollama (https://ollama.com/download)
Git
```

### Install Ollama Model
```bash
ollama pull llama3.2:3b-instruct-q5_K_M
ollama serve
```

---

## 7. FIRST-TIME SETUP

### Step 1 — Create Python virtual environment
```bash
python -m venv .venv
```

### Step 2 — Activate virtual environment

**Windows PowerShell:**
```powershell
.venv\Scripts\Activate.ps1
```

**Mac/Linux:**
```bash
source .venv/bin/activate
```

### Step 3 — Install Python dependencies
```bash
pip install -r backend/requirements.txt
```

### Step 4 — Install frontend server
```bash
npm install -g serve
```

---

## 8. ENVIRONMENT VARIABLES

### backend/.env
```env
SUPABASE_URL=https://uhrqrrksblibtsomntqh.supabase.co
SUPABASE_KEY=<anon key>
SUPABASE_SERVICE_ROLE_KEY=<service role key>

OLLAMA_HOST=http://localhost:11434
USE_QWEN_LORA=true
QWEN_BASE_MODEL=Qwen/Qwen2.5-Coder-1.5B-Instruct
HF_SPACE_URL=https://ali-hyder2019-smart-exam-question-gen.hf.space

AI_CONFIDENCE_THRESHOLD=0.65

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=alihydershar688@gmail.com
SMTP_PASS=<gmail app password>
SMTP_FROM=alihydershar688@gmail.com
APP_URL=http://127.0.0.1:5500

XAI_API_KEY=<xai grok api key>
```

### .env (root)
```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_TIMEOUT=60
OLLAMA_MAX_CALLS_CPU=8
OLLAMA_MAX_CALLS_GPU=12
SUPABASE_URL=https://uhrqrrksblibtsomntqh.supabase.co
SUPABASE_ANON_KEY=<anon key>
```

---

## 9. HOW TO RUN THE PROJECT

### Step 1 — Start Ollama
```bash
ollama serve
```

### Step 2 — Start Backend
```bash
# Windows
cd backend
../.venv/Scripts/python.exe app.py

# Mac/Linux
cd backend
../.venv/bin/python app.py
```

Expected output:
```
✓ Ollama Qwen 2.5 7B is reachable at http://localhost:11434
✓ CodeBERT loaded successfully
 * Running on http://127.0.0.1:5000
```

### Step 3 — Start Frontend
```bash
cd frontend
serve . -l 5500
```

### Step 4 — Open browser
```
http://127.0.0.1:5500/login.html
```

---

## 10. TEST CREDENTIALS

| Role | Email | Password |
|---|---|---|
| Admin | alihydershar688@gmail.com | Mehrozali786? |
| Teacher | maduhyder@gmail.com | Madushar1234? |
| Student | njv00334@njv.edu.pk | Madushar1234? |

---

## 11. USER REGISTRATION & APPROVAL FLOW

### New User Registers
1. Goes to `signup.html` → selects Student or Teacher
2. Fills form → clicks Create Account
3. Backend (`POST /api/auth/register`) creates Supabase auth user + profile with `status: pending`
4. Admin receives email notification: "New registration pending approval"
5. User sees success screen: "Registration submitted — awaiting admin approval"

### Admin Approves/Rejects
1. Admin logs in → yellow banner shows: "X registrations pending approval"
2. Goes to Manage Users → filters by Pending
3. Each pending user shows **Approve** (green) and **Reject** (red) buttons
4. Approve → `status: active` → user gets approval email → can login
5. Reject → `status: rejected` → user gets rejection email

### Login Status Messages
- `pending` → "Your account is pending admin approval"
- `rejected` → "Your registration request was rejected"
- `suspended` → "Your account has been suspended"

---

## 12. COMPLETE WORKFLOW — STEP BY STEP

### Admin Workflow
1. Login → `dashboard-admin.html`
2. Manage Users → approve pending registrations
3. Create courses → assign teachers
4. Enroll students into courses

### Teacher Workflow
1. Login → `dashboard-teacher.html`
2. Click Create Exam → select course
3. Fill exam title, duration, marks, difficulty
4. Upload PDF/PPTX/DOCX material files
5. Set question counts → click Generate Paper (~30–90 seconds)
6. Review in Question Editor → edit text, marks, options
7. Preview → academic paper layout
8. Publish Exam → students can now see it
9. After submissions → grade with AI or manually
10. Finalize → releases results to students

### Student Workflow
1. Login → `dashboard-student.html`
2. See available exams from enrolled courses
3. Click Start Exam → timer begins
4. Answer questions → Submit before timer runs out
5. Wait for teacher to finalize
6. View results and feedback

---

## 13. QUESTION GENERATION — HOW IT WORKS

```
1. Teacher uploads files → POST /api/upload-material
2. pdf_processor.py extracts text from PDF/PPTX/DOCX
3. Subject detected from course name + DistilBERT + keywords
4. Text split into sentences, spread evenly across document
5. For each question slot:
   a. 3-sentence window taken from different part of document
   b. Ollama called with chunk + subject context
   c. Ollama returns JSON: { question, options, correct_option, answer }
   d. If Ollama fails → rule-based builder creates the question
6. Post-processing: deduplication, quality filter, type labeling
7. Saved to exam in Supabase
8. Frontend loads into Question Editor
```

**Question type distribution (default):**
- 60% MCQ (4 options, auto-graded)
- 25% Short Answer (AI + teacher graded)
- 15% Long Answer (AI + teacher graded)

**Generation priority order:**
1. HF Space (remote GPU) — if available
2. Qwen LoRA (GPU only) — if available
3. Ollama local LLM — primary
4. Rule-based fallback — last resort

---

## 14. ESSAY GRADING — HOW IT WORKS

```
1. Student submits short/long answer
2. Teacher clicks "Auto Grade"
3. POST /api/grade-essay called with:
   - student_answer
   - model_answer (reference from question creation)
   - max_marks
4. Sentence-BERT encodes both answers into 768-dim vectors
5. Cosine similarity computed
6. Score = similarity × max_marks
7. If similarity >= 0.65 → auto_graded
8. If similarity < 0.65 → pending teacher review
```

---

## 15. API REFERENCE

All routes prefixed with `/api`. Auth headers required on protected routes.

### Auth Headers
```
Authorization: Bearer <supabase_jwt_token>
X-User-Email: user@example.com
X-User-ID: <uuid>
X-User-Role: student | teacher | admin
```

### Key Endpoints

| Method | Route | Description |
|---|---|---|
| GET | `/api/health` | Backend + model status |
| GET | `/api/models/status` | Detailed AI model status |
| POST | `/api/auth/register` | Register new user (public) |
| POST | `/api/upload-material` | Upload PDF/PPTX/DOCX |
| POST | `/api/generate-questions` | Generate questions from text |
| POST | `/api/grade-essay` | Grade single essay answer |
| POST | `/api/grade-batch` | Grade all subjective answers |
| GET | `/api/exams` | List teacher's exams |
| POST | `/api/exams/create` | Create exam draft |
| GET | `/api/exams/<id>` | Get exam + questions |
| POST | `/api/exams/<id>/publish` | Publish exam |
| POST | `/api/exams/attempts/start` | Start exam attempt |
| POST | `/api/exams/attempts/<id>/submit` | Submit answers |
| GET | `/api/exams/attempts/<id>` | Get attempt + results |
| PUT | `/api/exams/attempts/<id>/marks` | Update manual marks |
| POST | `/api/finalize-attempt` | Finalize (release to student) |
| GET | `/api/teacher/courses` | Teacher's assigned courses |
| GET | `/api/admin/users` | List all users |
| PUT | `/api/admin/users/status` | Approve/reject/suspend user |
| PUT | `/api/admin/teachers/<id>/courses` | Assign courses to teacher |
| POST | `/api/admin/enroll` | Enroll student in course |
| POST | `/api/chatbot` | AI chatbot (Grok/Ollama) |

---

## 16. DATABASE TABLES

| Table | Purpose |
|---|---|
| `users` | All accounts — admin, teacher, student |
| `courses` | Course definitions with teacher assignment |
| `enrollments` | Student ↔ course enrollment |
| `course_enrollments` | Legacy enrollment table (fallback) |
| `exams` | Exam metadata + questions JSON |
| `exam_attempts` | Student attempt records + answers |
| `student_answers` | Per-question answer records with grading |
| `question_bank` | Saved reusable questions |

---

## 17. SUPABASE SETTINGS

### Authentication → Sign In / Providers
| Setting | Value |
|---|---|
| Allow new users to sign up | ON |
| Allow manual linking | OFF |
| Allow anonymous sign-ins | OFF |
| Confirm email | **OFF** |

### Authentication → Sessions
| Setting | Value |
|---|---|
| Detect and revoke compromised tokens | ON |
| Refresh token reuse interval | 10 seconds |
| Enforce single session per user | OFF |
| Time-box user sessions | 0 (never) |

### Authentication → URL Configuration
- Site URL: `http://127.0.0.1:5500`
- Redirect URLs: `http://127.0.0.1:5500`, `http://127.0.0.1:5500/`, `http://localhost:5500`, `http://localhost:5500/`

### Authentication → SMTP Settings
| Setting | Value |
|---|---|
| Enable custom SMTP | ON |
| Sender email | alihydershar688@gmail.com |
| Sender name | Smart Exam System |
| Host | smtp.gmail.com |
| Port | 587 |
| Username | alihydershar688@gmail.com |
| Password | Gmail App Password (16 chars) |

---

## 18. EMAIL NOTIFICATIONS

Emails are sent by the Flask backend via Gmail SMTP for:
- New registration → admin notified
- Account approved → user notified
- Account rejected → user notified
- Account suspended → user notified

SMTP is configured in `backend/.env`. Gmail App Password required (not regular password). Generate at: `myaccount.google.com/apppasswords`

---

## 19. SESSION MANAGEMENT

Session timeout is currently **disabled for testing**. To re-enable:

In `frontend/js/session-manager.js`:
```javascript
const TESTING_MODE_DISABLE_TIMEOUT = false;  // change from true to false
```

Default timeouts when enabled:
- Idle timeout: 4 minutes
- Absolute timeout: 8 hours
- Session lock: prevents same teacher/admin account on two devices simultaneously

---

## 20. PERMISSION MODEL

| Action | Admin | Teacher | Student |
|---|---|---|---|
| Approve/reject users | ✅ | ❌ | ❌ |
| Create course | ✅ | ❌ | ❌ |
| Assign teacher to course | ✅ | ❌ | ❌ |
| Enroll student | ✅ | ❌ | ❌ |
| Create exam | ❌ | ✅ | ❌ |
| Publish exam | ❌ | ✅ | ❌ |
| Grade submission | ❌ | ✅ | ❌ |
| Take exam | ❌ | ❌ | ✅ |
| View own results | ❌ | ❌ | ✅ |
| View all submissions | ❌ | ✅ | ❌ |

---

## 21. COMMON ISSUES & FIXES

| Error | Cause | Fix |
|---|---|---|
| `supabase is not defined` | CDN blocked by network | Already fixed — using local `js/supabase.min.js` |
| `Unexpected token '<'` | Backend URL wrong or backend down | Start backend first, check port 5000 |
| `Authentication required` on chatbot | Token not sent | Fixed — chatbot auth is now optional |
| `No courses found for teacher` | teacher_id mismatch | Admin must assign courses via Manage Users |
| `Session expired` on every page | Testing mode | Set `TESTING_MODE_DISABLE_TIMEOUT = true` |
| Same questions every generation | Ollama not called on CPU | Fixed — `OLLAMA_MAX_CALLS_CPU=8` in `.env` |
| Registration not working | Supabase RLS blocking insert | Fixed — backend uses service role key |
| Email not sending | SMTP not configured | Add Gmail App Password to `backend/.env` |
| Chatbot unavailable | xAI no credits | Falls back to Ollama automatically |

---

## 22. TESTING CHECKLIST

### Admin
- [ ] Login with admin credentials
- [ ] See pending approval banner when new user registers
- [ ] Approve a student account
- [ ] Reject a teacher account
- [ ] Create a course and assign teacher
- [ ] Enroll student in course

### Teacher
- [ ] Login with teacher credentials
- [ ] See assigned courses in Create Exam
- [ ] Upload a PDF/PPTX file
- [ ] Generate questions — verify they differ from previous run
- [ ] Edit a question in Question Editor
- [ ] Preview exam in academic format
- [ ] Publish exam
- [ ] Auto-grade with AI after student submits
- [ ] Finalize attempt

### Student
- [ ] Login with student credentials
- [ ] See published exam on dashboard
- [ ] Start exam — timer starts
- [ ] Answer MCQ and subjective questions
- [ ] Submit exam
- [ ] View results after teacher finalizes

---

## 23. RESTART COMMANDS

```powershell
# Kill existing processes (Windows)
taskkill /F /IM python.exe
taskkill /F /IM node.exe

# Start Ollama
ollama serve

# Start backend (new terminal)
cd backend
../.venv/Scripts/python.exe app.py

# Start frontend (new terminal)
cd frontend
serve . -l 5500
```

---

## 24. DEPLOYMENT NOTES

For production:
- Replace `serve` with Nginx for frontend
- Use Gunicorn + Nginx for Flask backend
- Update `APP_URL` in `backend/.env` to production domain
- Update Supabase Site URL and Redirect URLs to production domain
- Set `TESTING_MODE_DISABLE_TIMEOUT = false` in session-manager.js
- Keep `SUPABASE_SERVICE_ROLE_KEY` in backend only — never expose in frontend
- Set `AI_CONFIDENCE_THRESHOLD` based on grading strictness (0.65 default)

---

## 25. GUIDE FILES IN THIS PROJECT

| File | Contents |
|---|---|
| **`DEVELOPER_GUIDE.md`** | **This file — complete guide covering everything** |
| `MODEL_SPECIFICATIONS.md` | Detailed AI model training specs, datasets, benchmarks |
| `QUESTION_GENERATION_FIX.md` | Fix history for question generation same-paper bug |
| `QUICK_REFERENCE.md` | Quick API reference and code snippets |
| `DATABASE_SCHEMA.sql` | SQL patches for Supabase tables |
