import { useState } from 'react';
import { currencies } from '../../data/mockData';
import Sparkline from '../Sparkline';

export default function TasasView() {
  const [filter, setFilter] = useState('Hoy');
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.02em' }}>
          Cotizaciones actuales
        </h2>
        <div style={{ display: 'flex', gap: 4, background: 'var(--surface-2)', borderRadius: 8, padding: 4, border: '1px solid var(--border)' }}>
          {['Hoy', '7D', '30D', '90D', '1A'].map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                padding: '6px 14px', borderRadius: 6, border: 'none',
                background: filter === f ? 'var(--primary)' : 'transparent',
                color: filter === f ? '#fff' : 'var(--text-2)',
                fontFamily: 'DM Sans', fontSize: 12, fontWeight: 600, cursor: 'pointer',
              }}
            >
              {f}
            </button>
          ))}
        </div>
      </div>
      
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
        {currencies.filter(c => c.code !== 'PYG').map(c => (
          <div key={c.code} className="ge-card" style={{ padding: 24 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: 24 }}>{c.flag}</span>
                <div>
                  <div style={{ fontFamily: 'JetBrains Mono', fontWeight: 700, fontSize: 16, color: 'var(--text)' }}>{c.code}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>{c.name}</div>
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.04em', fontFamily: 'DM Sans', marginBottom: 2 }}>VARIACIÓN</div>
                <div style={{ fontSize: 13, fontWeight: 600, color: c.trend === 'up' ? 'var(--success)' : c.trend === 'down' ? 'var(--danger)' : 'var(--text-3)', fontFamily: 'JetBrains Mono' }}>
                  {c.change >= 0 ? '+' : ''}{c.change.toFixed(2)}%
                </div>
              </div>
            </div>
            
            <div style={{ display: 'flex', gap: 24, marginBottom: 20 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'DM Sans', marginBottom: 4 }}>COMPRA</div>
                <div style={{ fontFamily: 'JetBrains Mono', fontSize: 18, fontWeight: 600, color: 'var(--text)' }}>
                  {c.buy.toLocaleString('es-PY')}
                </div>
              </div>
              <div style={{ width: 1, background: 'var(--border-subtle)' }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'DM Sans', marginBottom: 4 }}>VENTA</div>
                <div style={{ fontFamily: 'JetBrains Mono', fontSize: 18, fontWeight: 600, color: 'var(--text)' }}>
                  {c.sell.toLocaleString('es-PY')}
                </div>
              </div>
            </div>
            
            <div style={{ marginBottom: 16 }}>
              <Sparkline data={c.sparkData} trend={c.trend} width={300} height={60} />
            </div>
            
            <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'DM Sans', textAlign: 'center' }}>
              Última actualización: {c.updated}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}