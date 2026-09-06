import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import Navbar from '../components/Navbar';
import Sidebar from '../components/Sidebar';
import { analystRates, gainData } from '../data/mockData';
import { useAuth } from '../contexts/AuthContext';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';

const sidebarItems = [
  { icon: '◈', label: 'Resumen', href: '/analyst' },
  { icon: '📊', label: 'Tasas', href: '/analyst/tasas' },
  { icon: '📈', label: 'Histórico', href: '/analyst/historico' },
  { icon: '💰', label: 'Ganancias', href: '/analyst/ganancias' },
  { icon: '📋', label: 'Reportes', href: '/analyst/reportes' },
  { icon: '🔔', label: 'Notificaciones', href: '/analyst/notificaciones', badge: 1 },
];

const historyData = [
  { date: 'Ago 1', usd: 7320, eur: 7990, brl: 1310 },
  { date: 'Ago 5', usd: 7360, eur: 8020, brl: 1318 },
  { date: 'Ago 10', usd: 7390, eur: 8050, brl: 1325 },
  { date: 'Ago 15', usd: 7420, eur: 8080, brl: 1331 },
  { date: 'Ago 20', usd: 7440, eur: 8095, brl: 1336 },
  { date: 'Ago 25', usd: 7460, eur: 8110, brl: 1338 },
  { date: 'Ago 31', usd: 7480, eur: 8120, brl: 1340 },
];

