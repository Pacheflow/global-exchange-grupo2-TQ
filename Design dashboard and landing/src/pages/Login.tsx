import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import LiveExchangeBoard from '../components/LiveExchangeBoard';
import { useAuth } from '../contexts/AuthContext';
import AppIcon from '../components/icons/AppIcon';

export default function Login() {
  const { login } = useAuth();
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
              <AppIcon name="globe" size={28} />
            </div>
            <div style={{ lineHeight: 1 }}>
              <div style={{ fontFamily: 'Fraunces, serif', fontWeight: 600, fontSize: 18, letterSpacing: '-0.02em', color: '#E8F2FF' }}>GLOBAL</div>
              <div style={{ fontFamily: 'DM Sans, sans-serif', fontWeight: 300, fontSize: 11, color: '#5A7AAC', letterSpacing: '0.15em' }}>EXCHANGE</div>
            </div>
          </Link>
        </div>

        {/* Live Exchange Board */}
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 40px', position: 'relative' }}>
          <div style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
            <LiveExchangeBoard variant="auth" animate />
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
                style={{ width: '100%', justifyContent: 'center', marginTop: 12, fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}
              >
                <AppIcon name="back" size={15} /> Volver al inicio de sesión
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
