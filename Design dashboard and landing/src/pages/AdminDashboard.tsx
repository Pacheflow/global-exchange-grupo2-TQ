import { useState } from 'react';
import Navbar from '../components/Navbar';
import Sidebar from '../components/Sidebar';
import StatusBadge from '../components/StatusBadge';
import { transactions, adminStats, currencies } from '../data/mockData';
import { useAuth } from '../contexts/AuthContext';
import AppIcon, { type AppIconName } from '../components/icons/AppIcon';
import CurrencyIcon from '../components/icons/CurrencyIcon';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';

const sidebarItems = [
  { icon: <AppIcon name="dashboard" />, label: 'Dashboard', href: '/admin' },
  { icon: <AppIcon name="users" />, label: 'Usuarios', href: '/admin/usuarios' },
  { icon: <AppIcon name="building" />, label: 'Clientes', href: '/admin/clientes' },
  { icon: <AppIcon name="association" />, label: 'Asociaciones', href: '/admin/asociaciones' },
  { icon: <AppIcon name="roles" />, label: 'Roles / Permisos', href: '/admin/roles' },
  { icon: <AppIcon name="currency" />, label: 'Divisas', href: '/admin/divisas' },
  { icon: <AppIcon name="chart" />, label: 'Tasas', href: '/admin/tasas' },
  { icon: <AppIcon name="payment" />, label: 'Medios de pago', href: '/admin/pagos' },
  { icon: <AppIcon name="vault" />, label: 'Cajas', href: '/admin/cajas' },
  { icon: <AppIcon name="earnings" />, label: 'Ganancias', href: '/admin/ganancias' },
  { icon: <AppIcon name="reports" />, label: 'Reportes', href: '/admin/reportes' },
  { icon: <AppIcon name="bell" />, label: 'Notificaciones', href: '/admin/notificaciones', badge: 3 },
  { icon: <AppIcon name="settings" />, label: 'Configuración', href: '/admin/config' },
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

function KPI({ label, value, sub, icon }: { label: string; value: string; sub?: string; icon: AppIconName }) {
  return (
    <div className="ge-card" style={{ padding: '20px 22px', display: 'flex', gap: 14, alignItems: 'flex-start' }}>
      <div style={{
        width: 40, height: 40, borderRadius: 10,
        background: 'var(--primary-muted)', border: '1px solid rgba(59,91,255,0.2)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 18, flexShrink: 0,
      }}>
        <AppIcon name={icon} size={20} />
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
  const [activeSection, setActiveSection] = useState<'dashboard' | 'clientes' | 'usuarios' | 'roles' | 'divisas'>('dashboard');

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
            {/* Section tabs */}
            <div style={{ display: 'flex', gap: 4, background: 'var(--surface-2)', borderRadius: 8, padding: 4, border: '1px solid var(--border)' }}>
              {(['dashboard', 'clientes', 'usuarios', 'roles', 'divisas'] as const).map(s => (
                <button key={s} onClick={() => setActiveSection(s)} style={{
                  padding: '6px 14px', borderRadius: 6, border: 'none',
                  background: activeSection === s ? 'var(--primary)' : 'transparent',
                  color: activeSection === s ? '#fff' : 'var(--text-2)',
                  fontFamily: 'DM Sans', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                  textTransform: 'capitalize',
                }}>
                  {s}
                </button>
              ))}
            </div>
          </div>

          <div style={{ padding: '28px 40px' }}>
            {/* ── Dashboard ── */}
            {activeSection === 'dashboard' && (
              <div>
                {/* KPIs */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 24 }}>
                  <KPI label="USUARIOS ACTIVOS" value={`${adminStats.activeUsers}`} sub="en el sistema" icon="users" />
                  <KPI label="CLIENTES" value={`${adminStats.clients}`} sub="registrados" icon="building" />
                  <KPI label="OPERACIONES HOY" value={`${adminStats.operationsToday}`} sub="+3 vs. ayer" icon="exchange" />
                  <KPI label="GANANCIA MES" value={formatPYG(adminStats.gainMonth)} sub="Agosto 2026" icon="earnings" />
                </div>

                {/* Second row */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 28 }}>
                  <KPI label="CAJAS ACTIVAS" value={`${adminStats.activeCaixas}/5`} sub="Turno abierto" icon="vault" />
                  <KPI label="PENDIENTES" value={`${adminStats.pendingTransactions}`} sub="transacciones" icon="pending" />
                  <KPI label="GANANCIA HOY" value={formatPYG(adminStats.gainToday)} sub="31/08/2026" icon="up" />
                  <KPI label="OPERACIONES MES" value={`${adminStats.operationsMonth}`} sub="Agosto 2026" icon="chart" />
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
                    <button className="ge-btn-ghost" style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 5 }}>Ver todo <AppIcon name="forward" size={13} /></button>
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
                                <AppIcon name="check" size={16} style={{ color: 'var(--success)', margin: '0 auto' }} />
                              ) : (
                                <AppIcon name="neutral" size={14} style={{ color: 'var(--border)', margin: '0 auto' }} />
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
            {activeSection === 'divisas' && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
                  <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.02em' }}>Gestión de divisas</h2>
                  <button className="ge-btn-primary" style={{ fontSize: 13 }}>+ Nueva divisa</button>
                </div>
                <div className="ge-card" style={{ overflow: 'hidden' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--border)' }}>
                        {['', 'Código', 'Nombre', 'Símbolo', 'Estado', 'Acciones'].map(h => (
                          <th key={h} style={{ padding: '12px 20px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', fontFamily: 'DM Sans' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {currencies.map((c, i) => (
                        <tr key={c.code} className="table-row-hover" style={{ borderBottom: i < currencies.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}>
                          <td style={{ padding: '14px 20px' }}><CurrencyIcon code={c.code} size={22} /></td>
                          <td style={{ padding: '14px 20px' }}><span style={{ fontFamily: 'JetBrains Mono', fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>{c.code}</span></td>
                          <td style={{ padding: '14px 20px' }}><span style={{ fontSize: 14, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>{c.name}</span></td>
                          <td style={{ padding: '14px 20px' }}><span style={{ fontFamily: 'JetBrains Mono', fontSize: 13, color: 'var(--text-2)' }}>
                            {c.code === 'USD' ? '$' : c.code === 'EUR' ? '€' : c.code === 'BRL' ? 'R$' : c.code === 'ARS' ? 'A$' : '₲'}
                          </span></td>
                          <td style={{ padding: '14px 20px' }}>
                            <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--success)', fontFamily: 'DM Sans', fontWeight: 600 }}>
                              <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--success)' }} />
                              Activa
                            </span>
                          </td>
                          <td style={{ padding: '14px 20px' }}>
                            <div style={{ display: 'flex', gap: 4 }}>
                              <button className="ge-btn-ghost" style={{ fontSize: 11, padding: '3px 8px' }}>Editar</button>
                              <button className="ge-btn-ghost" style={{ fontSize: 11, padding: '3px 8px', color: 'var(--danger)' }}>Desactivar</button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
