export default function StatCard({ label, value, footer, accent = '#2563EB', onClick }) {
  return (
    <div onClick={onClick} style={{
      background: '#fff', border: '1px solid #DBEAFE', borderRadius: 10,
      boxShadow: '0 2px 8px rgba(30,58,138,0.07)', padding: '1rem',
      position: 'relative', overflow: 'hidden', cursor: onClick ? 'pointer' : 'default',
      transition: 'transform 0.2s, box-shadow 0.2s'
    }}
      onMouseEnter={e => { if (onClick) { e.currentTarget.style.transform = 'translateY(-3px)'; e.currentTarget.style.boxShadow = '0 8px 20px rgba(30,58,138,0.12)' } }}
      onMouseLeave={e => { e.currentTarget.style.transform = ''; e.currentTarget.style.boxShadow = '0 2px 8px rgba(30,58,138,0.07)' }}
    >
      <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 4, background: accent }} />
      <div style={{ fontSize: 11, fontWeight: 700, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: '2rem', fontWeight: 900, color: '#1E3A8A', lineHeight: 1.1, marginBottom: 4 }}>{value ?? '—'}</div>
      {footer && <div style={{ fontSize: 11, color: '#6B7280' }}>{footer}</div>}
    </div>
  )
}
