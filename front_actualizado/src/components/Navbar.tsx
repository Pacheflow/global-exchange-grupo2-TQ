import { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTheme } from '../contexts/ThemeContext';
import { useAuth, type UserRole } from '../contexts/AuthContext';

const DEMO_ROLES: { label: string; role: UserRole; path: string }[] = [
  { label: 'Visitante', role: 'visitor', path: '/' },
  { label: 'Cliente (KNG S.A.)', role: 'client', path: '/dashboard' },
  { label: 'Administrador', role: 'admin', path: '/admin' },
  { label: 'Analista cambiario', role: 'analyst', path: '/analyst' },
  { label: 'Cajero / Operador', role: 'cashier', path: '/cashier' },
];

const GlobeLogo = () => (
  <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
    <circle cx="14" cy="14" r="12" stroke="currentColor" strokeWidth="1.5" />
    <ellipse cx="14" cy="14" rx="5.5" ry="12" stroke="currentColor" strokeWidth="1.5" />
    <line x1="2" y1="14" x2="26" y2="14" stroke="currentColor" strokeWidth="1.5" />
    <line x1="4" y1="8.5" x2="24" y2="8.5" stroke="currentColor" strokeWidth="1" strokeOpacity="0.6" />
    <line x1="4" y1="19.5" x2="24" y2="19.5" stroke="currentColor" strokeWidth="1" strokeOpacity="0.6" />
  </svg>
);

const SunIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <circle cx="12" cy="12" r="5" />
    <line x1="12" y1="1" x2="12" y2="3" />
    <line x1="12" y1="21" x2="12" y2="23" />
    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
    <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
    <line x1="1" y1="12" x2="3" y2="12" />
    <line x1="21" y1="12" x2="23" y2="12" />
    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
    <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
  </svg>
);

const MoonIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
);

