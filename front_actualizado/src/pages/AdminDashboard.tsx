import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import Navbar from '../components/Navbar';
import Sidebar from '../components/Sidebar';
import StatusBadge from '../components/StatusBadge';
import { transactions, adminStats, currencies } from '../data/mockData';
import { useAuth } from '../contexts/AuthContext';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import DivisasCrud from '../components/crud/DivisasCrud';
import TasasCrud from '../components/crud/TasasCrud';
import PagosCrud from '../components/crud/PagosCrud';

const sidebarItems = [
  { icon: '◈', label: 'Dashboard', href: '/admin' },
  { icon: '👥', label: 'Usuarios', href: '/admin/usuarios' },
  { icon: '🏢', label: 'Clientes', href: '/admin/clientes' },
  { icon: '🔗', label: 'Asociaciones', href: '/admin/asociaciones' },
  { icon: '🎭', label: 'Roles / Permisos', href: '/admin/roles' },
  { icon: '💱', label: 'Divisas', href: '/admin/divisas' },
  { icon: '📊', label: 'Tasas', href: '/admin/tasas' },
  { icon: '💳', label: 'Medios de pago', href: '/admin/pagos' },
  { icon: '🗄', label: 'Cajas', href: '/admin/cajas' },
  { icon: '💰', label: 'Ganancias', href: '/admin/ganancias' },
  { icon: '📋', label: 'Reportes', href: '/admin/reportes' },
  { icon: '🔔', label: 'Notificaciones', href: '/admin/notificaciones', badge: 3 },
  { icon: '⚙', label: 'Configuración', href: '/admin/config' },
];

const gainByMonth = [
  { month: 'Mar', gain: 32_000_000 },
  { month: 'Abr', gain: 38_000_000 },
  { month: 'May', gain: 41_000_000 },
  { month: 'Jun', gain: 35_000_000 },
  { month: 'Jul', gain: 44_000_000 },
  { month: 'Ago', gain: 48_200_000 },
];

const gainByCurrency = [
  { name: 'USD', value: 38, color: '#3B5BFF' },
  { name: 'EUR', value: 28, color: '#22C55E' },
  { name: 'BRL', value: 20, color: '#FBBF24' },
  { name: 'ARS', value: 14, color: '#F87171' },
];

const clients = [
  { name: 'KNG S.A.', category: 'VIP', users: 3, ops: 47, status: 'Activo' },
  { name: 'Importadora del Norte', category: 'Corporativo', users: 2, ops: 28, status: 'Activo' },
  { name: 'Exportaciones Río S.R.L.', category: 'Corporativo', users: 1, ops: 15, status: 'Activo' },
  { name: 'María González', category: 'Minorista', users: 1, ops: 4, status: 'Activo' },
  { name: 'Tech Solutions PY', category: 'Corporativo', users: 2, ops: 9, status: 'Inactivo' },
];

const users = [
  { name: 'Laura Benítez', email: 'laura@...', role: 'client', clients: 2, status: 'Activo' },
  { name: 'Diego Ferreira', email: 'diego@...', role: 'analyst', clients: 0, status: 'Activo' },
  { name: 'Ana González', email: 'ana@...', role: 'cashier', clients: 0, status: 'Activo' },
  { name: 'Roberto Sánchez', email: 'roberto@...', role: 'client', clients: 1, status: 'Activo' },
  { name: 'Carlos Medina', email: 'carlos@...', role: 'admin', clients: 0, status: 'Activo' },
];

const ROLES = ['Administrador', 'Analista cambiario', 'Cajero / Operador', 'Usuario'];
const PERMISSIONS = [
  { perm: 'Ver cotizaciones',       admin: true,  analyst: true,  cashier: true,  user: true  },
  { perm: 'Actualizar tasas',       admin: true,  analyst: true,  cashier: false, user: false },
  { perm: 'Ver transacciones',      admin: true,  analyst: true,  cashier: true,  user: true  },
  { perm: 'Crear operación',        admin: true,  analyst: false, cashier: true,  user: false },
  { perm: 'Gestionar cajas',        admin: true,  analyst: false, cashier: true,  user: false },
  { perm: 'Ver ganancias',          admin: true,  analyst: true,  cashier: false, user: false },
  { perm: 'Gestionar usuarios',     admin: true,  analyst: false, cashier: false, user: false },
  { perm: 'Gestionar clientes',     admin: true,  analyst: false, cashier: false, user: false },
  { perm: 'Ver reportes completos', admin: true,  analyst: true,  cashier: false, user: false },
  { perm: 'Facturación',            admin: true,  analyst: false, cashier: false, user: false },
];

