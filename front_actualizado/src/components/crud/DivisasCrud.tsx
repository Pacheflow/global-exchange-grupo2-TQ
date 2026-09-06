import { useState } from 'react';
import { currencies } from '../../data/mockData';

export default function DivisasCrud() {
  const [view, setView] = useState<'list' | 'create' | 'edit'>('list');
  const [selectedCurrency, setSelectedCurrency] = useState<any>(null);
  const [currencyToDelete, setCurrencyToDelete] = useState<any>(null);
  const [operationDone, setOperationDone] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setView('list');
    setOperationDone(true);
    setTimeout(() => setOperationDone(false), 3000);
  };

  if (view === 'create' || view === 'edit') {
    return (
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => setView('list')} className="ge-btn-ghost" style={{ fontSize: 13, padding: '6px 12px' }}>
            ← Volver
          </button>
          <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.02em', margin: 0 }}>
            {view === 'create' ? 'Nueva divisa' : `Editar divisa: ${selectedCurrency?.code}`}
          </h2>
        </div>
        <div className="ge-card" style={{ padding: 32, maxWidth: 600 }}>
          <form onSubmit={handleSubmit}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
              <div>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 8, fontFamily: 'DM Sans' }}>CÓDIGO (ISO)</label>
                <input className="ge-input" defaultValue={selectedCurrency?.code} required />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 8, fontFamily: 'DM Sans' }}>BANDERA (EMOJI)</label>
                <input className="ge-input" defaultValue={selectedCurrency?.flag} required />
              </div>
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 8, fontFamily: 'DM Sans' }}>NOMBRE DE LA MONEDA</label>
              <input className="ge-input" defaultValue={selectedCurrency?.name} required />
            </div>
            <div style={{ marginBottom: 32 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                <input type="checkbox" defaultChecked={true} style={{ width: 18, height: 18, accentColor: 'var(--primary)' }} />
                <span style={{ fontSize: 13, color: 'var(--text)', fontFamily: 'DM Sans', fontWeight: 500 }}>Divisa activa en el sistema</span>
              </label>
            </div>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button type="button" onClick={() => setView('list')} className="ge-btn-outline" style={{ padding: '10px 24px' }}>Cancelar</button>
              <button type="submit" className="ge-btn-primary" style={{ padding: '10px 24px' }}>Guardar cambios</button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div>
      {operationDone && (
        <div style={{
          background: 'var(--success-bg)', border: '1px solid rgba(34,197,94,0.3)',
          borderRadius: 10, padding: '16px 20px', marginBottom: 24,
          display: 'flex', alignItems: 'center', gap: 12,
          fontSize: 14, color: 'var(--success)', fontFamily: 'DM Sans', fontWeight: 600,
        }}>
          <span style={{ fontSize: 20 }}>✓</span>
          Divisa guardada exitosamente.
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 16 }}>
        <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.02em', margin: 0 }}>Gestión de divisas</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ position: 'relative' }}>
            <span style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', fontSize: 12, color: 'var(--text-3)' }}>🔍</span>
            <input type="text" placeholder="Buscar divisa..." className="ge-input" style={{ paddingLeft: 30, width: 200, fontSize: 12, padding: '8px 12px 8px 30px' }} />
          </div>
          <button onClick={() => { setSelectedCurrency(null); setView('create'); }} className="ge-btn-primary" style={{ fontSize: 13, padding: '8px 16px' }}>+ Nueva divisa</button>
        </div>
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
                <td style={{ padding: '14px 20px', fontSize: 22 }}>{c.flag}</td>
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
                    <button onClick={() => { setSelectedCurrency(c); setView('edit'); }} className="ge-btn-ghost" style={{ fontSize: 11, padding: '3px 8px' }}>Editar</button>
                    <button onClick={() => setCurrencyToDelete(c)} className="ge-btn-ghost" style={{ fontSize: 11, padding: '3px 8px', color: 'var(--danger)' }}>Desactivar</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {currencyToDelete && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }}>
          <div className="ge-card" style={{ padding: 32, maxWidth: 400, width: '100%', backgroundColor: 'var(--surface)' }}>
            <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 20, marginTop: 0, color: 'var(--text)' }}>Desactivar Divisa</h3>
            <p style={{ fontSize: 14, color: 'var(--text-2)', fontFamily: 'DM Sans', marginBottom: 24 }}>
              ¿Estás seguro que deseas desactivar la divisa <strong>{currencyToDelete.code}</strong>? Esta acción ocultará la divisa en las nuevas operaciones.
            </p>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button onClick={() => setCurrencyToDelete(null)} className="ge-btn-outline" style={{ padding: '8px 16px' }}>Cancelar</button>
              <button onClick={() => setCurrencyToDelete(null)} className="ge-btn-primary" style={{ padding: '8px 16px', backgroundColor: 'var(--danger)', borderColor: 'var(--danger)' }}>Desactivar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
