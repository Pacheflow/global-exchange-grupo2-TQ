import { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth, type UserRole } from '../contexts/AuthContext';
import AppIcon from './icons/AppIcon';

const DEMO_ROLES: { label: string; role: UserRole; path: string }[] = [
  { label: 'Visitante', role: 'visitor', path: '/' },
  { label: 'Cliente (KNG S.A.)', role: 'client', path: '/dashboard' },
  { label: 'Administrador', role: 'admin', path: '/admin' },
  { label: 'Analista cambiario', role: 'analyst', path: '/analyst' },
  { label: 'Cajero / Operador', role: 'cashier', path: '/cashier' },
];

const BellIcon = ({ count }: { count: number }) => (
  <div style={{ position: 'relative' }}>
    <AppIcon name="bell" size={18} />
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
    : 'rgba(6, 11, 30, 0.92)';

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
          <div style={{ color: 'var(--primary)' }}><AppIcon name="globe" size={28} /></div>
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
          <Link to="/" className="ge-btn-ghost" style={{ marginLeft: 24, fontSize: 13, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <AppIcon name="back" size={15} /> Volver al sitio
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
            DEMO <AppIcon name="chevron-down" size={13} />
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
                    <AppIcon name="check" size={14} style={{ color: 'var(--primary)', marginLeft: 6, display: 'inline' }} />
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

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
              <AppIcon name="chevron-down" size={13} style={{ color: 'var(--text-3)' }} />
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
