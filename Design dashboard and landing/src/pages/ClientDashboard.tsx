import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Navbar from '../components/Navbar';
import Sidebar from '../components/Sidebar';
import StatusBadge from '../components/StatusBadge';
import Sparkline from '../components/Sparkline';
import { transactions, notifications, currencies, exchangeRates } from '../data/mockData';
import { useAuth } from '../contexts/AuthContext';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import AppIcon from '../components/icons/AppIcon';
import CurrencyIcon from '../components/icons/CurrencyIcon';

const historyData = [
  { date: 'Ago 1', usd: 7380, eur: 8050 },
  { date: 'Ago 8', usd: 7400, eur: 8080 },
  { date: 'Ago 15', usd: 7420, eur: 8100 },
  { date: 'Ago 22', usd: 7450, eur: 8090 },
  { date: 'Ago 31', usd: 7480, eur: 8120 },
];

const sidebarItems = [
  { icon: <AppIcon name="dashboard" />, label: 'Resumen', href: '/dashboard' },
  { icon: <AppIcon name="exchange" />, label: 'Operaciones', href: '/dashboard/operaciones' },
  { icon: <AppIcon name="movements" />, label: 'Transacciones', href: '/dashboard/transacciones' },
  { icon: <AppIcon name="file" />, label: 'Facturas', href: '/dashboard/facturas' },
  { icon: <AppIcon name="bell" />, label: 'Notificaciones', href: '/dashboard/notificaciones', badge: 2 },
  { icon: <AppIcon name="building" />, label: 'Mi cliente', href: '/dashboard/cliente' },
  { icon: <AppIcon name="settings" />, label: 'Configuración', href: '/dashboard/config' },
];

function StatCard({ label, value, sub, color, trend }: { label: string; value: string; sub?: string; color?: string; trend?: 'up' | 'down' }) {
  return (
    <div className="ge-card" style={{ padding: '22px 24px' }}>
      <div style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600, letterSpacing: '0.08em', fontFamily: 'DM Sans', marginBottom: 10 }}>
        {label}
      </div>
      <div style={{ fontFamily: 'JetBrains Mono', fontSize: 24, fontWeight: 600, color: color ?? 'var(--text)', lineHeight: 1 }}>
        {value}
      </div>
      {sub && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Sans', display: 'flex', alignItems: 'center', gap: 4 }}>
        {trend && <AppIcon name={trend} size={13} />}{sub}
      </div>}
    </div>
  );
}

