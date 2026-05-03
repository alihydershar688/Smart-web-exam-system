import { Link } from 'react-router-dom'

export default function Landing() {
  return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(160deg, #081126 0%, #0b1838 38%, #0e3a68 72%, #0f766e 100%)', color: '#f8fafc', fontFamily: 'Manrope, sans-serif', overflowX: 'hidden' }}>
      {/* Navbar */}
      <nav style={{ position: 'sticky', top: 0, zIndex: 1000, background: 'rgba(8,11,34,0.95)', backdropFilter: 'blur(20px)', borderBottom: '1px solid rgba(129,140,248,0.18)', boxShadow: '0 4px 28px rgba(2,6,23,0.38)' }}>
        <div style={{ maxWidth: 1400, margin: '0 auto', padding: '0 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', minHeight: 72 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 40, height: 40, borderRadius: 12, background: 'linear-gradient(140deg, #1E3A8A, #2563EB)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 14, color: '#fff' }}>SE</div>
            <span style={{ fontWeight: 800, fontSize: 16, color: '#f8fafc' }}>Smart Exam System</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
            <a href="#features" style={{ color: 'rgba(226,232,240,0.86)', fontWeight: 700, fontSize: 14, textDecoration: 'none' }}>Features</a>
            <a href="#about" style={{ color: 'rgba(226,232,240,0.86)', fontWeight: 700, fontSize: 14, textDecoration: 'none' }}>About</a>
            <Link to="/login" style={{ background: 'linear-gradient(135deg, #1E3A8A, #3B82F6)', color: '#fff', padding: '8px 20px', borderRadius: 12, fontWeight: 700, fontSize: 14, textDecoration: 'none', boxShadow: '0 8px 20px rgba(37,99,235,0.3)' }}>Login</Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section style={{ padding: '80px 32px', textAlign: 'center', maxWidth: 900, margin: '0 auto' }}>
        <div style={{ display: 'inline-block', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(191,219,254,0.34)', borderRadius: 999, padding: '6px 18px', fontSize: 13, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 24, color: 'rgba(255,255,255,0.92)' }}>
          Teacher-Student Assessment Workflow
        </div>
        <h1 style={{ fontSize: 'clamp(2.4rem, 5vw, 4rem)', fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.08, marginBottom: 24 }}>Smart Exam System</h1>
        <p style={{ fontSize: 'clamp(1rem, 2vw, 1.2rem)', color: 'rgba(241,245,249,0.96)', lineHeight: 1.75, marginBottom: 40, maxWidth: 680, margin: '0 auto 40px' }}>
          AI-powered exam management platform. Upload course material, generate questions automatically, manage student attempts, and publish results — all in one place.
        </p>
        <div style={{ display: 'flex', gap: 16, justifyContent: 'center', flexWrap: 'wrap' }}>
          <Link to="/login" style={{ background: 'linear-gradient(135deg, #14b8a6, #2563eb)', color: '#fff', padding: '14px 32px', borderRadius: 14, fontWeight: 700, fontSize: 16, textDecoration: 'none', boxShadow: '0 16px 28px rgba(37,99,235,0.28)' }}>Get Started</Link>
          <a href="#features" style={{ border: '2px solid rgba(255,255,255,0.85)', color: '#fff', padding: '14px 32px', borderRadius: 14, fontWeight: 700, fontSize: 16, textDecoration: 'none' }}>Learn More</a>
        </div>
      </section>

      {/* Features */}
      <section id="features" style={{ padding: '80px 32px', maxWidth: 1200, margin: '0 auto' }}>
        <h2 style={{ textAlign: 'center', fontSize: '2rem', fontWeight: 800, marginBottom: 12 }}>Built for Real Exam Operations</h2>
        <p style={{ textAlign: 'center', color: 'rgba(191,219,254,0.8)', marginBottom: 48 }}>From content upload to publishing, attempts, grading, and results</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 20 }}>
          {[
            ['AI Question Generation', 'Generate MCQs, short, and long questions directly from uploaded course material.'],
            ['Hybrid Grading Pipeline', 'Objective questions auto-graded. Subjective answers prepared for teacher review.'],
            ['Structured Exam Flow', 'Supports exam publishing, student attempts, result pages, and teacher review.'],
            ['Dashboard Insights', 'Track pending grading, scores, percentages, and per-exam performance summaries.'],
          ].map(([title, desc]) => (
            <div key={title} style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 16, padding: '1.5rem', backdropFilter: 'blur(8px)' }}>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 800, marginBottom: 10 }}>{title}</h3>
              <p style={{ color: 'rgba(191,219,254,0.8)', fontSize: 14, lineHeight: 1.65 }}>{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section style={{ padding: '80px 32px', maxWidth: 1200, margin: '0 auto' }}>
        <h2 style={{ textAlign: 'center', fontSize: '2rem', fontWeight: 800, marginBottom: 12 }}>How Smart Exam System Works</h2>
        <p style={{ textAlign: 'center', color: 'rgba(191,219,254,0.8)', marginBottom: 48 }}>A complete teacher-to-student assessment cycle</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 20 }}>
          {[
            ['Step 01', 'Create and Upload', 'Teacher selects course and uploads lecture material (PDF, DOCX, PPT).'],
            ['Step 02', 'Generate and Review', 'System generates questions. Teacher reviews before publishing.'],
            ['Step 03', 'Student Attempt', 'Published exams appear on student dashboard for online attempt.'],
            ['Step 04', 'Grade and Publish', 'Objective grading is automatic. Teachers review remaining answers.'],
          ].map(([step, title, desc]) => (
            <div key={step} style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 16, padding: '1.5rem' }}>
              <span style={{ background: 'rgba(59,130,246,0.2)', color: '#93c5fd', padding: '4px 12px', borderRadius: 999, fontSize: 12, fontWeight: 700 }}>{step}</span>
              <h3 style={{ fontSize: '1rem', fontWeight: 800, margin: '12px 0 8px' }}>{title}</h3>
              <p style={{ color: 'rgba(191,219,254,0.8)', fontSize: 14, lineHeight: 1.65 }}>{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer style={{ borderTop: '1px solid rgba(255,255,255,0.08)', padding: '40px 32px', textAlign: 'center' }}>
        <p style={{ color: 'rgba(148,163,184,0.7)', fontSize: 13 }}>
          Smart Exam System — Final Year Project, BS Software Engineering<br />
          Pak Austria Fachhochschule, Mang Haripur | Ali Hyder · Badar Ul Islam Qureshi · Kashan Sardar
        </p>
        <p style={{ color: 'rgba(148,163,184,0.5)', fontSize: 12, marginTop: 8 }}>Supervisor: Dr. Musadaq Mansoor</p>
      </footer>
    </div>
  )
}