function KPI({ label, value, sub, icon }: { label: string; value: string; sub?: string; icon: string }) {
  return (
    <div className="ge-card" style={{ padding: '20px 22px', display: 'flex', gap: 14, alignItems: 'flex-start' }}>
      <div style={{
        width: 40, height: 40, borderRadius: 10,
        background: 'var(--primary-muted)', border: '1px solid rgba(59,91,255,0.2)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 18, flexShrink: 0,
      }}>
        {icon}
      </div>
      <div>
        <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 700, letterSpacing: '0.08em', fontFamily: 'DM Sans', marginBottom: 4 }}>{label}</div>
        <div style={{ fontFamily: 'JetBrains Mono', fontSize: 22, fontWeight: 600, color: 'var(--text)', lineHeight: 1 }}>{value}</div>
        {sub && <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'DM Sans', marginTop: 4 }}>{sub}</div>}
      </div>
    </div>
  );
}

export default function AdminDashboard() {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  // Parse active section from URL
  const pathParts = location.pathname.split('/').filter(Boolean);
  const currentSection = pathParts[1] || 'dashboard';

  const setActiveSection = (s: string) => {
    navigate(s === 'dashboard' ? '/admin' : `/admin/${s}`);
  };

  const activeSection = currentSection;

  const formatPYG = (n: number) => `${(n / 1_000_000).toFixed(1)}M PYG`;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
      <Navbar />
      <div style={{ display: 'flex', flex: 1 }}>
        <Sidebar items={sidebarItems} name={user?.name ?? 'Administrador'} role="Administrador" />

        <main style={{ flex: 1, padding: '80px 0 0', overflowX: 'hidden' }}>
          {/* Header */}
          <div style={{ padding: '24px 40px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <h1 style={{ fontFamily: 'Fraunces, serif', fontSize: 24, fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.02em' }}>
                Panel Administrador
              </h1>
              <p style={{ fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans', marginTop: 4 }}>
                31 de agosto de 2026 · Visión global del sistema
              </p>
            </div>
          </div>

          <div style={{ padding: '28px 40px' }}>
            {/* ── Dashboard ── */}
            {activeSection === 'dashboard' && (
              <div>
                {/* KPIs */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 24 }}>
                  <KPI label="USUARIOS ACTIVOS" value={`${adminStats.activeUsers}`} sub="en el sistema" icon="👥" />
                  <KPI label="CLIENTES" value={`${adminStats.clients}`} sub="registrados" icon="🏢" />
                  <KPI label="OPERACIONES HOY" value={`${adminStats.operationsToday}`} sub="↑ +3 vs. ayer" icon="⇄" />
                  <KPI label="GANANCIA MES" value={formatPYG(adminStats.gainMonth)} sub="Agosto 2026" icon="💰" />
                </div>

                {/* Second row */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 28 }}>
                  <KPI label="CAJAS ACTIVAS" value={`${adminStats.activeCaixas}/5`} sub="Turno abierto" icon="🗄" />
                  <KPI label="PENDIENTES" value={`${adminStats.pendingTransactions}`} sub="transacciones" icon="⏳" />
                  <KPI label="GANANCIA HOY" value={formatPYG(adminStats.gainToday)} sub="31/08/2026" icon="📈" />
                  <KPI label="OPERACIONES MES" value={`${adminStats.operationsMonth}`} sub="Agosto 2026" icon="📊" />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
                  {/* Gain chart */}
                  <div className="ge-card" style={{ padding: 24 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans', marginBottom: 20 }}>
                      Ganancia mensual (PYG)
                    </div>
                    <ResponsiveContainer width="100%" height={200}>
                      <BarChart data={gainByMonth}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                        <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--text-3)', fontFamily: 'DM Sans' }} />
                        <YAxis tickFormatter={v => `${(v / 1_000_000).toFixed(0)}M`} tick={{ fontSize: 10, fill: 'var(--text-3)', fontFamily: 'DM Sans' }} width={48} />
                        <Tooltip
                          formatter={(v) => [`${(Number(v) / 1_000_000).toFixed(1)}M PYG`, 'Ganancia']}
                          contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12, fontFamily: 'DM Sans' }}
                        />
                        <Bar dataKey="gain" fill="var(--primary)" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Gain by currency donut */}
                  <div className="ge-card" style={{ padding: 24 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans', marginBottom: 20 }}>
                      Ganancia por divisa (%)
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
                      <ResponsiveContainer width="50%" height={160}>
                        <PieChart>
                          <Pie data={gainByCurrency} cx="50%" cy="50%" innerRadius={45} outerRadius={70} dataKey="value" strokeWidth={0}>
                            {gainByCurrency.map((entry, index) => (
                              <Cell key={`cell-${index}`} fill={entry.color} />
                            ))}
                          </Pie>
                          <Tooltip formatter={(v) => [`${Number(v)}%`, '']} contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }} />
                        </PieChart>
                      </ResponsiveContainer>
                      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10 }}>
                        {gainByCurrency.map(item => (
                          <div key={item.name} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontFamily: 'DM Sans' }}>
                            <span style={{ width: 10, height: 10, borderRadius: 2, background: item.color, flexShrink: 0 }} />
                            <span style={{ flex: 1, color: 'var(--text-2)' }}>{item.name}</span>
                            <span style={{ fontFamily: 'JetBrains Mono', fontWeight: 600, color: 'var(--text)' }}>{item.value}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Recent transactions */}
                <div className="ge-card" style={{ overflow: 'hidden' }}>
                  <div style={{ padding: '18px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans' }}>Actividad reciente</div>
                    <button className="ge-btn-ghost" style={{ fontSize: 12 }}>Ver todo →</button>
                  </div>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--border)' }}>
                        {['ID', 'Fecha', 'Cliente', 'Tipo', 'Monto', 'Estado'].map(h => (
                          <th key={h} style={{ padding: '10px 20px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', fontFamily: 'DM Sans' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {transactions.slice(0, 4).map((t, i) => (
                        <tr key={t.id} className="table-row-hover" style={{ borderBottom: i < 3 ? '1px solid var(--border-subtle)' : 'none' }}>
                          <td style={{ padding: '13px 20px' }}><span style={{ fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--primary)' }}>{t.id}</span></td>
                          <td style={{ padding: '13px 20px' }}><span style={{ fontSize: 12, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>{t.date}</span></td>
                          <td style={{ padding: '13px 20px' }}><span style={{ fontSize: 13, color: 'var(--text)', fontFamily: 'DM Sans', fontWeight: 500 }}>{t.client}</span></td>
                          <td style={{ padding: '13px 20px' }}>
                            <span style={{ fontSize: 12, fontWeight: 700, color: t.type === 'Compra' ? 'var(--success)' : 'var(--danger)', fontFamily: 'DM Sans' }}>{t.type}</span>
                          </td>
                          <td style={{ padding: '13px 20px' }}><span style={{ fontFamily: 'JetBrains Mono', fontSize: 13, fontWeight: 500, color: 'var(--text)' }}>{t.amount.toLocaleString('es-PY')} {t.from}</span></td>
                          <td style={{ padding: '13px 20px' }}><StatusBadge status={t.status} size="sm" /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* ── Clientes ── */}
            {activeSection === 'clientes' && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
                  <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.02em' }}>Gestión de clientes</h2>
                  <button className="ge-btn-primary" style={{ fontSize: 13 }}>+ Nuevo cliente</button>
                </div>
                <div className="ge-card" style={{ overflow: 'hidden' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--border)' }}>
                        {['Cliente', 'Categoría', 'Usuarios', 'Operaciones', 'Estado', 'Acciones'].map(h => (
                          <th key={h} style={{ padding: '12px 20px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', fontFamily: 'DM Sans' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {clients.map((c, i) => (
                        <tr key={c.name} className="table-row-hover" style={{ borderBottom: i < clients.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}>
                          <td style={{ padding: '14px 20px' }}>
                            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans' }}>{c.name}</div>
                          </td>
                          <td style={{ padding: '14px 20px' }}>
                            <span style={{
                              fontSize: 11, fontWeight: 700, fontFamily: 'DM Sans', letterSpacing: '0.04em',
                              color: c.category === 'VIP' ? '#FBBF24' : c.category === 'Corporativo' ? 'var(--primary)' : 'var(--text-2)',
                              background: c.category === 'VIP' ? 'rgba(251,191,36,0.12)' : c.category === 'Corporativo' ? 'var(--primary-muted)' : 'var(--surface-2)',
                              borderRadius: 4, padding: '2px 8px',
                            }}>
                              {c.category}
                            </span>
                          </td>
                          <td style={{ padding: '14px 20px' }}><span style={{ fontFamily: 'JetBrains Mono', fontSize: 13, color: 'var(--text)' }}>{c.users}</span></td>
                          <td style={{ padding: '14px 20px' }}><span style={{ fontFamily: 'JetBrains Mono', fontSize: 13, color: 'var(--text)' }}>{c.ops}</span></td>
                          <td style={{ padding: '14px 20px' }}>
                            <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: c.status === 'Activo' ? 'var(--success)' : 'var(--text-3)', fontFamily: 'DM Sans', fontWeight: 600 }}>
                              <span style={{ width: 6, height: 6, borderRadius: '50%', background: c.status === 'Activo' ? 'var(--success)' : 'var(--text-3)' }} />
                              {c.status}
                            </span>
                          </td>
                          <td style={{ padding: '14px 20px' }}>
                            <div style={{ display: 'flex', gap: 4 }}>
                              {['Ver', 'Editar', 'Asociar'].map(a => (
                                <button key={a} className="ge-btn-ghost" style={{ fontSize: 11, padding: '3px 8px' }}>{a}</button>
                              ))}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* ── Usuarios ── */}
            {activeSection === 'usuarios' && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
                  <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.02em' }}>Gestión de usuarios</h2>
                  <button className="ge-btn-primary" style={{ fontSize: 13 }}>+ Nuevo usuario</button>
                </div>
                <div className="ge-card" style={{ overflow: 'hidden' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--border)' }}>
                        {['Nombre', 'Correo', 'Rol', 'Clientes', 'Estado', 'Acciones'].map(h => (
                          <th key={h} style={{ padding: '12px 20px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', fontFamily: 'DM Sans' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((u, i) => (
                        <tr key={u.name} className="table-row-hover" style={{ borderBottom: i < users.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}>
                          <td style={{ padding: '14px 20px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                              <div style={{ width: 30, height: 30, borderRadius: '50%', background: 'var(--primary)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700, flexShrink: 0 }}>
                                {u.name.charAt(0)}
                              </div>
                              <span style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)', fontFamily: 'DM Sans' }}>{u.name}</span>
                            </div>
                          </td>
                          <td style={{ padding: '14px 20px' }}><span style={{ fontSize: 12, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>{u.email}</span></td>
                          <td style={{ padding: '14px 20px' }}>
                            <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--primary)', background: 'var(--primary-muted)', borderRadius: 4, padding: '2px 8px', fontFamily: 'DM Sans', letterSpacing: '0.04em' }}>
                              {u.role}
                            </span>
                          </td>
                          <td style={{ padding: '14px 20px' }}><span style={{ fontFamily: 'JetBrains Mono', fontSize: 13, color: 'var(--text)' }}>{u.clients}</span></td>
                          <td style={{ padding: '14px 20px' }}>
                            <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--success)', fontFamily: 'DM Sans', fontWeight: 600 }}>
                              <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--success)' }} />
                              {u.status}
                            </span>
                          </td>
                          <td style={{ padding: '14px 20px' }}>
                            <div style={{ display: 'flex', gap: 4 }}>
                              {['Ver', 'Editar'].map(a => (
                                <button key={a} className="ge-btn-ghost" style={{ fontSize: 11, padding: '3px 8px' }}>{a}</button>
                              ))}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* ── Roles / Permisos ── */}
            {activeSection === 'roles' && (
              <div>
                <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.02em', marginBottom: 24 }}>
                  Roles y permisos
                </h2>
                <div className="ge-card" style={{ overflow: 'hidden' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--border)' }}>
                        <th style={{ padding: '14px 20px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', fontFamily: 'DM Sans', width: '30%' }}>
                          PERMISO
                        </th>
                        {ROLES.map(r => (
                          <th key={r} style={{ padding: '14px 16px', textAlign: 'center', fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.06em', fontFamily: 'DM Sans' }}>
                            {r}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {PERMISSIONS.map((p, i) => (
                        <tr key={p.perm} className="table-row-hover" style={{ borderBottom: i < PERMISSIONS.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}>
                          <td style={{ padding: '12px 20px', fontSize: 13, color: 'var(--text)', fontFamily: 'DM Sans' }}>
                            {p.perm}
                          </td>
                          {[p.admin, p.analyst, p.cashier, p.user].map((allowed, j) => (
                            <td key={j} style={{ padding: '12px 16px', textAlign: 'center' }}>
                              {allowed ? (
                                <span style={{ fontSize: 16, color: 'var(--success)' }}>✓</span>
                              ) : (
                                <span style={{ fontSize: 14, color: 'var(--border)' }}>—</span>
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* ── Divisas ── */}
            {activeSection === 'divisas' && <DivisasCrud />}

            {/* ── Tasas ── */}
            {activeSection === 'tasas' && <TasasCrud />}

            {/* ── Pagos ── */}
            {activeSection === 'pagos' && <PagosCrud />}

            {/* ── Asociaciones ── */}
            {activeSection === 'asociaciones' && (
              <div className="ge-card" style={{ padding: 24 }}>
                <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 18, color: 'var(--text)', marginBottom: 16 }}>Asociaciones Comerciales</h3>
                <p style={{ fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>Módulo en desarrollo. Aquí se podrán gestionar alianzas y asociaciones comerciales con entidades bancarias o empresas.</p>
              </div>
            )}

            {/* ── Cajas ── */}
            {activeSection === 'cajas' && (
              <div className="ge-card" style={{ padding: 24 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
                  <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 18, color: 'var(--text)' }}>Gestión de Cajas</h3>
                  <button className="ge-btn-primary" style={{ padding: '6px 12px', fontSize: 12 }}>+ Nueva Caja</button>
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)' }}>
                      <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 10, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>ID</th>
                      <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 10, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>SUCURSAL</th>
                      <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 10, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>ESTADO</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td style={{ padding: '12px 16px', fontSize: 13 }}>CAJA-01</td>
                      <td style={{ padding: '12px 16px', fontSize: 13 }}>Central - Asunción</td>
                      <td style={{ padding: '12px 16px', fontSize: 13 }}><span style={{ color: 'var(--success)' }}>Abierta</span></td>
                    </tr>
                    <tr>
                      <td style={{ padding: '12px 16px', fontSize: 13 }}>CAJA-02</td>
                      <td style={{ padding: '12px 16px', fontSize: 13 }}>CDE - KM4</td>
                      <td style={{ padding: '12px 16px', fontSize: 13 }}><span style={{ color: 'var(--danger)' }}>Cerrada</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}

            {/* ── Reportes ── */}
            {activeSection === 'reportes' && (
              <div className="ge-card" style={{ padding: 24 }}>
                <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 18, color: 'var(--text)', marginBottom: 16 }}>Reportes Generales</h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                  <div style={{ border: '1px solid var(--border)', padding: 16, borderRadius: 8 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Cierre de Cajas Mensual</div>
                    <button className="ge-btn-outline" style={{ fontSize: 12 }}>Descargar PDF</button>
                  </div>
                  <div style={{ border: '1px solid var(--border)', padding: 16, borderRadius: 8 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Auditoría de Tasas</div>
                    <button className="ge-btn-outline" style={{ fontSize: 12 }}>Descargar CSV</button>
                  </div>
                </div>
              </div>
            )}

            {/* ── Notificaciones ── */}
            {activeSection === 'notificaciones' && (
              <div className="ge-card" style={{ padding: 24 }}>
                <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 18, color: 'var(--text)', marginBottom: 16 }}>Centro de Notificaciones</h3>
                <div style={{ borderBottom: '1px solid var(--border-subtle)', paddingBottom: 12, marginBottom: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>Tasa de USD/PYG con alta volatilidad</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>Hace 1 hora</div>
                </div>
                <div style={{ borderBottom: '1px solid var(--border-subtle)', paddingBottom: 12, marginBottom: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>Cierre de CAJA-02 inusual</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>Ayer, 18:30</div>
                </div>
              </div>
            )}

            {/* ── Configuración ── */}
            {activeSection === 'config' && (
              <div className="ge-card" style={{ padding: 24 }}>
                <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 18, color: 'var(--text)', marginBottom: 16 }}>Configuración del Sistema</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                  <div>
                    <label style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>Nombre de la Entidad</label>
                    <input type="text" className="ge-input" defaultValue="Global Exchange" style={{ maxWidth: 300 }} />
                  </div>
                  <div>
                    <label style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>Moneda Base</label>
                    <select className="ge-input" style={{ maxWidth: 300, cursor: 'pointer' }}>
                      <option>PYG - Guaraní</option>
                      <option>USD - Dólar</option>
                    </select>
                  </div>
                  <button className="ge-btn-primary" style={{ width: 'fit-content' }}>Guardar Cambios</button>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
