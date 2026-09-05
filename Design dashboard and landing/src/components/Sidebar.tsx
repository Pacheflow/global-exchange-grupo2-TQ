import { Link, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';

interface SidebarItem {
  icon: ReactNode;
  label: string;
  href: string;
  badge?: number;
}

interface SidebarProps {
  items: SidebarItem[];
  role?: string;
  name?: string;
}

export default function Sidebar({ items, role, name }: SidebarProps) {
  const location = useLocation();

  return (
    <aside style={{
      width: 220,
      flexShrink: 0,
      background: 'var(--surface)',
      borderRight: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      position: 'sticky',
      top: 0,
      overflowY: 'auto',
    }}>
      {/* User info block */}
      {name && (
        <div style={{ padding: '80px 16px 20px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: '50%',
              background: 'var(--primary)', color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 14, fontWeight: 700, flexShrink: 0,
            }}>
              {name.charAt(0)}
            </div>
            <div style={{ lineHeight: 1.3, overflow: 'hidden' }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {name}
              </div>
              {role && (
                <div style={{ fontSize: 10, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  {role}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Nav items */}
      <nav style={{ flex: 1, padding: '12px 8px' }}>
        {items.map(item => {
          const isActive = location.pathname === item.href ||
            (item.href !== '/' && location.pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              to={item.href}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '9px 12px',
                borderRadius: 8, marginBottom: 2,
                textDecoration: 'none',
                color: isActive ? 'var(--primary)' : 'var(--text-2)',
                background: isActive ? 'var(--primary-muted)' : 'transparent',
                fontSize: 13, fontWeight: isActive ? 600 : 400,
                fontFamily: 'DM Sans, sans-serif',
                transition: 'all 0.15s ease',
                position: 'relative',
              }}
              onMouseEnter={e => {
                if (!isActive) {
                  (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)';
                  (e.currentTarget as HTMLElement).style.color = 'var(--text)';
                }
              }}
              onMouseLeave={e => {
                if (!isActive) {
                  (e.currentTarget as HTMLElement).style.background = 'transparent';
                  (e.currentTarget as HTMLElement).style.color = 'var(--text-2)';
                }
              }}
            >
              {isActive && (
                <span style={{
                  position: 'absolute', left: 0, top: 4, bottom: 4,
                  width: 3, borderRadius: '0 2px 2px 0',
                  background: 'var(--primary)',
                }} />
              )}
              <span style={{ opacity: isActive ? 1 : 0.7, flexShrink: 0 }}>{item.icon}</span>
              <span style={{ flex: 1 }}>{item.label}</span>
              {item.badge !== undefined && item.badge > 0 && (
                <span style={{
                  background: 'var(--primary)', color: '#fff',
                  borderRadius: 999, fontSize: 10, fontWeight: 700,
                  padding: '1px 6px', minWidth: 18, textAlign: 'center',
                }}>
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Version tag */}
      <div style={{ padding: '12px 20px', borderTop: '1px solid var(--border)' }}>
        <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.06em' }}>
          GLOBAL EXCHANGE · v1.0
        </div>
      </div>
    </aside>
  );
}
