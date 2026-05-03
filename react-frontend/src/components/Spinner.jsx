export default function Spinner({ size = 28, color = '#1E3A8A' }) {
  return (
    <div style={{
      width: size, height: size,
      border: `3px solid rgba(30,58,138,0.15)`,
      borderTop: `3px solid ${color}`,
      borderRadius: '50%',
      animation: 'spin 0.8s linear infinite',
      display: 'inline-block'
    }} />
  )
}