export default function ClientDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'resumen' | 'operaciones' | 'transacciones'>('resumen');
  const [buyAmount, setBuyAmount] = useState('');
  const [buyFrom, setBuyFrom] = useState('PYG');
  const [buyTo, setBuyTo] = useState('USD');
  const [showConfirm, setShowConfirm] = useState(false);
  const [operationDone, setOperationDone] = useState(false);

  const clients = ['KNG S.A.', 'Importadora del Norte'];
  const [activeClient, setActiveClient] = useState(user?.activeClient ?? 'KNG S.A.');

  const handleBuySubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setShowConfirm(true);
  };

  const handleConfirm = () => {
    setShowConfirm(false);
    setOperationDone(true);
    setTimeout(() => setOperationDone(false), 4000);
    setBuyAmount('');
  };

  const buyResult = parseFloat(buyAmount || '0') * (exchangeRates[buyFrom]?.[buyTo] ?? 1);
  const buyRate = exchangeRates[buyFrom]?.[buyTo] ?? 1;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
      <Navbar />
      <div style={{ display: 'flex', flex: 1 }}>
        <Sidebar
          items={sidebarItems}
          name={user?.name ?? 'Usuario'}
          role={user?.activeClient ?? 'Sin cliente'}
        />

        <main style={{ flex: 1, padding: '80px 0 0', overflowX: 'hidden' }}>
          {/* Header bar */}
          <div style={{ padding: '24px 40px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
            <div>
              <h1 style={{ fontFamily: 'Fraunces, serif', fontSize: 24, fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.02em' }}>
                Bienvenido, {user?.name?.split(' ')[0]}
              </h1>
              <p style={{ fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans', marginTop: 4 }}>
                31 de agosto de 2026 · Asunción, Paraguay
              </p>
            </div>
            {/* Client selector */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>Cliente activo:</div>
              <select
                value={activeClient}
                onChange={e => setActiveClient(e.target.value)}
                className="ge-input"
                style={{ width: 'auto', fontWeight: 600, paddingRight: 32, cursor: 'pointer', fontSize: 13 }}
              >
                {clients.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
              <span style={{
                fontSize: 10, fontWeight: 700, letterSpacing: '0.06em',
                color: '#FBBF24', background: 'rgba(251,191,36,0.12)',
                borderRadius: 4, padding: '2px 8px', fontFamily: 'DM Sans',
              }}>
                {user?.clientCategory ?? 'Corporativo'}
              </span>
            </div>
          </div>

          {/* Tabs */}
          <div style={{ padding: '0 40px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 4 }}>
            {(['resumen', 'operaciones', 'transacciones'] as const).map(t => (
              <button
                key={t}
                onClick={() => setActiveTab(t)}
                style={{
                  padding: '14px 20px', background: 'transparent', border: 'none',
                  borderBottom: activeTab === t ? '2px solid var(--primary)' : '2px solid transparent',
                  color: activeTab === t ? 'var(--primary)' : 'var(--text-2)',
                  fontFamily: 'DM Sans', fontSize: 13, fontWeight: activeTab === t ? 600 : 400,
                  cursor: 'pointer', marginBottom: -1, transition: 'all 0.15s',
                  textTransform: 'capitalize',
                }}
              >
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>

          <div style={{ padding: '32px 40px' }}>
            {/* ── Resumen ── */}
            {activeTab === 'resumen' && (
              <div>
                {/* Stat cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 28 }}>
                  <StatCard label="OPERACIONES (MES)" value="12" sub="3 más que el mes anterior" trend="up" />
                  <StatCard label="ÚLTIMO MONTO USD" value="2.500" sub="Venta · 30 ago" />
                  <StatCard label="TRANSACCIONES" value="8" sub="PAGADAS este mes" color="var(--success)" />
                  <StatCard label="PENDIENTES" value="1" sub="Por confirmar" color="var(--warning)" />
                </div>

                {/* Main grid */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
                  {/* Quick actions */}
                  <div className="ge-card" style={{ padding: 24 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans', marginBottom: 16 }}>Accesos rápidos</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                      {[
                        { icon: 'buy' as const, label: 'Comprar divisas', color: 'var(--success)' },
                        { icon: 'sell' as const, label: 'Vender divisas', color: 'var(--danger)' },
                        { icon: 'exchange' as const, label: 'Convertir', color: 'var(--primary)' },
                        { icon: 'history' as const, label: 'Ver historial', color: 'var(--text-2)' },
                      ].map(a => (
                        <button
                          key={a.label}
                          onClick={() => a.label !== 'Ver historial' ? setActiveTab('operaciones') : setActiveTab('transacciones')}
                          style={{
                            display: 'flex', alignItems: 'center', gap: 10,
                            padding: '14px 16px', border: '1px solid var(--border)',
                            borderRadius: 8, background: 'var(--surface-2)',
                            cursor: 'pointer', color: 'var(--text)', fontFamily: 'DM Sans',
                            fontSize: 13, fontWeight: 500,
                            transition: 'all 0.15s',
                          }}
                          onMouseEnter={e => {
                            (e.currentTarget as HTMLElement).style.borderColor = 'var(--primary)';
                            (e.currentTarget as HTMLElement).style.background = 'var(--primary-muted)';
                          }}
                          onMouseLeave={e => {
                            (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)';
                            (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)';
                          }}
                        >
                          <AppIcon name={a.icon} size={20} style={{ color: a.color }} />
                          {a.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Recent notifications */}
                  <div className="ge-card" style={{ padding: 24 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans', marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      Notificaciones
                      <span style={{ fontSize: 11, background: 'var(--primary)', color: '#fff', borderRadius: 999, padding: '1px 7px', fontWeight: 700 }}>2</span>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                      {notifications.slice(0, 4).map(n => (
                        <div key={n.id} style={{
                          display: 'flex', gap: 12, padding: '10px 12px',
                          background: n.read ? 'transparent' : 'var(--primary-muted)',
                          borderRadius: 8, borderLeft: `3px solid ${n.type === 'success' ? 'var(--success)' : n.type === 'warning' ? 'var(--warning)' : 'var(--primary)'}`,
                        }}>
                          <div style={{ flex: 1 }}>
                            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans' }}>{n.title}</div>
                            <div style={{ fontSize: 11, color: 'var(--text-2)', fontFamily: 'DM Sans', marginTop: 2 }}>{n.message}</div>
                          </div>
                          <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'DM Sans', whiteSpace: 'nowrap', paddingTop: 2 }}>{n.time}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Rate chart */}
                  <div className="ge-card" style={{ padding: 24 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans', marginBottom: 20 }}>Evolución de tasas · Agosto 2026</div>
                    <ResponsiveContainer width="100%" height={180}>
                      <LineChart data={historyData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                        <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-3)', fontFamily: 'DM Sans' }} />
                        <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10, fill: 'var(--text-3)', fontFamily: 'DM Sans' }} width={60} />
                        <Tooltip
                          contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12, fontFamily: 'DM Sans' }}
                          labelStyle={{ color: 'var(--text-2)' }}
                        />
                        <Line type="monotone" dataKey="usd" stroke="#3B5BFF" strokeWidth={2} dot={false} name="USD/PYG" />
                        <Line type="monotone" dataKey="eur" stroke="#22C55E" strokeWidth={2} dot={false} name="EUR/PYG" />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Cotizaciones del día mini */}
                  <div className="ge-card" style={{ padding: 24 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans', marginBottom: 16 }}>Cotizaciones del día</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {currencies.filter(c => c.code !== 'PYG').map(c => (
                        <div key={c.code} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                          <CurrencyIcon code={c.code} size={18} />
                          <div style={{ flex: 1 }}>
                            <div style={{ fontFamily: 'JetBrains Mono', fontWeight: 700, fontSize: 13, color: 'var(--text)' }}>{c.code}</div>
                          </div>
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ fontFamily: 'JetBrains Mono', fontSize: 13, color: 'var(--text)' }}>
                              {c.buy.toLocaleString('es-PY')}
                            </div>
                            <div style={{ fontSize: 10, color: c.trend === 'up' ? 'var(--success)' : c.trend === 'down' ? 'var(--danger)' : 'var(--text-3)', fontFamily: 'DM Sans' }}>
                              {c.change >= 0 ? '+' : ''}{c.change.toFixed(2)}%
                            </div>
                          </div>
                          <Sparkline data={c.sparkData} trend={c.trend} width={60} height={28} />
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* ── Operaciones ── */}
            {activeTab === 'operaciones' && (
              <div style={{ maxWidth: 640 }}>
                <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 500, color: 'var(--text)', marginBottom: 24, letterSpacing: '-0.02em' }}>
                  Nueva operación
                </h2>

                {operationDone && (
                  <div style={{
                    background: 'var(--success-bg)', border: '1px solid rgba(34,197,94,0.3)',
                    borderRadius: 10, padding: '16px 20px', marginBottom: 24,
                    display: 'flex', alignItems: 'center', gap: 12,
                    fontSize: 14, color: 'var(--success)', fontFamily: 'DM Sans', fontWeight: 600,
                  }}>
                    <AppIcon name="confirmation" size={20} />
                    Operación registrada exitosamente. Recibirás una confirmación pronto.
                  </div>
                )}

                <div className="ge-card" style={{ padding: 28 }}>
                  <div style={{ display: 'flex', gap: 4, marginBottom: 24, background: 'var(--surface-2)', borderRadius: 8, padding: 4, border: '1px solid var(--border)', width: 'fit-content' }}>
                    {['Comprar divisas', 'Vender divisas'].map(t => (
                      <button key={t} style={{
                        padding: '7px 16px', borderRadius: 6, border: 'none',
                        background: t === 'Comprar divisas' ? 'var(--primary)' : 'transparent',
                        color: t === 'Comprar divisas' ? '#fff' : 'var(--text-2)',
                        fontFamily: 'DM Sans', fontSize: 13, fontWeight: 600, cursor: 'pointer',
                      }}>
                        {t}
                      </button>
                    ))}
                  </div>

                  <form onSubmit={handleBuySubmit}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
                      <div>
                        <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 6, fontFamily: 'DM Sans' }}>
                          MONEDA ORIGEN
                        </label>
                        <select value={buyFrom} onChange={e => setBuyFrom(e.target.value)} className="ge-input" style={{ cursor: 'pointer' }}>
                          {currencies.map(c => <option key={c.code} value={c.code}>{c.code} — {c.name}</option>)}
                        </select>
                      </div>
                      <div>
                        <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 6, fontFamily: 'DM Sans' }}>
                          MONEDA DESTINO
                        </label>
                        <select value={buyTo} onChange={e => setBuyTo(e.target.value)} className="ge-input" style={{ cursor: 'pointer' }}>
                          {currencies.map(c => <option key={c.code} value={c.code}>{c.code} — {c.name}</option>)}
                        </select>
                      </div>
                    </div>

                    <div style={{ marginBottom: 16 }}>
                      <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 6, fontFamily: 'DM Sans' }}>
                        MONTO
                      </label>
                      <input
                        type="number"
                        value={buyAmount}
                        onChange={e => setBuyAmount(e.target.value)}
                        className="ge-input"
                        placeholder="0"
                        style={{ fontFamily: 'JetBrains Mono', fontSize: 18 }}
                        required
                        min="1"
                      />
                    </div>

                    <div style={{ marginBottom: 24 }}>
                      <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 6, fontFamily: 'DM Sans' }}>
                        MEDIO DE PAGO
                      </label>
                      <select className="ge-input" style={{ cursor: 'pointer' }}>
                        <option>Cuenta bancaria</option>
                        <option>Billetera electrónica</option>
                      </select>
                    </div>

                    {/* Summary */}
                    {buyAmount && parseFloat(buyAmount) > 0 && (
                      <div style={{ background: 'var(--surface-2)', borderRadius: 10, padding: '16px 20px', marginBottom: 20, border: '1px solid var(--border)' }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 12, fontFamily: 'DM Sans' }}>
                          RESUMEN DE OPERACIÓN
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                          {[
                            { label: 'Monto entregado', value: `${parseFloat(buyAmount).toLocaleString('es-PY')} ${buyFrom}` },
                            { label: 'Monto a recibir', value: `${buyResult.toLocaleString('es-PY', { maximumFractionDigits: buyResult < 100 ? 4 : 0 })} ${buyTo}` },
                            { label: 'Tipo de cambio', value: `1 ${buyFrom} = ${buyRate.toLocaleString('es-PY', { maximumFractionDigits: 4 })} ${buyTo}` },
                            { label: 'Cliente', value: activeClient },
                          ].map(row => (
                            <div key={row.label}>
                              <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'DM Sans', marginBottom: 2 }}>{row.label}</div>
                              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'JetBrains Mono' }}>{row.value}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <button type="submit" className="ge-btn-primary" style={{ width: '100%', padding: '13px', fontSize: 15, justifyContent: 'center', display: 'flex', alignItems: 'center', gap: 6 }}>
                      Continuar <AppIcon name="forward" size={16} />
                    </button>
                  </form>
                </div>

                {/* Confirmation modal */}
                {showConfirm && (
                  <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
                    <div className="ge-card" style={{ padding: 36, maxWidth: 420, width: '90%', boxShadow: 'var(--shadow-lg)' }}>
                      <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 500, color: 'var(--text)', marginBottom: 8 }}>
                        Confirmar operación
                      </h3>
                      <p style={{ fontSize: 14, color: 'var(--text-2)', fontFamily: 'DM Sans', marginBottom: 24, lineHeight: 1.6 }}>
                        Estás a punto de registrar la compra de{' '}
                        <strong style={{ color: 'var(--text)' }}>
                          {buyResult.toLocaleString('es-PY', { maximumFractionDigits: 2 })} {buyTo}
                        </strong>{' '}
                        por{' '}
                        <strong style={{ color: 'var(--text)' }}>
                          {parseFloat(buyAmount).toLocaleString('es-PY')} {buyFrom}
                        </strong>.
                        ¿Confirmás?
                      </p>
                      <div style={{ display: 'flex', gap: 12 }}>
                        <button onClick={() => setShowConfirm(false)} className="ge-btn-outline" style={{ flex: 1 }}>
                          Cancelar
                        </button>
                        <button onClick={handleConfirm} className="ge-btn-primary" style={{ flex: 1 }}>
                          Confirmar operación
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ── Transacciones ── */}
            {activeTab === 'transacciones' && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
                  <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.02em' }}>
                    Historial de transacciones
                  </h2>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="ge-btn-outline" style={{ fontSize: 13 }}>Exportar PDF</button>
                    <button className="ge-btn-outline" style={{ fontSize: 13 }}>Exportar Excel</button>
                  </div>
                </div>

                {/* Filters */}
                <div className="ge-card" style={{ padding: '14px 20px', marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Sans', fontWeight: 600 }}>FILTROS:</span>
                  {['Fecha', 'Moneda', 'Estado', 'Tipo'].map(f => (
                    <select key={f} className="ge-input" style={{ width: 'auto', fontSize: 12, padding: '6px 28px 6px 10px', cursor: 'pointer' }}>
                      <option>{f}</option>
                    </select>
                  ))}
                </div>

                <div className="ge-card" style={{ overflow: 'hidden' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--border)' }}>
                        {['ID', 'Fecha', 'Tipo', 'De', 'A', 'Monto', 'Estado', 'Acciones'].map(h => (
                          <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', fontFamily: 'DM Sans', whiteSpace: 'nowrap' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {transactions.map((t, i) => (
                        <tr key={t.id} className="table-row-hover" style={{ borderBottom: i < transactions.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}>
                          <td style={{ padding: '14px 16px' }}>
                            <span style={{ fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--primary)', fontWeight: 500 }}>{t.id}</span>
                          </td>
                          <td style={{ padding: '14px 16px' }}>
                            <span style={{ fontSize: 12, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>{t.date}</span>
                          </td>
                          <td style={{ padding: '14px 16px' }}>
                            <span style={{
                              fontSize: 12, fontWeight: 700, fontFamily: 'DM Sans',
                              color: t.type === 'Compra' ? 'var(--success)' : 'var(--danger)',
                            }}>
                              {t.type}
                            </span>
                          </td>
                          <td style={{ padding: '14px 16px' }}>
                            <span style={{ fontFamily: 'JetBrains Mono', fontSize: 12, color: 'var(--text)' }}>{t.from}</span>
                          </td>
                          <td style={{ padding: '14px 16px' }}>
                            <span style={{ fontFamily: 'JetBrains Mono', fontSize: 12, color: 'var(--text)' }}>{t.to}</span>
                          </td>
                          <td style={{ padding: '14px 16px' }}>
                            <span style={{ fontFamily: 'JetBrains Mono', fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>
                              {t.amount.toLocaleString('es-PY')}
                            </span>
                          </td>
                          <td style={{ padding: '14px 16px' }}>
                            <StatusBadge status={t.status} size="sm" />
                          </td>
                          <td style={{ padding: '14px 16px' }}>
                            <button className="ge-btn-ghost" style={{ fontSize: 12, padding: '4px 10px', display: 'flex', alignItems: 'center', gap: 5 }}>
                              Ver <AppIcon name="forward" size={13} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 16, flexWrap: 'wrap', gap: 12 }}>
                  <span style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>
                    Mostrando 5 de 47 transacciones
                  </span>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {[1, 2, 3, '...', 10].map((p, i) => (
                      <button key={i} style={{
                        width: 32, height: 32, borderRadius: 6, border: '1px solid var(--border)',
                        background: p === 1 ? 'var(--primary)' : 'transparent',
                        color: p === 1 ? '#fff' : 'var(--text-2)',
                        fontFamily: 'DM Sans', fontSize: 13, cursor: 'pointer',
                      }}>
                        {p}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
