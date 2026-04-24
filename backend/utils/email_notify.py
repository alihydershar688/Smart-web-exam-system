"""
Email Notification Service — Smart Exam System
Uses Supabase's built-in email (via SMTP env vars) or falls back to
a simple log so the system never crashes if email is not configured.

Supported events:
  1. exam_published   — notify enrolled students
  2. result_ready     — notify student their result is published
  3. account_approved — notify user their account is activated
  4. account_suspended— notify user their account is suspended
"""

import os
import smtplib
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── SMTP config from environment ─────────────────────────
SMTP_HOST     = os.getenv('SMTP_HOST', '')
SMTP_PORT     = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER     = os.getenv('SMTP_USER', '')
SMTP_PASS     = os.getenv('SMTP_PASS', '')
SMTP_FROM     = os.getenv('SMTP_FROM', SMTP_USER)
SMTP_ENABLED  = bool(SMTP_HOST and SMTP_USER and SMTP_PASS)

APP_NAME      = 'Smart Exam System'
APP_URL       = os.getenv('APP_URL', 'http://127.0.0.1:5500')


def _send(to_email: str, subject: str, html_body: str) -> bool:
    """Send one email. Returns True on success, False on failure."""
    if not SMTP_ENABLED:
        # Log instead of crash when SMTP is not configured
        print(f"[email] SMTP not configured — would send to {to_email}: {subject}")
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f"{APP_NAME} <{SMTP_FROM}>"
        msg['To']      = to_email
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        print(f"[email] Sent '{subject}' to {to_email}")
        return True
    except Exception as exc:
        print(f"[email] Failed to send to {to_email}: {exc}")
        return False


def _base_template(title: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  body{{font-family:'Segoe UI',Arial,sans-serif;background:#f8fafc;margin:0;padding:32px;color:#0f172a;}}
  .card{{background:#fff;border-radius:12px;padding:32px;max-width:560px;margin:0 auto;
         box-shadow:0 4px 16px rgba(0,0,0,0.08);border:1px solid #e2e8f0;}}
  h2{{color:#4f46e5;margin-bottom:8px;}}
  p{{line-height:1.65;color:#334155;}}
  .btn{{display:inline-block;background:#4f46e5;color:#fff;padding:12px 28px;
        border-radius:8px;text-decoration:none;font-weight:700;margin-top:16px;}}
  .footer{{text-align:center;color:#94a3b8;font-size:0.78rem;margin-top:24px;}}
</style></head>
<body>
  <div class="card">
    <h2>{APP_NAME}</h2>
    <h3 style="color:#0f172a;margin-bottom:16px;">{title}</h3>
    {body_html}
    <div class="footer">{APP_NAME} &nbsp;|&nbsp; Automated notification</div>
  </div>
</body></html>"""


# ── Public notification functions ────────────────────────

def notify_exam_published(student_emails: list, exam_title: str, course_name: str = '') -> int:
    """
    Notify enrolled students that a new exam has been published.
    Returns count of emails sent successfully.
    """
    sent = 0
    subject = f"New Exam Published: {exam_title}"
    course_line = f"<p><strong>Course:</strong> {course_name}</p>" if course_name else ''
    body = f"""
        <p>A new exam has been published for your course.</p>
        {course_line}
        <p><strong>Exam:</strong> {exam_title}</p>
        <p>Log in to your student dashboard to view and attempt the exam.</p>
        <a href="{APP_URL}/dashboard-student.html" class="btn">Go to Dashboard</a>
    """
    html = _base_template("New Exam Available", body)
    for email in student_emails:
        if _send(email, subject, html):
            sent += 1
    return sent


def notify_result_ready(student_email: str, student_name: str,
                        exam_title: str, score: float, max_score: float,
                        percentage: float, attempt_id: str = '') -> bool:
    """Notify a student that their exam result has been published."""
    grade = 'A' if percentage >= 90 else 'B' if percentage >= 80 else 'C' if percentage >= 70 else 'D' if percentage >= 60 else 'F'
    result_link = f"{APP_URL}/exam-results.html?attempt={attempt_id}" if attempt_id else f"{APP_URL}/dashboard-student.html"
    body = f"""
        <p>Hi <strong>{student_name}</strong>,</p>
        <p>Your exam result for <strong>{exam_title}</strong> has been published.</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
          <tr style="background:#f1f5f9;">
            <td style="padding:10px;font-weight:700;">Score</td>
            <td style="padding:10px;">{score:.1f} / {max_score:.0f}</td>
          </tr>
          <tr>
            <td style="padding:10px;font-weight:700;">Percentage</td>
            <td style="padding:10px;">{percentage:.1f}%</td>
          </tr>
          <tr style="background:#f1f5f9;">
            <td style="padding:10px;font-weight:700;">Grade</td>
            <td style="padding:10px;font-size:1.2rem;font-weight:800;">{grade}</td>
          </tr>
        </table>
        <a href="{result_link}" class="btn">View Full Result</a>
    """
    return _send(student_email, f"Result Published: {exam_title}", _base_template("Your Result is Ready", body))


def notify_account_approved(user_email: str, user_name: str, role: str) -> bool:
    """Notify a user that their account has been activated by admin."""
    body = f"""
        <p>Hi <strong>{user_name}</strong>,</p>
        <p>Your <strong>{role.title()}</strong> account on {APP_NAME} has been <strong style="color:#059669;">activated</strong>.</p>
        <p>You can now log in and access all features available to your role.</p>
        <a href="{APP_URL}/login.html" class="btn">Login Now</a>
    """
    return _send(user_email, f"Account Activated — {APP_NAME}", _base_template("Account Activated", body))


def notify_account_suspended(user_email: str, user_name: str) -> bool:
    """Notify a user that their account has been suspended."""
    body = f"""
        <p>Hi <strong>{user_name}</strong>,</p>
        <p>Your account on {APP_NAME} has been <strong style="color:#dc2626;">suspended</strong>.</p>
        <p>Please contact your administrator if you believe this is a mistake.</p>
    """
    return _send(user_email, f"Account Suspended — {APP_NAME}", _base_template("Account Suspended", body))
