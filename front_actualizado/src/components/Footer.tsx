export function Footer() {
  return (
    <footer style={{ background: 'var(--surface)', borderTop: '1px solid var(--border)', padding: 'clamp(40px,5vw,56px) clamp(24px,6vw,80px) 32px' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 48, marginBottom: 48 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, color: 'var(--text)' }}>
              <div style={{ color: 'var(--primary)' }}>
                <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
                  <circle cx="14" cy="14" r="12" stroke="currentColor" strokeWidth="1.5" />
                  <ellipse cx="14" cy="14" rx="5.5" ry="12" stroke="currentColor" strokeWidth="1.5" />
                  <line x1="2" y1="14" x2="26" y2="14" stroke="currentColor" strokeWidth="1.5" />
                </svg>
              </div>
              <span style={{ fontFamily: 'Fraunces, serif', fontWeight: 600, fontSize: 16, letterSpacing: '-0.02em' }}>
                GLOBAL EXCHANGE
              </span>
            </div>
            <p style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text-3)', fontFamily: 'DM Sans', maxWidth: 240 }}>
              Casa de cambios líder en Paraguay. Cotizaciones transparentes y operaciones seguras.
            </p>
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.1em', marginBottom: 16, fontFamily: 'DM Sans' }}>NAVEGACIÓN</div>
            {['Inicio', 'Cotizaciones', 'Conversor', 'Seguridad'].map(l => (
              <a key={l} href={`/#${l.toLowerCase()}`} style={{ display: 'block', fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans', marginBottom: 10, textDecoration: 'none' }}
                onMouseEnter={e => (e.currentTarget.style.color = 'var(--primary)')}
                onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-2)')}>
                {l}
              </a>
            ))}
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.1em', marginBottom: 16, fontFamily: 'DM Sans' }}>LEGAL</div>
            {['Términos de uso', 'Privacidad'].map(l => (
              <a key={l} href="#" style={{ display: 'block', fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans', marginBottom: 10, textDecoration: 'none' }}>{l}</a>
            ))}
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.1em', marginBottom: 16, fontFamily: 'DM Sans' }}>CONTACTO</div>
            <div style={{ fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans', lineHeight: 1.7 }}>
              <div>Asunción, Paraguay</div>
              <div style={{ marginTop: 8 }}>info@globalexchange.com.py</div>
            </div>
          </div>
        </div>
        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 24, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <span style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>
            © 2026 Global Exchange. Todos los derechos reservados.
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>
            Asunción, Paraguay · Habilitado por el BCP
          </span>
        </div>
      </div>
    </footer>
  );
}
