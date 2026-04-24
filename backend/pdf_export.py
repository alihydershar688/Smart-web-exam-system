"""
PDF Export helper — generates printable HTML for exam results.
Imported by app.py.
"""

def build_result_html(exam_title, student_name, student_email, student_reg,
                      score, max_score, percentage, grade, grade_color,
                      submitted, status, answers_sorted, q_map):
    """Return a complete HTML string suitable for browser print-to-PDF."""

    rows_html = ''
    for i, ans in enumerate(answers_sorted, 1):
        qid    = ans.get('question_id')
        q      = q_map.get(qid, {})
        qt     = str(q.get('question_type') or '').lower()
        q_text = q.get('question_text') or '—'
        s_ans  = ans.get('student_answer') or '(no answer)'
        m_obt  = float(ans.get('marks_obtained') or 0)
        m_max  = float(ans.get('max_marks') or q.get('marks') or 1)
        correct   = ans.get('is_correct')
        r_status  = str(ans.get('review_status') or '').replace('_', ' ').title()
        remarks   = ans.get('teacher_remarks') or ''

        if correct is True:
            status_badge = '<span style="color:#059669;font-weight:700;">✔ Correct</span>'
        elif correct is False:
            status_badge = '<span style="color:#dc2626;font-weight:700;">✘ Incorrect</span>'
        else:
            status_badge = f'<span style="color:#d97706;font-weight:700;">{r_status}</span>'

        is_mcq = any(x in qt for x in ['mcq', 'multiple', 'true', 'false'])
        ans_display = f'<strong>{s_ans}</strong>' if is_mcq else f'<p style="margin:0;white-space:pre-wrap;">{s_ans}</p>'

        rows_html += f'''
        <tr>
            <td style="width:32px;text-align:center;font-weight:700;color:#6366f1;">Q{i}</td>
            <td style="padding:10px 8px;">
                <div style="font-weight:600;margin-bottom:4px;">{q_text}</div>
                <div style="color:#64748b;font-size:0.82rem;margin-bottom:4px;">
                    Type: {str(q.get("question_type","")).replace("_"," ").title()}
                </div>
                <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:8px;margin-top:4px;">
                    {ans_display}
                </div>
                {f'<div style="margin-top:6px;color:#64748b;font-size:0.82rem;"><em>Teacher remarks: {remarks}</em></div>' if remarks else ''}
            </td>
            <td style="text-align:center;white-space:nowrap;">{status_badge}</td>
            <td style="text-align:center;font-weight:700;white-space:nowrap;">{m_obt:.1f} / {m_max:.0f}</td>
        </tr>'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Exam Result — {exam_title}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background:#f8fafc; color:#0f172a; padding:32px; }}
  .card {{ background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:28px; margin-bottom:20px; box-shadow:0 2px 8px rgba(0,0,0,0.06); }}
  h1 {{ font-size:1.5rem; font-weight:800; color:#0f172a; margin-bottom:4px; }}
  .subtitle {{ color:#64748b; font-size:0.9rem; margin-bottom:20px; }}
  .meta-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:20px; }}
  .meta-item {{ background:#f1f5f9; border-radius:8px; padding:12px; }}
  .meta-label {{ font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.06em; color:#64748b; margin-bottom:4px; }}
  .meta-value {{ font-size:1rem; font-weight:800; color:#0f172a; }}
  .score-circle {{ display:inline-flex; align-items:center; justify-content:center; width:80px; height:80px; border-radius:50%; border:4px solid {grade_color}; color:{grade_color}; font-size:1.6rem; font-weight:900; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ background:#f1f5f9; padding:10px 8px; text-align:left; font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:0.06em; color:#64748b; border-bottom:2px solid #e2e8f0; }}
  td {{ padding:8px; border-bottom:1px solid #f1f5f9; vertical-align:top; font-size:0.88rem; }}
  tr:last-child td {{ border-bottom:none; }}
  .footer {{ text-align:center; color:#94a3b8; font-size:0.78rem; margin-top:20px; }}
  @media print {{
    body {{ background:#fff; padding:16px; }}
    .no-print {{ display:none; }}
    .card {{ box-shadow:none; border:1px solid #e2e8f0; }}
  }}
</style>
</head>
<body>

<div class="no-print" style="margin-bottom:16px;">
  <button onclick="window.print()" style="background:#4f46e5;color:#fff;border:none;padding:10px 24px;border-radius:8px;font-size:0.95rem;font-weight:700;cursor:pointer;">
    Save as PDF / Print
  </button>
  <button onclick="window.close()" style="background:#f1f5f9;color:#0f172a;border:1px solid #e2e8f0;padding:10px 24px;border-radius:8px;font-size:0.95rem;font-weight:700;cursor:pointer;margin-left:8px;">
    Close
  </button>
</div>

<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;">
    <div>
      <h1>Smart Exam System</h1>
      <div class="subtitle">Official Examination Result</div>
      <div style="font-size:1.1rem;font-weight:700;color:#4f46e5;margin-bottom:8px;">{exam_title}</div>
      <div style="color:#64748b;font-size:0.88rem;">
        <strong>Student:</strong> {student_name}<br>
        <strong>Email:</strong> {student_email}<br>
        {f"<strong>Reg No:</strong> {student_reg}<br>" if student_reg else ""}
        <strong>Submitted:</strong> {submitted}<br>
        <strong>Status:</strong> {status.replace("_"," ").title()}
      </div>
    </div>
    <div style="text-align:center;">
      <div class="score-circle">{grade}</div>
      <div style="margin-top:8px;font-size:0.82rem;color:#64748b;">Grade</div>
    </div>
  </div>
</div>

<div class="card">
  <div class="meta-grid">
    <div class="meta-item">
      <div class="meta-label">Score</div>
      <div class="meta-value">{score:.1f} / {max_score:.0f}</div>
    </div>
    <div class="meta-item">
      <div class="meta-label">Percentage</div>
      <div class="meta-value" style="color:{grade_color};">{percentage:.1f}%</div>
    </div>
    <div class="meta-item">
      <div class="meta-label">Result</div>
      <div class="meta-value" style="color:{'#059669' if percentage >= 50 else '#dc2626'};">
        {'PASS' if percentage >= 50 else 'FAIL'}
      </div>
    </div>
  </div>
</div>

<div class="card">
  <h2 style="font-size:1rem;font-weight:800;margin-bottom:16px;color:#0f172a;">Answer Sheet</h2>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Question &amp; Answer</th>
        <th style="text-align:center;">Result</th>
        <th style="text-align:center;">Marks</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</div>

<div class="footer">
  Generated by Smart Exam System &nbsp;|&nbsp; {submitted}
</div>

</body>
</html>'''
