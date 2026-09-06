import { useState } from 'react';

const mockPagos = [
  { id: 1, name: 'Banco Familiar', type: 'Cuenta bancaria', account: '***4567', client: 'KNG S.A.', status: 'Activo' },
  { id: 2, name: 'Billetera Tigo', type: 'Billetera electrónica', account: '***8901', client: 'KNG S.A.', status: 'Activo' },
  { id: 3, name: 'Banco Itaú', type: 'Cuenta bancaria', account: '***1234', client: 'Importadora del Norte', status: 'Activo' },
];

export default function PagosCrud() {
  const [view, setView] = useState<'list' | 'create' | 'edit'>('list');
  const [selectedPago, setSelectedPago] = useState<any>(null);
  const [pagoToDelete, setPagoToDelete] = useState<any>(null);
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
            {view === 'create' ? 'Nuevo medio de pago' : `Editar medio de pago: ${selectedPago?.name}`}
          </h2>
        </div>
        <div className="ge-card" style={{ padding: 32, maxWidth: 600 }}>
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 8, fontFamily: 'DM Sans' }}>CLIENTE ASOCIADO</label>
              <select className="ge-input" defaultValue={selectedPago?.client || ''} required style={{ cursor: 'pointer' }}>
                <option value="" disabled>Seleccionar cliente...</option>
                <option value="KNG S.A.">KNG S.A.</option>
                <option value="Importadora del Norte">Importadora del Norte</option>
                <option value="Exportaciones Río S.R.L.">Exportaciones Río S.R.L.</option>
              </select>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
              <div>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 8, fontFamily: 'DM Sans' }}>TIPO DE MEDIO</label>
                <select className="ge-input" defaultValue={selectedPago?.type || 'Cuenta bancaria'} required style={{ cursor: 'pointer' }}>
                  <option value="Cuenta bancaria">Cuenta bancaria</option>
                  <option value="Billetera electrónica">Billetera electrónica</option>
                  <option value="Efectivo">Efectivo / Caja</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 8, fontFamily: 'DM Sans' }}>ENTIDAD (EJ: BANCO ITAÚ)</label>
                <input type="text" className="ge-input" defaultValue={selectedPago?.name} required />
              </div>
            </div>
            <div style={{ marginBottom: 32 }}>
              <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 8, fontFamily: 'DM Sans' }}>NÚMERO DE CUENTA / TELÉFONO</label>
              <input type="text" className="ge-input" defaultValue={selectedPago?.account} required />
            </div>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button type="button" onClick={() => setView('list')} className="ge-btn-outline" style={{ padding: '10px 24px' }}>Cancelar</button>
              <button type="submit" className="ge-btn-primary" style={{ padding: '10px 24px' }}>Guardar medio de pago</button>
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
          Medio de pago guardado exitosamente.
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 16 }}>
        <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.02em', margin: 0 }}>Medios de pago del cliente</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ position: 'relative' }}>
            <span style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', fontSize: 12, color: 'var(--text-3)' }}>🔍</span>
            <input type="text" placeholder="Buscar cliente o medio..." className="ge-input" style={{ paddingLeft: 30, width: 220, fontSize: 12, padding: '8px 12px 8px 30px' }} />
          </div>
          <button onClick={() => { setSelectedPago(null); setView('create'); }} className="ge-btn-primary" style={{ fontSize: 13, padding: '8px 16px' }}>+ Nuevo medio de pago</button>
        </div>
      </div>
      <div className="ge-card" style={{ overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['Cliente', 'Entidad', 'Tipo', 'Cuenta', 'Estado', 'Acciones'].map(h => (
                <th key={h} style={{ padding: '12px 20px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.08em', fontFamily: 'DM Sans' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {mockPagos.map((p, i) => (
              <tr key={p.id} className="table-row-hover" style={{ borderBottom: i < mockPagos.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}>
                <td style={{ padding: '14px 20px' }}><span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans' }}>{p.client}</span></td>
                <td style={{ padding: '14px 20px' }}><span style={{ fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>{p.name}</span></td>
                <td style={{ padding: '14px 20px' }}>
                  <span style={{ fontSize: 12, padding: '2px 8px', borderRadius: 4, background: 'var(--surface-2)', color: 'var(--text)', fontFamily: 'DM Sans' }}>
                    {p.type}
                  </span>
                </td>
                <td style={{ padding: '14px 20px' }}><span style={{ fontFamily: 'JetBrains Mono', fontSize: 13, color: 'var(--text)' }}>{p.account}</span></td>
                <td style={{ padding: '14px 20px' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: p.status === 'Activo' ? 'var(--success)' : 'var(--text-3)', fontFamily: 'DM Sans', fontWeight: 600 }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: p.status === 'Activo' ? 'var(--success)' : 'var(--text-3)' }} />
                    {p.status}
                  </span>
                </td>
                <td style={{ padding: '14px 20px' }}>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button onClick={() => { setSelectedPago(p); setView('edit'); }} className="ge-btn-ghost" style={{ fontSize: 11, padding: '3px 8px' }}>Editar</button>
                    <button onClick={() => setPagoToDelete(p)} className="ge-btn-ghost" style={{ fontSize: 11, padding: '3px 8px', color: 'var(--danger)' }}>Eliminar</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pagoToDelete && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }}>
          <div className="ge-card" style={{ padding: 32, maxWidth: 400, width: '100%', backgroundColor: 'var(--surface)' }}>
            <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 20, marginTop: 0, color: 'var(--text)' }}>Eliminar Medio de Pago</h3>
            <p style={{ fontSize: 14, color: 'var(--text-2)', fontFamily: 'DM Sans', marginBottom: 24 }}>
              ¿Estás seguro que deseas eliminar el medio de pago <strong>{pagoToDelete.name}</strong> de <strong>{pagoToDelete.client}</strong>?
            </p>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button onClick={() => setPagoToDelete(null)} className="ge-btn-outline" style={{ padding: '8px 16px' }}>Cancelar</button>
              <button onClick={() => setPagoToDelete(null)} className="ge-btn-primary" style={{ padding: '8px 16px', backgroundColor: 'var(--danger)', borderColor: 'var(--danger)' }}>Eliminar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
