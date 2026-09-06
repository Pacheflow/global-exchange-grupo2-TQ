import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import GlobalExchangeMap from '../components/GlobalExchangeMap';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';

const SunIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <circle cx="12" cy="12" r="5" />
    <line x1="12" y1="1" x2="12" y2="3" />
    <line x1="12" y1="21" x2="12" y2="23" />
    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
    <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
    <line x1="1" y1="12" x2="3" y2="12" />
    <line x1="21" y1="12" x2="23" y2="12" />
  </svg>
);
const MoonIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
);

export default function Login() {
  const { login } = useAuth();
  const { isDark, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [tab, setTab] = useState<'login' | 'forgot'>('login');

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setTimeout(() => {
      if (password.length < 3) {
        setError('Credenciales incorrectas. Por favor, inténtalo nuevamente.');
        setLoading(false);
        return;
      }
      login('client');
      navigate('/dashboard');
    }, 1200);
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      background: 'var(--bg)',
    }}>
      {/* Left: Brand panel */}
      <div style={{
        background: 'radial-gradient(ellipse at 55% 50%, #0D1E4A 0%, #060B1E 70%)',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        overflow: 'hidden',
      }}>
        {/* Logo header */}
        <div style={{ padding: '28px 40px', display: 'flex', alignItems: 'center', gap: 12, zIndex: 2, position: 'relative' }}>
          <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 12, textDecoration: 'none' }}>
            <div style={{ color: '#3B5BFF' }}>
              <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                <circle cx="14" cy="14" r="12" stroke="currentColor" strokeWidth="1.5" />
                <ellipse cx="14" cy="14" rx="5.5" ry="12" stroke="currentColor" strokeWidth="1.5" />
                <line x1="2" y1="14" x2="26" y2="14" stroke="currentColor" strokeWidth="1.5" />
                <line x1="4" y1="8.5" x2="24" y2="8.5" stroke="currentColor" strokeWidth="1" strokeOpacity="0.6" />
                <line x1="4" y1="19.5" x2="24" y2="19.5" stroke="currentColor" strokeWidth="1" strokeOpacity="0.6" />
              </svg>
            </div>
            <div style={{ lineHeight: 1 }}>
              <div style={{ fontFamily: 'Fraunces, serif', fontWeight: 600, fontSize: 18, letterSpacing: '-0.02em', color: '#E8F2FF' }}>GLOBAL</div>
              <div style={{ fontFamily: 'DM Sans, sans-serif', fontWeight: 300, fontSize: 11, color: '#5A7AAC', letterSpacing: '0.15em' }}>EXCHANGE</div>
            </div>
          </Link>
        </div>

        {/* Map visualization */}
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 32px', position: 'relative' }}>
          <div style={{ width: '100%', maxWidth: 520, aspectRatio: '1000 / 500', position: 'relative' }}>
            <GlobalExchangeMap variant="auth" animate />
          </div>
        </div>

        {/* Bottom message */}
        <div style={{ padding: '40px', position: 'relative', zIndex: 2 }}>
          <blockquote style={{
            fontFamily: 'Fraunces, serif', fontStyle: 'italic', fontWeight: 300,
            fontSize: 17, color: '#8BA8E0', lineHeight: 1.55,
            borderLeft: '2px solid #2A4080', paddingLeft: 16,
          }}>
            "La plataforma de cambio más confiable y transparente del mercado paraguayo."
          </blockquote>
          <div style={{ marginTop: 12, fontSize: 12, color: '#2A4070', fontFamily: 'DM Sans' }}>
            Global Exchange · Asunción, Paraguay
          </div>
        </div>
      </div>

      {/* Right: Form panel */}
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px 64px',
        position: 'relative',
        background: 'var(--bg)',
      }}>
        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          style={{
            position: 'absolute', top: 24, right: 24,
            background: 'var(--surface-2)', border: '1px solid var(--border)',
            borderRadius: 8, padding: '8px', cursor: 'pointer',
            color: 'var(--text-2)', display: 'flex', alignItems: 'center',
          }}
        >
          {isDark ? <SunIcon /> : <MoonIcon />}
        </button>

        <div style={{ width: '100%', maxWidth: 380 }}>
          {/* Header */}
          <div style={{ marginBottom: 40 }}>
            <h1 style={{ fontFamily: 'Fraunces, serif', fontSize: 32, fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.03em', marginBottom: 8 }}>
              {tab === 'login' ? 'Iniciar sesión' : 'Recuperar contraseña'}
            </h1>
            <p style={{ fontSize: 14, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>
              {tab === 'login'
                ? 'Accede a tu cuenta de Global Exchange'
                : 'Ingresa tu correo para recibir instrucciones'}
            </p>
          </div>

          {tab === 'login' ? (
            <form onSubmit={handleLogin}>
              <div style={{ marginBottom: 18 }}>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 6, fontFamily: 'DM Sans' }}>
                  Correo electrónico
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="ge-input"
                  placeholder="tu@correo.com"
                  required
                  autoComplete="email"
                />
              </div>
              <div style={{ marginBottom: 8 }}>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 6, fontFamily: 'DM Sans' }}>
                  Contraseña
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="ge-input"
                  placeholder="••••••••"
                  required
                  autoComplete="current-password"
                />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans', cursor: 'pointer' }}>
                  <input type="checkbox" style={{ accentColor: 'var(--primary)' }} />
                  Recordarme
                </label>
                <button type="button" onClick={() => setTab('forgot')} style={{
                  background: 'none', border: 'none', fontSize: 13, color: 'var(--primary)',
                  cursor: 'pointer', fontFamily: 'DM Sans', fontWeight: 500,
                }}>
                  ¿Olvidaste tu contraseña?
                </button>
              </div>

              {error && (
                <div style={{
                  background: 'var(--danger-bg)', border: '1px solid rgba(220,38,38,0.25)',
                  borderRadius: 8, padding: '10px 14px',
                  fontSize: 13, color: 'var(--danger)', fontFamily: 'DM Sans', marginBottom: 16,
                }}>
                  {error}
                </div>
              )}

              <button
                type="submit"
                className="ge-btn-primary"
                disabled={loading}
                style={{ width: '100%', padding: '13px', fontSize: 15, justifyContent: 'center' }}
              >
                {loading ? (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 16, height: 16, border: '2px solid rgba(255,255,255,0.4)', borderTopColor: '#fff', borderRadius: '50%', animation: 'spinSlow 0.7s linear infinite', display: 'inline-block' }} />
                    Verificando...
                  </span>
                ) : 'Iniciar sesión'}
              </button>

              {/* Register link */}
              <div style={{ marginTop: 20, textAlign: 'center' as const, fontSize: 14, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>
                ¿No tienes una cuenta?{' '}
                <Link to="/register" style={{
                  color: 'var(--primary)', fontWeight: 600,
                  textDecoration: 'none',
                }}
                  onMouseEnter={e => (e.currentTarget.style.textDecoration = 'underline')}
                  onMouseLeave={e => (e.currentTarget.style.textDecoration = 'none')}
                >
                  Registrarse
                </Link>
              </div>

              {/* Demo hint */}
              <div style={{ marginTop: 16, padding: '12px 16px', background: 'var(--primary-muted)', borderRadius: 8, fontSize: 12, color: 'var(--primary)', fontFamily: 'DM Sans', lineHeight: 1.6 }}>
                <strong>Demo:</strong> Usa el selector DEMO en el navbar para acceder a diferentes roles directamente.
              </div>
            </form>
          ) : (
            <div>
              <div style={{ marginBottom: 18 }}>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 6, fontFamily: 'DM Sans' }}>
                  Correo electrónico
                </label>
                <input type="email" className="ge-input" placeholder="tu@correo.com" />
              </div>
              <button className="ge-btn-primary" style={{ width: '100%', padding: '13px', fontSize: 15, justifyContent: 'center' }}>
                Enviar instrucciones
              </button>
              <button
                onClick={() => setTab('login')}
                className="ge-btn-ghost"
                style={{ width: '100%', justifyContent: 'center', marginTop: 12, fontSize: 14 }}
              >
                ← Volver al inicio de sesión
              </button>
            </div>
          )}

          <div style={{ marginTop: 32, paddingTop: 24, borderTop: '1px solid var(--border)', textAlign: 'center' as const, fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>
            ¿Problemas para acceder? Contacta al administrador del sistema.
          </div>
        </div>
      </div>
    </div>
  );
}