export default function AnalystDashboard() {
  const { user } = useAuth();
  const location = useLocation();
  const path = location.pathname.split('/')[2];
  const activeSection = path || 'resumen';

  const [editingRate, setEditingRate] = useState<string | null>(null);
  const [rateValues, setRateValues] = useState<Record<string, { buy: number; sell: number }>>(
    Object.fromEntries(analystRates.map(r => [r.currency, { buy: r.buy, sell: r.sell }]))
  );
  const [saved, setSaved] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState<string | null>(null);
  const [gainFilter, setGainFilter] = useState('Mes');

  const handleSave = (currency: string) => {
    setShowConfirm(currency);
  };

  const handleConfirmSave = () => {
    setSaved(showConfirm);
    setEditingRate(null);
    setShowConfirm(null);
    setTimeout(() => setSaved(null), 3000);
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
      <Navbar />
      <div style={{ display: 'flex', flex: 1 }}>
        <Sidebar items={sidebarItems} name={user?.name ?? 'Analista'} role="Analista cambiario" />

        <main style={{ flex: 1, padding: '80px 0 0', overflowX: 'hidden' }}>
          <div style={{ padding: '24px 40px', borderBottom: '1px solid var(--border)' }}>
            <h1 style={{ fontFamily: 'Fraunces, serif', fontSize: 24, fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.02em' }}>
              Panel Analista Cambiario
            </h1>
            <p style={{ fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans', marginTop: 4 }}>
              31 de agosto de 2026 · Tasas y análisis de mercado
            </p>
          </div>

          <div style={{ padding: '28px 40px' }}>
            {activeSection === 'resumen' && (
              <>
                {/* ── KPIs ── */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 28 }}>
                  {[
                    { label: 'USD/PYG COMPRA', value: '7.480', sub: '↑ +31 vs. ayer', color: 'var(--success)' },
                    { label: 'EUR/PYG COMPRA', value: '8.120', sub: '↓ -15 vs. ayer', color: 'var(--danger)' },
                    { label: 'GANANCIA HOY', value: '1.84M', sub: 'PYG · 31/08', color: 'var(--primary)' },
                    { label: 'GANANCIA MES', value: '48.2M', sub: 'PYG · Agosto 2026', color: 'var(--primary)' },
                  ].map(k => (
                    <div key={k.label} className="ge-card" style={{ padding: '20px 24px' }}>
                      <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 700, letterSpacing: '0.08em', fontFamily: 'DM Sans', marginBottom: 8 }}>{k.label}</div>
                      <div style={{ fontFamily: 'JetBrains Mono', fontSize: 24, fontWeight: 600, color: k.color, lineHeight: 1 }}>{k.value}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'DM Sans', marginTop: 6 }}>{k.sub}</div>
                    </div>
                  ))}
                </div>
                
                {/* Charts */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
                  {/* Historical rates */}
                  <div className="ge-card" style={{ padding: 24 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans' }}>Histórico de tasas · Agosto</div>
                      <div style={{ display: 'flex', gap: 12, fontSize: 11, fontFamily: 'DM Sans' }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--text-2)' }}>
                          <span style={{ width: 10, height: 2, background: '#3B5BFF', display: 'inline-block' }} />USD
                        </span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--text-2)' }}>
                          <span style={{ width: 10, height: 2, background: '#22C55E', display: 'inline-block' }} />EUR
                        </span>
                      </div>
                    </div>
                    <ResponsiveContainer width="100%" height={200}>
                      <LineChart data={historyData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                        <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-3)', fontFamily: 'DM Sans' }} />
                        <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10, fill: 'var(--text-3)', fontFamily: 'DM Sans' }} width={55} />
                        <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12, fontFamily: 'DM Sans' }} />
                        <Line type="monotone" dataKey="usd" stroke="#3B5BFF" strokeWidth={2} dot={false} name="USD/PYG" />
                        <Line type="monotone" dataKey="eur" stroke="#22C55E" strokeWidth={2} dot={false} name="EUR/PYG" />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  
                  {/* Gain chart */}
                  <div className="ge-card" style={{ padding: 24 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 8 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans' }}>Ganancia diaria · PYG</div>
                      <div style={{ display: 'flex', gap: 4, background: 'var(--surface-2)', borderRadius: 6, padding: 3 }}>
                        {['Semana', 'Mes', 'Año'].map(f => (
                          <button key={f} onClick={() => setGainFilter(f)} style={{
                            padding: '4px 10px', borderRadius: 4, border: 'none',
                            background: gainFilter === f ? 'var(--primary)' : 'transparent',
                            color: gainFilter === f ? '#fff' : 'var(--text-2)',
                            fontFamily: 'DM Sans', fontSize: 11, fontWeight: 600, cursor: 'pointer',
                          }}>
                            {f}
                          </button>
                        ))}
                      </div>
                    </div>
                    <ResponsiveContainer width="100%" height={200}>
                      <BarChart data={gainData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                        <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-3)', fontFamily: 'DM Sans' }} />
                        <YAxis tickFormatter={v => `${(v / 1_000_000).toFixed(1)}M`} tick={{ fontSize: 10, fill: 'var(--text-3)', fontFamily: 'DM Sans' }} width={50} />
                        <Tooltip
                          formatter={(v) => [`${(Number(v) / 1_000_000).toFixed(2)}M PYG`, 'Ganancia']}
                          contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12, fontFamily: 'DM Sans' }}
                        />
                        <Bar dataKey="gain" fill="var(--primary)" radius={[3, 3, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </>
            )}

            {/* ── Rate management table ── */}
            {activeSection === 'tasas' && (
              <>
                {saved && (
                  <div style={{
                    background: 'var(--success-bg)', border: '1px solid rgba(34,197,94,0.3)',
                    borderRadius: 8, padding: '12px 16px', marginBottom: 20,
                    fontSize: 13, color: 'var(--success)', fontFamily: 'DM Sans', fontWeight: 600,
                    display: 'flex', alignItems: 'center', gap: 8,
                  }}>
                    <span>✓</span> Tasa {saved}/PYG actualizada exitosamente
                  </div>
                )}

            <div className="ge-card" style={{ marginBottom: 24 }}>
              <div style={{ padding: '18px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans' }}>Gestión de tasas</div>
                <span style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>Última actualización: 31/08 · 09:00</span>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {['Divisa', 'Compra actual', 'Venta actual', 'Variación compra', 'Variación venta', 'Actualizado', 'Acciones'].map(h => (
                      <th key={h} style={{ padding: '11px 20px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', fontFamily: 'DM Sans' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {analystRates.map((r, i) => {
                    const isEditing = editingRate === r.currency;
                    const vals = rateValues[r.currency];
                    const buyDiff = vals.buy - r.prevBuy;
                    const sellDiff = vals.sell - r.prevSell;
                    return (
                      <tr key={r.currency} className="table-row-hover" style={{ borderBottom: i < analystRates.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}>
                        <td style={{ padding: '14px 20px' }}>
                          <span style={{ fontFamily: 'JetBrains Mono', fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>{r.currency}/PYG</span>
                        </td>
                        <td style={{ padding: '14px 20px' }}>
                          {isEditing ? (
                            <input
                              type="number"
                              value={vals.buy}
                              onChange={e => setRateValues(prev => ({ ...prev, [r.currency]: { ...prev[r.currency], buy: parseFloat(e.target.value) } }))}
                              className="ge-input"
                              style={{ width: 100, fontFamily: 'JetBrains Mono', fontSize: 13, padding: '6px 10px' }}
                              step="1"
                            />
                          ) : (
                            <span style={{ fontFamily: 'JetBrains Mono', fontSize: 14, fontWeight: 500, color: 'var(--text)' }}>
                              {vals.buy.toLocaleString('es-PY')}
                            </span>
                          )}
                        </td>
                        <td style={{ padding: '14px 20px' }}>
                          {isEditing ? (
                            <input
                              type="number"
                              value={vals.sell}
                              onChange={e => setRateValues(prev => ({ ...prev, [r.currency]: { ...prev[r.currency], sell: parseFloat(e.target.value) } }))}
                              className="ge-input"
                              style={{ width: 100, fontFamily: 'JetBrains Mono', fontSize: 13, padding: '6px 10px' }}
                              step="1"
                            />
                          ) : (
                            <span style={{ fontFamily: 'JetBrains Mono', fontSize: 14, fontWeight: 500, color: 'var(--text)' }}>
                              {vals.sell.toLocaleString('es-PY')}
                            </span>
                          )}
                        </td>
                        <td style={{ padding: '14px 20px' }}>
                          <span style={{ fontFamily: 'JetBrains Mono', fontSize: 13, color: buyDiff >= 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>
                            {buyDiff >= 0 ? '+' : ''}{buyDiff.toFixed(r.prevBuy < 10 ? 2 : 0)}
                          </span>
                        </td>
                        <td style={{ padding: '14px 20px' }}>
                          <span style={{ fontFamily: 'JetBrains Mono', fontSize: 13, color: sellDiff >= 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>
                            {sellDiff >= 0 ? '+' : ''}{sellDiff.toFixed(r.prevSell < 10 ? 2 : 0)}
                          </span>
                        </td>
                        <td style={{ padding: '14px 20px' }}>
                          <span style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>{r.updated}</span>
                        </td>
                        <td style={{ padding: '14px 20px' }}>
                          {isEditing ? (
                            <div style={{ display: 'flex', gap: 6 }}>
                              <button onClick={() => handleSave(r.currency)} className="ge-btn-primary" style={{ fontSize: 11, padding: '5px 10px' }}>Guardar</button>
                              <button onClick={() => setEditingRate(null)} className="ge-btn-ghost" style={{ fontSize: 11, padding: '5px 10px' }}>Cancelar</button>
                            </div>
                          ) : (
                            <button onClick={() => setEditingRate(r.currency)} className="ge-btn-ghost" style={{ fontSize: 12, padding: '5px 12px' }}>
                              Editar
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
              </>
            )}

            {activeSection === 'reportes' && (
              <div className="ge-card" style={{ padding: 24 }}>
                <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 18, color: 'var(--text)', marginBottom: 16 }}>Reportes Analíticos</h3>
                <p style={{ fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans', marginBottom: 20 }}>Módulo en desarrollo para la generación de reportes detallados sobre la evolución de tasas y predicción de mercado.</p>
                <button className="ge-btn-primary" style={{ padding: '6px 12px', fontSize: 12 }}>+ Nuevo Reporte</button>
              </div>
            )}

            {activeSection === 'notificaciones' && (
              <div className="ge-card" style={{ padding: 24 }}>
                <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 18, color: 'var(--text)', marginBottom: 16 }}>Notificaciones de Mercado</h3>
                <div style={{ borderBottom: '1px solid var(--border-subtle)', paddingBottom: 12, marginBottom: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>Cierre de mercado europeo</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>Hoy, 12:00</div>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>

      {/* Confirm rate change modal */}
      {showConfirm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="ge-card" style={{ padding: 32, maxWidth: 380, width: '90%', boxShadow: 'var(--shadow-lg)' }}>
            <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 20, fontWeight: 500, color: 'var(--text)', marginBottom: 12 }}>
              Confirmar cambio de tasa
            </h3>
            <p style={{ fontSize: 14, color: 'var(--text-2)', fontFamily: 'DM Sans', lineHeight: 1.6, marginBottom: 24 }}>
              Estás a punto de actualizar las tasas de <strong style={{ color: 'var(--text)' }}>{showConfirm}/PYG</strong>.
              Esta acción afectará todas las conversiones futuras. ¿Confirmás?
            </p>
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => setShowConfirm(null)} className="ge-btn-outline" style={{ flex: 1 }}>Cancelar</button>
              <button onClick={handleConfirmSave} className="ge-btn-primary" style={{ flex: 1 }}>Confirmar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