const BellIcon = ({ count }: { count: number }) => (
  <div style={{ position: 'relative' }}>
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
    {count > 0 && (
      <span style={{
        position: 'absolute', top: -4, right: -4,
        background: 'var(--primary)', color: '#fff',
        borderRadius: '999px', fontSize: 9, fontWeight: 700,
        width: 14, height: 14, display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>{count}</span>
    )}
  </div>
);

export default function Navbar({ transparent = false }: { transparent?: boolean }) {
  const { isDark, toggleTheme } = useTheme();
  const { user, isLoggedIn, login, logout } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 50);
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const isLanding = location.pathname === '/';
  const isDashboard = !['/login', '/'].includes(location.pathname);

  const navBg = transparent && isLanding && !scrolled
    ? 'transparent'
    : isDark
      ? 'rgba(6, 11, 30, 0.92)'
      : 'rgba(240, 245, 255, 0.92)';

  const navBorder = transparent && isLanding && !scrolled
    ? 'transparent'
    : 'var(--border)';

  const navLinks = [
    { label: 'Inicio', href: '/#inicio' },
    { label: 'Cotizaciones', href: '/#cotizaciones' },
    { label: 'Conversor', href: '/#conversor' },
    { label: 'Seguridad', href: '/#seguridad' },
  ];

  const handleDemoRole = (role: UserRole, path: string) => {
    if (role === 'visitor') { logout(); navigate('/'); }
    else { login(role); navigate(path); }
    setDemoOpen(false);
  };

  return (
    <nav style={{
      position: 'fixed',
      top: 0, left: 0, right: 0,
      zIndex: 100,
      background: navBg,
      borderBottom: `1px solid ${navBorder}`,
      backdropFilter: scrolled || !isLanding ? 'blur(16px)' : 'none',
      transition: 'background 0.3s ease, border-color 0.3s ease, backdrop-filter 0.3s ease',
    }}>
      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '0 24px', display: 'flex', alignItems: 'center', height: 64, gap: 8 }}>
        {/* Logo */}
        <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none', color: 'var(--text)', flexShrink: 0 }}>
          <div style={{ color: 'var(--primary)' }}><GlobeLogo /></div>
          <div style={{ lineHeight: 1 }}>
            <span style={{ fontFamily: 'Fraunces, serif', fontWeight: 600, fontSize: 17, letterSpacing: '-0.02em' }}>
              GLOBAL
            </span>
            <span style={{ fontFamily: 'DM Sans, sans-serif', fontWeight: 300, fontSize: 12, color: 'var(--text-2)', display: 'block', letterSpacing: '0.12em' }}>
              EXCHANGE
            </span>
          </div>
        </Link>

        {/* Public nav links */}
        {!isDashboard && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 2, marginLeft: 32 }}>
            {navLinks.map(link => (
              <a key={link.href} href={link.href} className="ge-btn-ghost" style={{ fontSize: 14 }}>
                {link.label}
              </a>
            ))}
          </div>
        )}

        {/* Dashboard back link */}
        {isDashboard && (
          <Link to="/" className="ge-btn-ghost" style={{ marginLeft: 24, fontSize: 13 }}>
            ← Volver al sitio
          </Link>
        )}

        <div style={{ flex: 1 }} />

        {/* Demo mode selector */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setDemoOpen(o => !o)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: 'var(--primary-muted)',
              color: 'var(--primary)',
              border: '1px solid var(--primary)',
              borderRadius: 6,
              padding: '5px 10px',
              fontSize: 11,
              fontWeight: 600,
              fontFamily: 'DM Sans, sans-serif',
              cursor: 'pointer',
              letterSpacing: '0.04em',
            }}
          >
            DEMO ▾
          </button>
          {demoOpen && (
            <div className="ge-card" style={{
              position: 'absolute', top: 36, right: 0, minWidth: 220,
              padding: 6, zIndex: 200, boxShadow: 'var(--shadow-lg)',
            }}>
              <div style={{ padding: '6px 10px 4px', fontSize: 10, fontWeight: 600, color: 'var(--text-3)', letterSpacing: '0.08em' }}>
                CAMBIAR ROL
              </div>
              {DEMO_ROLES.map(r => (
                <button
                  key={r.role}
                  onClick={() => handleDemoRole(r.role, r.path)}
                  style={{
                    display: 'block', width: '100%', textAlign: 'left',
                    padding: '8px 10px', fontSize: 13, fontFamily: 'DM Sans, sans-serif',
                    color: 'var(--text)', background: 'transparent', border: 'none',
                    borderRadius: 6, cursor: 'pointer',
                    fontWeight: user?.role === r.role || (!user && r.role === 'visitor') ? 600 : 400,
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--primary-muted)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  {r.label}
                  {(user?.role === r.role || (!user && r.role === 'visitor')) && (
                    <span style={{ color: 'var(--primary)', marginLeft: 6 }}>✓</span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          className="ge-btn-ghost"
          style={{ padding: '7px 10px', color: 'var(--text-2)' }}
          title={isDark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'}
        >
          {isDark ? <SunIcon /> : <MoonIcon />}
        </button>

        {/* Notifications (logged in) */}
        {isLoggedIn && (
          <button className="ge-btn-ghost" style={{ padding: '7px 10px', color: 'var(--text-2)' }}>
            <BellIcon count={2} />
          </button>
        )}

        {/* Auth button */}
        {!isLoggedIn ? (
          <Link to="/login" className="ge-btn-primary" style={{ fontSize: 13, padding: '8px 18px' }}>
            Iniciar sesión
          </Link>
        ) : (
          <div style={{ position: 'relative' }}>
            <button
              onClick={() => setProfileOpen(o => !o)}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                background: 'var(--surface-2)', border: '1px solid var(--border)',
                borderRadius: 8, padding: '6px 12px 6px 8px',
                cursor: 'pointer', color: 'var(--text)',
                fontFamily: 'DM Sans, sans-serif', fontSize: 13,
              }}
            >
              <div style={{
                width: 28, height: 28, borderRadius: '50%',
                background: 'var(--primary)', color: '#fff',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700, flexShrink: 0,
              }}>
                {user?.name?.charAt(0) ?? 'U'}
              </div>
              <div style={{ lineHeight: 1.2, textAlign: 'left' }}>
                <div style={{ fontWeight: 600 }}>{user?.name?.split(' ')[0]}</div>
                <div style={{ fontSize: 10, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  {user?.role}
                </div>
              </div>
              <span style={{ color: 'var(--text-3)', fontSize: 10 }}>▾</span>
            </button>
            {profileOpen && (
              <div className="ge-card" style={{
                position: 'absolute', top: 44, right: 0, minWidth: 240,
                padding: 8, zIndex: 200, boxShadow: 'var(--shadow-lg)',
              }}>
                <div style={{ padding: '8px 12px 12px', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text)' }}>{user?.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 2 }}>{user?.email}</div>
                  {user?.activeClient && (
                    <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ fontSize: 11, color: 'var(--text-3)' }}>Cliente activo:</span>
                      <span style={{
                        fontSize: 11, fontWeight: 600, color: 'var(--primary)',
                        background: 'var(--primary-muted)', borderRadius: 4, padding: '1px 6px',
                      }}>
                        {user.activeClient}
                      </span>
                      {user.clientCategory && (
                        <span style={{
                          fontSize: 10, fontWeight: 700,
                          color: user.clientCategory === 'VIP' ? '#FBBF24' : 'var(--text-2)',
                          letterSpacing: '0.06em',
                        }}>
                          {user.clientCategory}
                        </span>
                      )}
                    </div>
                  )}
                </div>
                <div style={{ paddingTop: 6 }}>
                  {[
                    { label: 'Mi panel', path: '/dashboard' },
                    { label: 'Configuración', path: '#' },
                  ].map(item => (
                    <Link
                      key={item.label}
                      to={item.path}
                      className="ge-btn-ghost"
                      style={{ display: 'block', width: '100%', textAlign: 'left', borderRadius: 6, fontSize: 13 }}
                      onClick={() => setProfileOpen(false)}
                    >
                      {item.label}
                    </Link>
                  ))}
                  <div style={{ borderTop: '1px solid var(--border)', marginTop: 4, paddingTop: 4 }}>
                    <button
                      onClick={() => { logout(); navigate('/'); setProfileOpen(false); }}
                      className="ge-btn-ghost"
                      style={{ width: '100%', textAlign: 'left', color: 'var(--danger)', fontSize: 13 }}
                    >
                      Cerrar sesión
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Overlay to close dropdowns */}
      {(profileOpen || demoOpen) && (
        <div
          style={{ position: 'fixed', inset: 0, zIndex: 99 }}
          onClick={() => { setProfileOpen(false); setDemoOpen(false); }}
        />
      )}
    </nav>
  );
}
