import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import Navbar from '../components/Navbar';
import Sidebar from '../components/Sidebar';
import StatusBadge from '../components/StatusBadge';
import { cashierData } from '../data/mockData';
import { useAuth } from '../contexts/AuthContext';

const sidebarItems = [
  { icon: '◈', label: 'Resumen', href: '/cashier' },
  { icon: '🗄', label: 'Mi caja', href: '/cashier/caja' },
  { icon: '💼', label: 'Saldos', href: '/cashier/saldos' },
  { icon: '↕', label: 'Movimientos', href: '/cashier/movimientos' },
  { icon: '⇄', label: 'Transferencias', href: '/cashier/transferencias' },
  { icon: '⚖', label: 'Arqueo', href: '/cashier/arqueo' },
  { icon: '📋', label: 'Historial', href: '/cashier/historial' },
];

const DENOMINATIONS: Record<string, number[]> = {
  USD: [100, 50, 20, 10, 5, 1],
  EUR: [100, 50, 20, 10, 5, 2, 1],
  BRL: [100, 50, 20, 10, 5, 2, 1],
  PYG: [100000, 50000, 20000, 10000, 5000, 2000, 1000],
};

function BalanceCard({ currency, amount, flag }: { currency: string; amount: number; flag: string }) {
  const formatted = currency === 'PYG'
    ? `${(amount / 1_000_000).toFixed(1)}M`
    : amount.toLocaleString('es-PY');
  return (
    <div className="ge-card" style={{ padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <span style={{ fontSize: 22 }}>{flag}</span>
        <span style={{
          fontSize: 10, fontWeight: 700, color: 'var(--success)',
          background: 'var(--success-bg)', borderRadius: 4, padding: '2px 7px', fontFamily: 'DM Sans',
        }}>ACTIVO</span>
      </div>
      <div style={{ fontFamily: 'JetBrains Mono', fontSize: 26, fontWeight: 600, color: 'var(--text)', lineHeight: 1 }}>
        {formatted}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'DM Sans', marginTop: 4 }}>
        {currency} · Saldo actual
      </div>
    </div>
  );
}

const FLAGS: Record<string, string> = { PYG: '🇵🇾', USD: '🇺🇸', EUR: '🇪🇺', BRL: '🇧🇷' };

