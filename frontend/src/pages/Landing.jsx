import { useEffect } from 'react'
import { Link } from 'react-router-dom'

export default function Landing() {
  useEffect(() => {
    // Override any body styles set by dashboard CSS
    document.body.style.cssText = `
      background: linear-gradient(135deg, #050D1A 0%, #08142D 50%, #0A1E46 100%) !important;
      min-height: 100vh;
      margin: 0;
      padding: 0;
      display: block;
      overflow-x: hidden;
      overflow-y: auto;
      color: #f8fafc;
    `
    return () => {
      document.body.style.cssText = ''
    }
  }, [])

  const features = [
    {
      icon: '📄',
      title: 'Material-Based Question Generation',
      desc: 'Generate MCQs, short, and long questions directly from uploaded course material and selected subject.',
    },
    {
      icon: '🤖',
      title: 'Hybrid Grading Pipeline',
      desc: 'Objective questions are auto-graded, while subjective answers are prepared for teacher review and final marks.',
    },
    {
      icon: '📋',
      title: 'Structured Exam Flow',
      desc: 'Supports exam publishing, student attempts, result pages, and teacher-side submission review in one flow.',
    },
    {
      icon: '📊',
      title: 'Dashboard Insights',
      desc: 'Track pending grading, completed attempts, scores, percentages, and per-exam performance summaries.',
    },
  ]

  const steps = [
    { step: 'Step 01', title: 'Create and Upload', desc: 'Teacher selects course/subject and uploads lecture material (PDF, DOCX, PPT).' },
    { step: 'Step 02', title: 'Generate and Review', desc: 'The system generates questions, shuffles options, and lets the teacher review before publishing.' },
    { step: 'Step 03', title: 'Student Attempt', desc: 'Published exams appear on the student dashboard where students attempt and submit online.' },
    { step: 'Step 04', title: 'Grade and Publish Results', desc: 'Objective grading is automatic; teachers review remaining answers and students receive final results.' },
  ]

  const team = [
    { initials: 'AH', name: 'Ali Hyder', id: 'B22F0764SE051' },
  ]

  return (
    <div style={{ fontFamily: "'Manrope', 'Segoe UI', sans-serif", color: '#f8fafc', minHeight: '100vh' }}>

      {/* ── NAVBAR ── */}
      <nav style={{
        position: 'sticky', top: 0, zIndex: 1000,
        background: 'rgba(8,11,34,0.96)',
        backdropFilter: 'blur(20px)',
        borderBottom: '1px solid rgba(129,140,248,0.15)',
        boxShadow: '0 4px 28px rgba(2,6,23,0.4)',
      }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 28px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', minHeight: 68 }}>
          {/* Logo */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 38, height: 38, borderRadius: 11,
              background: 'linear-gradient(140deg, #1E3A8A, #2563EB)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontWeight: 900, fontSize: 13, color: '#fff', letterSpacing: '-0.5px',
              boxShadow: '0 4px 12px rgba(37,99,235,0.4)',
            }}>SE</div>
            <span style={{ fontWeight: 800, fontSize: 15, color: '#f8fafc', letterSpacing: '-0.3px' }}>Smart Exam System</span>
          </div>

          {/* Nav links */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {['Home', 'Features', 'About'].map((label, i) => (
              <a key={label} href={['#home', '#features', '#about'][i]}
                style={{
                  color: 'rgba(226,232,240,0.82)', fontWeight: 600, fontSize: 14,
                  textDecoration: 'none', padding: '7px 14px', borderRadius: 8,
                  transition: 'background 0.2s, color 0.2s',
                }}
                onMouseEnter={e => { e.target.style.background = 'rgba(255,255,255,0.08)'; e.target.style.color = '#fff' }}
                onMouseLeave={e => { e.target.style.background = 'transparent'; e.target.style.color = 'rgba(226,232,240,0.82)' }}
              >{label}</a>
            ))}
            <Link to="/login" style={{
              marginLeft: 8,
              background: 'linear-gradient(135deg, #1E3A8A, #3B82F6)',
              color: '#fff', padding: '8px 20px', borderRadius: 10,
              fontWeight: 700, fontSize: 14, textDecoration: 'none',
              boxShadow: '0 4px 14px rgba(37,99,235,0.35)',
              transition: 'transform 0.2s, box-shadow 0.2s',
            }}
              onMouseEnter={e => { e.target.style.transform = 'translateY(-1px)'; e.target.style.boxShadow = '0 8px 20px rgba(37,99,235,0.45)' }}
              onMouseLeave={e => { e.target.style.transform = ''; e.target.style.boxShadow = '0 4px 14px rgba(37,99,235,0.35)' }}
            >Login</Link>
          </div>
        </div>
      </nav>

      {/* ── HERO ── */}
      <section id="home" style={{
        minHeight: '82vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        textAlign: 'center', padding: '80px 28px',
        background: 'linear-gradient(160deg, #050D1A 0%, #0A1E46 55%, #1E3A8A 100%)',
        position: 'relative', overflow: 'hidden',
      }}>
        {/* Background glow blobs */}
        <div style={{ position: 'absolute', top: '20%', left: '10%', width: 400, height: 400, borderRadius: '50%', background: 'radial-gradient(circle, rgba(37,99,235,0.18) 0%, transparent 70%)', pointerEvents: 'none' }} />
        <div style={{ position: 'absolute', bottom: '10%', right: '8%', width: 320, height: 320, borderRadius: '50%', background: 'radial-gradient(circle, rgba(99,102,241,0.14) 0%, transparent 70%)', pointerEvents: 'none' }} />

        <div style={{ maxWidth: 760, position: 'relative', zIndex: 1 }}>
          {/* Kicker badge */}
          <div style={{
            display: 'inline-block',
            background: 'rgba(255,255,255,0.07)',
            border: '1px solid rgba(129,140,248,0.3)',
            borderRadius: 999, padding: '6px 18px',
            fontSize: 11, fontWeight: 700, letterSpacing: '0.1em',
            textTransform: 'uppercase', color: 'rgba(199,210,254,0.9)',
            marginBottom: 24,
          }}>Teacher-Student Assessment Workflow</div>

          <h1 style={{
            fontSize: 'clamp(2.4rem, 5.5vw, 4rem)',
            fontWeight: 900, letterSpacing: '-0.04em', lineHeight: 1.06,
            color: '#ffffff', marginBottom: 22,
          }}>Smart Exam System</h1>

          <p style={{
            fontSize: 'clamp(1rem, 2vw, 1.18rem)',
            color: 'rgba(226,232,240,0.88)', lineHeight: 1.75,
            marginBottom: 16, maxWidth: 640, margin: '0 auto 16px',
          }}>
            Smart Exam System gives universities a clearer digital assessment workflow by helping teachers create papers from course material, manage student attempts, review answers, and publish results with more consistency and control.
          </p>

          <p style={{
            fontSize: 14, color: 'rgba(148,163,184,0.8)',
            lineHeight: 1.7, maxWidth: 560, margin: '0 auto 40px',
          }}>
            By connecting paper generation, student attempts, teacher review, grading, and result publication in one place, Smart Exam System helps institutions make assessment more transparent, efficient, and easier to manage.
          </p>

          <div style={{ display: 'flex', gap: 14, justifyContent: 'center', flexWrap: 'wrap' }}>
            <Link to="/login" style={{
              background: 'linear-gradient(135deg, #1E3A8A, #3B82F6)',
              color: '#fff', padding: '13px 30px', borderRadius: 12,
              fontWeight: 700, fontSize: 15, textDecoration: 'none',
              boxShadow: '0 8px 24px rgba(37,99,235,0.4)',
              transition: 'transform 0.2s, box-shadow 0.2s',
            }}
              onMouseEnter={e => { e.target.style.transform = 'translateY(-2px)'; e.target.style.boxShadow = '0 14px 32px rgba(37,99,235,0.5)' }}
              onMouseLeave={e => { e.target.style.transform = ''; e.target.style.boxShadow = '0 8px 24px rgba(37,99,235,0.4)' }}
            >Start Creating Exams</Link>
            <a href="#features" style={{
              background: 'rgba(255,255,255,0.06)',
              border: '1.5px solid rgba(255,255,255,0.2)',
              color: '#fff', padding: '13px 30px', borderRadius: 12,
              fontWeight: 700, fontSize: 15, textDecoration: 'none',
              transition: 'background 0.2s, border-color 0.2s',
            }}
              onMouseEnter={e => { e.target.style.background = 'rgba(255,255,255,0.12)'; e.target.style.borderColor = 'rgba(255,255,255,0.4)' }}
              onMouseLeave={e => { e.target.style.background = 'rgba(255,255,255,0.06)'; e.target.style.borderColor = 'rgba(255,255,255,0.2)' }}
            >Learn More</a>
          </div>
        </div>
      </section>

      {/* ── FEATURES ── */}
      <section id="features" style={{ padding: '88px 28px', background: '#0B1530' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>
          <div style={{ textAlign: 'center', marginBottom: 56 }}>
            <h2 style={{ fontSize: 'clamp(1.6rem, 3vw, 2.2rem)', fontWeight: 800, color: '#ffffff', marginBottom: 10, letterSpacing: '-0.03em' }}>
              Built for Real Exam Operations
            </h2>
            <p style={{ fontSize: 15, color: 'rgba(148,163,184,0.8)', margin: 0 }}>
              From content upload to publishing, attempts, grading, and results
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 20 }}>
            {features.map(({ icon, title, desc }) => (
              <div key={title} style={{
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: 16, padding: '28px 24px',
                transition: 'transform 0.2s, border-color 0.2s, background 0.2s',
              }}
                onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-4px)'; e.currentTarget.style.borderColor = 'rgba(99,102,241,0.3)'; e.currentTarget.style.background = 'rgba(255,255,255,0.07)' }}
                onMouseLeave={e => { e.currentTarget.style.transform = ''; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)'; e.currentTarget.style.background = 'rgba(255,255,255,0.04)' }}
              >
                <div style={{
                  width: 48, height: 48, borderRadius: 13,
                  background: 'rgba(37,99,235,0.15)',
                  border: '1px solid rgba(37,99,235,0.25)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 22, marginBottom: 16,
                }}>{icon}</div>
                <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#818CF8', marginBottom: 8 }}>Feature</p>
                <h3 style={{ fontSize: 15, fontWeight: 700, color: '#ffffff', marginBottom: 10, lineHeight: 1.4 }}>{title}</h3>
                <p style={{ fontSize: 13.5, color: 'rgba(148,163,184,0.85)', lineHeight: 1.65, margin: 0 }}>{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section style={{ padding: '88px 28px', background: '#080F24' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>
          <div style={{ textAlign: 'center', marginBottom: 56 }}>
            <h2 style={{ fontSize: 'clamp(1.6rem, 3vw, 2.2rem)', fontWeight: 800, color: '#ffffff', marginBottom: 10, letterSpacing: '-0.03em' }}>
              How Smart Exam System Works
            </h2>
            <p style={{ fontSize: 15, color: 'rgba(148,163,184,0.8)', margin: 0 }}>
              A complete teacher-to-student assessment cycle
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 20 }}>
            {steps.map(({ step, title, desc }, i) => (
              <div key={step} style={{
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.07)',
                borderRadius: 16, padding: '28px 22px',
                position: 'relative',
              }}>
                <div style={{
                  display: 'inline-block',
                  background: 'rgba(37,99,235,0.15)',
                  border: '1px solid rgba(37,99,235,0.25)',
                  color: '#93C5FD', padding: '4px 12px',
                  borderRadius: 999, fontSize: 11, fontWeight: 800,
                  letterSpacing: '0.06em', marginBottom: 14,
                }}>{step}</div>
                <h3 style={{ fontSize: 15, fontWeight: 700, color: '#ffffff', marginBottom: 10, lineHeight: 1.4 }}>{title}</h3>
                <p style={{ fontSize: 13.5, color: 'rgba(148,163,184,0.85)', lineHeight: 1.65, margin: 0 }}>{desc}</p>
                <div style={{
                  position: 'absolute', top: 24, right: 22,
                  width: 28, height: 28, borderRadius: '50%',
                  background: 'rgba(37,99,235,0.12)',
                  border: '1px solid rgba(37,99,235,0.2)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, fontWeight: 900, color: '#60A5FA',
                }}>{i + 1}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── ABOUT ── */}
      <section id="about" style={{ padding: '88px 28px', background: '#0B1530' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>

          {/* About card */}
          <div style={{
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 20, padding: '40px 36px', marginBottom: 24,
          }}>
            <h2 style={{ fontSize: 'clamp(1.4rem, 2.5vw, 1.9rem)', fontWeight: 800, color: '#ffffff', marginBottom: 8, letterSpacing: '-0.03em' }}>
              About Smart Exam System
            </h2>
            <p style={{ fontSize: 14, color: '#818CF8', fontWeight: 600, marginBottom: 16 }}>A practical end-to-end exam management platform</p>
            <p style={{ fontSize: 14.5, color: 'rgba(148,163,184,0.85)', lineHeight: 1.75, margin: 0, maxWidth: 720 }}>
              Smart Exam System is a Final Year Project designed to solve practical exam management challenges in academic environments. It connects exam creation, student attempts, grading, and reporting in a single consistent workflow.
            </p>
          </div>

          {/* Team */}
          <div style={{
            background: 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 20, padding: '36px', marginBottom: 24,
          }}>
            <h2 style={{ fontSize: '1.3rem', fontWeight: 800, color: '#ffffff', marginBottom: 28, textAlign: 'center', letterSpacing: '-0.02em' }}>Meet Our Team</h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 20 }}>
              {team.map(({ initials, name, id }) => (
                <div key={id} style={{
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid rgba(255,255,255,0.08)',
                  borderRadius: 16, padding: '28px 20px', textAlign: 'center',
                }}>
                  <div style={{
                    width: 60, height: 60, borderRadius: '50%',
                    background: 'linear-gradient(135deg, #1E3A8A, #3B82F6)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 18, fontWeight: 900, color: '#fff',
                    margin: '0 auto 14px',
                    boxShadow: '0 4px 14px rgba(37,99,235,0.35)',
                  }}>{initials}</div>
                  <h3 style={{ fontSize: 14, fontWeight: 700, color: '#ffffff', marginBottom: 6 }}>{name}</h3>
                  <p style={{ fontSize: 12, color: 'rgba(148,163,184,0.7)', margin: 0, fontFamily: 'monospace' }}>{id}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Supervisor */}
          <div style={{
            background: 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 20, padding: '36px', textAlign: 'center',
          }}>
            <h2 style={{ fontSize: '1.3rem', fontWeight: 800, color: '#ffffff', marginBottom: 28, letterSpacing: '-0.02em' }}>Project Supervisor</h2>
            <div style={{ display: 'inline-block' }}>
              <div style={{
                width: 72, height: 72, borderRadius: '50%',
                background: 'linear-gradient(135deg, #1E3A8A, #6366F1)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 22, fontWeight: 900, color: '#fff',
                margin: '0 auto 14px',
                boxShadow: '0 4px 16px rgba(99,102,241,0.35)',
              }}>DM</div>
              <h3 style={{ fontSize: 16, fontWeight: 700, color: '#ffffff', marginBottom: 6 }}>Dr. Musadaq Mansoor</h3>
              <p style={{ fontSize: 13, color: '#818CF8', fontWeight: 600, marginBottom: 4 }}>Project Supervisor</p>
              <p style={{ fontSize: 12, color: 'rgba(148,163,184,0.7)', margin: 0 }}>Department of Software Engineering</p>
            </div>
          </div>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer style={{
        borderTop: '1px solid rgba(255,255,255,0.07)',
        padding: '40px 28px', textAlign: 'center',
        background: '#050D1A',
      }}>
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, marginBottom: 14 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 9,
              background: 'linear-gradient(140deg, #1E3A8A, #2563EB)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontWeight: 900, fontSize: 11, color: '#fff',
            }}>SE</div>
            <span style={{ fontWeight: 700, fontSize: 14, color: 'rgba(226,232,240,0.7)' }}>Smart Exam System</span>
          </div>
          <p style={{ color: 'rgba(148,163,184,0.55)', fontSize: 13, margin: '0 0 6px' }}>
            Final Year Project · BS Software Engineering · Pak Austria Fachhochschule, Mang Haripur
          </p>
          <p style={{ color: 'rgba(148,163,184,0.4)', fontSize: 12, margin: 0 }}>
            Ali Hyder · Supervisor: Dr. Musadaq Mansoor
          </p>
          <p style={{ color: 'rgba(148,163,184,0.35)', fontSize: 12, marginTop: 12 }}>
            &copy; 2026 Smart Exam System
          </p>
        </div>
      </footer>
    </div>
  )
}