export default function CashierDashboard() {
  const { user } = useAuth();
  const location = useLocation();
  const path = location.pathname.split('/')[2];
  const activeSection = path || 'resumen';

  const [activeView, setActiveView] = useState<'caja' | 'arqueo' | 'billetes' | 'cierre'>('caja');
  const [billCounts, setBillCounts] = useState<Record<string, number>>(
    Object.fromEntries(DENOMINATIONS.USD.map(d => [String(d), 0]))
  );
  const [billCurrency, setBillCurrency] = useState('USD');
  const [realBalance, setRealBalance] = useState<Record<string, number>>({
    PYG: 85_400_000, USD: 12_500, EUR: 3_200, BRL: 8_000,
  });
  const [showCierre, setShowCierre] = useState(false);

  const billTotal = DENOMINATIONS[billCurrency]?.reduce(
    (sum, d) => sum + d * (billCounts[String(d)] ?? 0), 0
  ) ?? 0;

  const expectedBalance = cashierData.balances.find(b => b.currency === 'USD')?.amount ?? 12_500;
  const diff = realBalance.USD - expectedBalance;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
      <Navbar />
      <div style={{ display: 'flex', flex: 1 }}>
        <Sidebar items={sidebarItems} name={user?.name ?? 'Cajero'} role="Cajero / Operador" />

        <main style={{ flex: 1, padding: '80px 0 0', overflowX: 'hidden' }}>
          {/* Header */}
          <div style={{ padding: '20px 40px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
            <div>
              <h1 style={{ fontFamily: 'Fraunces, serif', fontSize: 24, fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.02em' }}>
                Panel de Caja
              </h1>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 6 }}>
                <span style={{ fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>{cashierData.cajaName}</span>
                <span style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>·</span>
                <span style={{ fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>Apertura: {cashierData.openTime} h</span>
                <StatusBadge status={cashierData.status} size="sm" />
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              {(activeSection === 'caja' || activeSection === 'resumen') && (
                <div style={{ display: 'flex', gap: 4, background: 'var(--surface-2)', borderRadius: 8, padding: 4, border: '1px solid var(--border)' }}>
                  {(['caja', 'arqueo', 'billetes'] as const).map(v => (
                    <button key={v} onClick={() => setActiveView(v)} style={{
                      padding: '6px 14px', borderRadius: 6, border: 'none',
                      background: activeView === v ? 'var(--primary)' : 'transparent',
                      color: activeView === v ? '#fff' : 'var(--text-2)',
                      fontFamily: 'DM Sans', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                      textTransform: 'capitalize',
                    }}>
                      {v}
                    </button>
                  ))}
                </div>
              )}
              <button onClick={() => setShowCierre(true)} className="ge-btn-outline" style={{ fontSize: 13, color: 'var(--danger)', borderColor: 'var(--danger)' }}>
                Cerrar caja
              </button>
            </div>
          </div>

          <div style={{ padding: '28px 40px' }}>
            {/* ── Caja / Saldos ── */}
            {(activeSection === 'resumen' || activeSection === 'caja' || activeSection === 'saldos' || activeSection === 'movimientos') && (
              <div>
                {/* Balance cards */}
                {(activeSection === 'resumen' || activeSection === 'caja' || activeSection === 'saldos') && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 28 }}>
                    {cashierData.balances.map(b => (
                      <BalanceCard key={b.currency} currency={b.currency} amount={b.amount} flag={FLAGS[b.currency] ?? '💱'} />
                    ))}
                  </div>
                )}

                {/* Movements table */}
                {(activeSection === 'resumen' || activeSection === 'caja' || activeSection === 'movimientos') && (
                  <div className="ge-card" style={{ overflow: 'hidden' }}>
                    <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans' }}>Movimientos del turno</div>
                      <button className="ge-btn-ghost" style={{ fontSize: 12 }}>Ver todo →</button>
                    </div>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr style={{ borderBottom: '1px solid var(--border)' }}>
                          {['ID', 'Fecha', 'Tipo', 'Moneda', 'Entrada', 'Salida', 'Saldo', 'Referencia'].map(h => (
                            <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', fontFamily: 'DM Sans' }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {cashierData.movements.map((m, i) => (
                          <tr key={m.id} className="table-row-hover" style={{ borderBottom: i < cashierData.movements.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}>
                            <td style={{ padding: '12px 16px' }}><span style={{ fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--primary)' }}>{m.id}</span></td>
                            <td style={{ padding: '12px 16px' }}><span style={{ fontSize: 12, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>{m.date}</span></td>
                            <td style={{ padding: '12px 16px' }}>
                              <span style={{ fontSize: 12, fontWeight: 600, fontFamily: 'DM Sans', color: m.type === 'Compra' ? 'var(--success)' : m.type === 'Venta' ? 'var(--danger)' : 'var(--text-2)' }}>
                                {m.type}
                              </span>
                            </td>
                            <td style={{ padding: '12px 16px' }}><span style={{ fontFamily: 'JetBrains Mono', fontSize: 12, color: 'var(--text)' }}>{m.currency}</span></td>
                            <td style={{ padding: '12px 16px' }}>
                              {m.entrada > 0 && <span style={{ fontFamily: 'JetBrains Mono', fontSize: 12, color: 'var(--success)', fontWeight: 600 }}>+{m.entrada.toLocaleString('es-PY')}</span>}
                            </td>
                            <td style={{ padding: '12px 16px' }}>
                              {m.salida > 0 && <span style={{ fontFamily: 'JetBrains Mono', fontSize: 12, color: 'var(--danger)', fontWeight: 600 }}>-{m.salida.toLocaleString('es-PY')}</span>}
                            </td>
                            <td style={{ padding: '12px 16px' }}><span style={{ fontFamily: 'JetBrains Mono', fontSize: 12, color: 'var(--text)', fontWeight: 500 }}>{m.saldo.toLocaleString('es-PY')}</span></td>
                            <td style={{ padding: '12px 16px' }}><span style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>{m.ref}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* ── Arqueo ── */}
            {(activeSection === 'arqueo' || (activeSection === 'caja' && activeView === 'arqueo')) && (
              <div style={{ maxWidth: 640 }}>
                <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 500, color: 'var(--text)', marginBottom: 24, letterSpacing: '-0.02em' }}>
                  Arqueo de caja
                </h2>
                <div className="ge-card" style={{ padding: 28, marginBottom: 20 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans', marginBottom: 20 }}>
                    Ingresar saldo real por moneda
                  </div>
                  {cashierData.balances.map(b => (
                    <div key={b.currency} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, alignItems: 'center', marginBottom: 14 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: 18 }}>{FLAGS[b.currency]}</span>
                        <span style={{ fontFamily: 'JetBrains Mono', fontWeight: 700, fontSize: 14, color: 'var(--text)' }}>{b.currency}</span>
                      </div>
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'DM Sans', marginBottom: 4 }}>ESPERADO</div>
                        <div style={{ fontFamily: 'JetBrains Mono', fontSize: 13, color: 'var(--text-2)', fontWeight: 500 }}>{b.amount.toLocaleString('es-PY')}</div>
                      </div>
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'DM Sans', marginBottom: 4 }}>REAL</div>
                        <input
                          type="number"
                          value={realBalance[b.currency] ?? b.amount}
                          onChange={e => setRealBalance(prev => ({ ...prev, [b.currency]: parseFloat(e.target.value) || 0 }))}
                          className="ge-input"
                          style={{ fontFamily: 'JetBrains Mono', fontSize: 13, padding: '6px 10px' }}
                        />
                      </div>
                    </div>
                  ))}
                </div>

                {/* Difference display */}
                <div className="ge-card" style={{ padding: 24 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans', marginBottom: 16 }}>
                    Resultado del arqueo
                  </div>
                  {cashierData.balances.map(b => {
                    const real = realBalance[b.currency] ?? b.amount;
                    const diff = real - b.amount;
                    return (
                      <div key={b.currency} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                        <span style={{ fontFamily: 'JetBrains Mono', fontWeight: 700, fontSize: 13, color: 'var(--text)' }}>{b.currency}</span>
                        <div style={{ display: 'flex', gap: 24, alignItems: 'center' }}>
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>Diferencia</div>
                            <div style={{ fontFamily: 'JetBrains Mono', fontSize: 14, fontWeight: 700, color: diff === 0 ? 'var(--text-2)' : diff > 0 ? 'var(--success)' : 'var(--danger)' }}>
                              {diff >= 0 ? '+' : ''}{diff.toLocaleString('es-PY')}
                            </div>
                          </div>
                          <span style={{ fontSize: 13, color: diff === 0 ? 'var(--text-3)' : diff > 0 ? 'var(--success)' : 'var(--danger)', fontFamily: 'DM Sans', fontWeight: 600 }}>
                            {diff === 0 ? 'Cuadre exacto' : diff > 0 ? 'Sobrante' : 'Faltante'}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* ── Control de billetes ── */}
            {(activeView === 'billetes' && activeSection === 'caja') && (
              <div style={{ maxWidth: 500 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
                  <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.02em' }}>
                    Control de billetes
                  </h2>
                  <select
                    value={billCurrency}
                    onChange={e => {
                      setBillCurrency(e.target.value);
                      setBillCounts(Object.fromEntries((DENOMINATIONS[e.target.value] ?? []).map(d => [String(d), 0])));
                    }}
                    className="ge-input"
                    style={{ width: 'auto', fontFamily: 'JetBrains Mono', fontWeight: 700, cursor: 'pointer' }}
                  >
                    {Object.keys(DENOMINATIONS).map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div className="ge-card" style={{ overflow: 'hidden' }}>
                  <div style={{ padding: '14px 24px', borderBottom: '1px solid var(--border)' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', fontSize: 10, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', fontFamily: 'DM Sans' }}>
                      <span>DENOMINACIÓN</span><span style={{ textAlign: 'center' }}>CANTIDAD</span><span style={{ textAlign: 'right' }}>SUBTOTAL</span>
                    </div>
                  </div>
                  {(DENOMINATIONS[billCurrency] ?? []).map(denom => {
                    const count = billCounts[String(denom)] ?? 0;
                    return (
                      <div key={denom} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', alignItems: 'center', padding: '12px 24px', borderBottom: '1px solid var(--border-subtle)' }}>
                        <span style={{ fontFamily: 'JetBrains Mono', fontWeight: 700, fontSize: 15, color: 'var(--text)' }}>
                          {denom.toLocaleString('es-PY')}
                        </span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center' }}>
                          <button
                            onClick={() => setBillCounts(prev => ({ ...prev, [String(denom)]: Math.max(0, (prev[String(denom)] ?? 0) - 1) }))}
                            style={{ width: 26, height: 26, borderRadius: 6, border: '1px solid var(--border)', background: 'var(--surface-2)', color: 'var(--text)', cursor: 'pointer', fontSize: 14 }}
                          >−</button>
                          <span style={{ fontFamily: 'JetBrains Mono', fontSize: 14, fontWeight: 600, color: 'var(--text)', minWidth: 28, textAlign: 'center' }}>{count}</span>
                          <button
                            onClick={() => setBillCounts(prev => ({ ...prev, [String(denom)]: (prev[String(denom)] ?? 0) + 1 }))}
                            style={{ width: 26, height: 26, borderRadius: 6, border: '1px solid var(--border)', background: 'var(--surface-2)', color: 'var(--text)', cursor: 'pointer', fontSize: 14 }}
                          >+</button>
                        </div>
                        <span style={{ fontFamily: 'JetBrains Mono', fontSize: 13, color: 'var(--text)', textAlign: 'right', fontWeight: 500 }}>
                          {(denom * count).toLocaleString('es-PY')}
                        </span>
                      </div>
                    );
                  })}
                  <div style={{ padding: '16px 24px', background: 'var(--surface-2)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', fontFamily: 'DM Sans' }}>TOTAL {billCurrency}</span>
                    <span style={{ fontFamily: 'JetBrains Mono', fontSize: 20, fontWeight: 700, color: 'var(--primary)' }}>
                      {billTotal.toLocaleString('es-PY')}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* ── Transferencias ── */}
            {activeSection === 'transferencias' && (
              <div className="ge-card" style={{ padding: 28, maxWidth: 640 }}>
                <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 500, color: 'var(--text)', marginBottom: 24, letterSpacing: '-0.02em' }}>
                  Transferencias Internas
                </h2>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
                  <div>
                    <label style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>Caja Destino</label>
                    <select className="ge-input" style={{ width: '100%', cursor: 'pointer' }}>
                      <option>Bóveda Central</option>
                      <option>Caja 02</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>Moneda</label>
                    <select className="ge-input" style={{ width: '100%', cursor: 'pointer' }}>
                      <option>USD - Dólar</option>
                      <option>PYG - Guaraní</option>
                    </select>
                  </div>
                </div>
                <div style={{ marginBottom: 20 }}>
                  <label style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>Monto</label>
                  <input type="number" className="ge-input" placeholder="0.00" style={{ width: '100%', fontFamily: 'JetBrains Mono' }} />
                </div>
                <button className="ge-btn-primary" style={{ width: '100%', padding: '10px' }}>Realizar Transferencia</button>
              </div>
            )}

            {/* ── Historial ── */}
            {activeSection === 'historial' && (
              <div className="ge-card" style={{ padding: 24 }}>
                <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 18, color: 'var(--text)', marginBottom: 16 }}>Historial de Turnos</h3>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)' }}>
                      <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 10, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>FECHA</th>
                      <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 10, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>TURNO</th>
                      <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 10, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>MOVIMIENTOS</th>
                      <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 10, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>ESTADO ARQUEO</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td style={{ padding: '12px 16px', fontSize: 13 }}>30/08/2026</td>
                      <td style={{ padding: '12px 16px', fontSize: 13 }}>08:00 - 18:00</td>
                      <td style={{ padding: '12px 16px', fontSize: 13 }}>142</td>
                      <td style={{ padding: '12px 16px', fontSize: 13 }}><span style={{ color: 'var(--success)' }}>Cuadre exacto</span></td>
                    </tr>
                    <tr>
                      <td style={{ padding: '12px 16px', fontSize: 13 }}>29/08/2026</td>
                      <td style={{ padding: '12px 16px', fontSize: 13 }}>08:00 - 18:00</td>
                      <td style={{ padding: '12px 16px', fontSize: 13 }}>98</td>
                      <td style={{ padding: '12px 16px', fontSize: 13 }}><span style={{ color: 'var(--success)' }}>Cuadre exacto</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </main>
      </div>

      {/* Cierre de caja modal */}
      {showCierre && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="ge-card" style={{ padding: 36, maxWidth: 440, width: '90%', boxShadow: 'var(--shadow-lg)' }}>
            <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 500, color: 'var(--text)', marginBottom: 20 }}>
              Resumen de cierre
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 24 }}>
              {[
                { label: 'Hora de apertura', value: '08:00 h' },
                { label: 'Hora de cierre', value: '18:00 h' },
                { label: 'Movimientos', value: `${cashierData.movements.length}` },
                { label: 'USD esperado', value: `${expectedBalance.toLocaleString('es-PY')}` },
                { label: 'USD real', value: `${realBalance.USD.toLocaleString('es-PY')}` },
                { label: 'Diferencia USD', value: `${diff >= 0 ? '+' : ''}${diff.toLocaleString('es-PY')}` },
              ].map(row => (
                <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                  <span style={{ fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>{row.label}</span>
                  <span style={{ fontFamily: 'JetBrains Mono', fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{row.value}</span>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => setShowCierre(false)} className="ge-btn-outline" style={{ flex: 1 }}>Cancelar</button>
              <button onClick={() => setShowCierre(false)} style={{ flex: 1 }} className="ge-btn-primary">
                Confirmar cierre
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
