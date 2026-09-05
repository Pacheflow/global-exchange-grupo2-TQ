import { useEffect, useRef, useState } from 'react';
import Navbar from '../components/Navbar';
import LiveExchangeBoard from '../components/LiveExchangeBoard';
import Sparkline from '../components/Sparkline';
import { currencies, exchangeRates, currencyDataByFilter } from '../data/mockData';
import AppIcon from '../components/icons/AppIcon';
import CurrencyIcon from '../components/icons/CurrencyIcon';

const FILTERS = ['Hoy', '7D', '30D', '90D', '1A'];

function useReveal() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { el.classList.add('visible'); obs.disconnect(); } },
      { threshold: 0.1 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return ref;
}

function RevealSection({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  const ref = useReveal();
  return <div ref={ref} className="reveal" style={style}>{children}</div>;
}

function AnimatedChange({ value, triggered }: { value: number; triggered: boolean }) {
  const [display, setDisplay] = useState(0);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    cancelAnimationFrame(rafRef.current);
    if (!triggered) { setDisplay(0); return; }
    setDisplay(0);
    const start = performance.now();
    const duration = 900;
    const animate = (now: number) => {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 2);
      setDisplay(value * eased);
      if (p < 1) rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [value, triggered]);

  const abs = Math.abs(display);
  const sign = value >= 0 ? '+' : '-';
  const col = value > 0 ? 'var(--success)' : value < 0 ? 'var(--danger)' : 'var(--text-2)';

  return (
    <span style={{ fontFamily: 'JetBrains Mono', fontSize: 13, fontWeight: 600, color: col }}>
      {sign}{abs.toFixed(2)}%
    </span>
  );
}

function AnimatedPrice({ value, triggered }: { value: number; triggered: boolean }) {
  const [display, setDisplay] = useState(value);
  const rafRef = useRef<number>(0);
  const prev = useRef(value);

  useEffect(() => {
    cancelAnimationFrame(rafRef.current);
    if (!triggered) { setDisplay(value); prev.current = value; return; }
    const from = prev.current;
    const to = value;
    prev.current = value;
    const start = performance.now();
    const duration = 700;
    const animate = (now: number) => {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 2);
      setDisplay(from + (to - from) * eased);
      if (p < 1) rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [value, triggered]);
  return (
    <span style={{ fontFamily: 'JetBrains Mono', fontSize: 15, fontWeight: 500, color: 'var(--text)' }}>
      {display.toLocaleString('es-PY', { maximumFractionDigits: display < 100 ? 2 : 0 })}
    </span>
  );
}

export default function Landing() {
  const [rateFilter, setRateFilter] = useState('90D');
  const [fromCurrency, setFromCurrency] = useState('USD');
  const [toCurrency, setToCurrency] = useState('PYG');
  const [amount, setAmount] = useState('1000');
  const [converted, setConverted] = useState('');
  const [swapAnim, setSwapAnim] = useState(false);

  // Cotizaciones IntersectionObserver (one-shot)
  const cotizRef = useRef<HTMLDivElement>(null);
  const [cotizVisible, setCotizVisible] = useState(false);

  useEffect(() => {
    const el = cotizRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) { setCotizVisible(true); obs.disconnect(); }
      },
      { threshold: 0.15 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    const src = parseFloat(amount.replace(/[^0-9.]/g, '')) || 0;
    const rate = exchangeRates[fromCurrency]?.[toCurrency] ?? 1;
    const result = src * rate;
    setConverted(result.toLocaleString('es-PY', { maximumFractionDigits: result < 100 ? 4 : 0 }));
  }, [amount, fromCurrency, toCurrency]);

  const handleSwap = () => {
    setSwapAnim(true);
    setTimeout(() => setSwapAnim(false), 320);
    setFromCurrency(prev => {
      const next = toCurrency;
      setToCurrency(prev);
      return next;
    });
  };

  const currentRate = exchangeRates[fromCurrency]?.[toCurrency] ?? 1;
  const displayRate = currentRate < 1
    ? `1 ${toCurrency} = ${(1 / currentRate).toLocaleString('es-PY', { maximumFractionDigits: 2 })} ${fromCurrency}`
    : `1 ${fromCurrency} = ${currentRate.toLocaleString('es-PY', { maximumFractionDigits: 2 })} ${toCurrency}`;

  const availableCurrencies = currencies.filter(c => ['USD', 'EUR', 'BRL', 'ARS', 'PYG'].includes(c.code));

  const getFilterData = (code: string) => {
    const list = currencyDataByFilter[rateFilter];
    return list?.find(d => d.code === code) ?? currencies.find(c => c.code === code)!;
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
      <Navbar transparent />

      {/* ── Hero ── */}
      <section id="inicio" className="landing-hero" style={{
        background: 'radial-gradient(ellipse at 60% 50%, #0D1E4A 0%, #060B1E 65%)',
        position: 'relative',
      }}>
        {/* dot-grid texture */}
        <div style={{
          position: 'absolute', inset: 0, opacity: 0.035,
          backgroundImage: 'radial-gradient(circle, #3B5BFF 1px, transparent 1px)',
          backgroundSize: '36px 36px',
          pointerEvents: 'none',
        }} />

        <div className="landing-hero-content">
        {/* Left: Text */}
        <div className="landing-hero-copy">
          {/* Pill badge */}
          <div className="animate-fade-up" style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            background: 'rgba(59, 91, 255, 0.12)',
            border: '1px solid rgba(59, 91, 255, 0.28)',
            borderRadius: 999, padding: '5px 14px',
            fontSize: 11, fontWeight: 700, color: '#6B8AFF',
            letterSpacing: '0.12em', marginBottom: 'clamp(16px, 2.4vh, 24px)',
            fontFamily: 'DM Sans, sans-serif', textTransform: 'uppercase' as const,
          }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#3B5BFF', display: 'inline-block', flexShrink: 0 }} />
            Cotizaciones en tiempo real 
          </div>

          {/* Headline */}
          <h1 className="animate-fade-up delay-200 font-display" style={{
            fontSize: 'clamp(60px, 6vw, 92px)',
            fontWeight: 400,
            fontStyle: 'italic',
            color: '#E8F2FF',
            lineHeight: 0.98,
            letterSpacing: '-0.035em',
            marginBottom: 0,
            paddingBottom: 0,
            overflow: 'visible',
          }}>
            <span className="landing-hero-heading-line">Líderes en</span>
            <span className="landing-hero-heading-line" style={{ fontWeight: 600 }}>cambios</span>
            <span className="landing-hero-heading-line landing-hero-country-line">
              en{' '}
              <span className="gradient-text landing-hero-country" style={{ fontStyle: 'italic' }}>Paraguay</span>
            </span>
          </h1>

          {/* Divider accent */}
          <div className="animate-fade-up delay-300" style={{
            width: 48, height: 2,
            background: 'linear-gradient(90deg, #3B5BFF, transparent)',
            margin: 'clamp(8px, 1.4vh, 12px) 0',
          }} />

          <p className="animate-fade-up delay-400" style={{
            fontSize: 18,
            lineHeight: 1.65,
            color: '#4E6E9A',
            maxWidth: 520,
            fontFamily: 'DM Sans, sans-serif',
          }}>
            Operaciones seguras y transparentes. La plataforma de cambio de
            divisas más confiable del mercado paraguayo.
          </p>

          {/* CTAs */}
          <div className="animate-fade-up delay-600" style={{ display: 'flex', gap: 12, marginTop: 'clamp(20px, 2.8vh, 26px)', flexWrap: 'wrap' as const }}>
            <a href="#cotizaciones" className="ge-btn-primary" style={{ fontSize: 14 }}>
              Ver cotizaciones
            </a>
            <a href="#conversor" className="ge-btn-outline" style={{ fontSize: 14, borderColor: 'rgba(59,91,255,0.4)', color: '#6B8AFF' }}>
              Convertir moneda
            </a>
          </div>
        </div>

        {/* Right: Live Exchange Board */}
        <div className="animate-fade-in delay-300 landing-hero-board" style={{
            position: 'relative',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <div style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              position: 'relative',
            }}>
              <LiveExchangeBoard variant="hero" animate />
            </div>
        </div>
        </div>

        {/* Scroll indicator */}
        <a
          href="#cotizaciones"
          aria-label="Ir a Cotizaciones del Día"
          className="landing-hero-chevron"
          style={{
            margin: '0 auto',
            width: 'fit-content',
            textAlign: 'center',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 10,
            zIndex: 2,
            opacity: 0.85,
            transition: 'opacity 0.2s ease',
          }}
        >
          <AppIcon name="chevron-down" size={14} style={{ color: 'rgba(59, 91, 255, 0.55)' }} />
          <div style={{ width: 1, height: 24, background: 'linear-gradient(to bottom, rgba(59, 91, 255, 0.45), transparent)', margin: '0 auto' }} />
        </a>
      </section>

      {/* ── Cotizaciones del Día ── */}
      <section id="cotizaciones" style={{ padding: 'clamp(64px,8vw,96px) clamp(24px,6vw,80px)', background: 'var(--bg)' }}>
        <div ref={cotizRef}>
          <RevealSection>
            <div style={{ maxWidth: 1100, margin: '0 auto' }}>
              {/* Header row */}
              <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 48, flexWrap: 'wrap' as const, gap: 16 }}>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--primary)', letterSpacing: '0.12em', fontFamily: 'DM Sans', marginBottom: 8 }}>
                    MERCADO
                  </div>
                  <h2 className="font-display" style={{ fontSize: 'clamp(28px, 3vw, 42px)', fontWeight: 500, color: 'var(--text)', lineHeight: 1.1, letterSpacing: '-0.02em' }}>
                    Cotizaciones del Día
                  </h2>
                  <p style={{ marginTop: 10, fontSize: 15, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>
                    Cotizaciones actualizadas en tiempo real. Base: Guaraní paraguayo (PYG).
                  </p>
                </div>
                {/* Filter tabs */}
                <div style={{ display: 'flex', gap: 4, background: 'var(--surface-2)', borderRadius: 8, padding: 4, border: '1px solid var(--border)' }}>
                  {FILTERS.map(f => (
                    <button
                      key={f}
                      onClick={() => setRateFilter(f)}
                      style={{
                        padding: '5px 14px', fontSize: 12, fontWeight: 600,
                        borderRadius: 6, border: 'none', cursor: 'pointer',
                        fontFamily: 'DM Sans',
                        background: rateFilter === f ? 'var(--primary)' : 'transparent',
                        color: rateFilter === f ? '#fff' : 'var(--text-2)',
                        transition: 'all 0.15s',
                      }}
                    >
                      {f}
                    </button>
                  ))}
                </div>
              </div>

              {/* Table */}
              <div className="ge-card" style={{ overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' as const }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)' }}>
                      {['Moneda', 'Compra', 'Venta', rateFilter, 'Variación', 'Actualización'].map(h => (
                        <th key={h} style={{
                          padding: '14px 20px', textAlign: h === 'Moneda' ? 'left' : 'right' as const,
                          fontSize: 11, fontWeight: 600, color: 'var(--text-3)',
                          letterSpacing: '0.08em', fontFamily: 'DM Sans',
                          transition: 'all 0.15s',
                        }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {currencies.filter(c => c.code !== 'PYG').map((c, i) => {
                      const fd = getFilterData(c.code);
                      const trend = fd.change > 0 ? 'up' : fd.change < 0 ? 'down' : 'neutral';
                      const rateDirectionIcon = fd.change > 0 ? 'sell' : fd.change < 0 ? 'buy' : 'equal';
                      const rateDirectionColor = fd.change > 0
                        ? 'var(--success)'
                        : fd.change < 0
                          ? 'var(--danger)'
                          : 'var(--text-3)';
                      return (
                        <tr
                          key={c.code}
                          className="table-row-hover"
                          style={{ borderBottom: i < 3 ? '1px solid var(--border-subtle)' : 'none' }}
                        >
                          <td style={{ padding: '18px 20px' }}>
                            <div>
                              <div style={{ fontWeight: 700, color: 'var(--text)', fontFamily: 'JetBrains Mono', fontSize: 14 }}>{c.code}</div>
                              <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'DM Sans', marginTop: 1 }}>{c.name}</div>
                            </div>
                          </td>
                          <td style={{ padding: '18px 20px', textAlign: 'right' as const }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8 }}>
                              <AppIcon name={rateDirectionIcon} size={15} style={{ color: rateDirectionColor }} />
                              <AnimatedPrice value={fd.buy} triggered={cotizVisible} />
                            </div>
                          </td>
                          <td style={{ padding: '18px 20px', textAlign: 'right' as const }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8 }}>
                              <AppIcon name={rateDirectionIcon} size={15} style={{ color: rateDirectionColor }} />
                              <AnimatedPrice value={fd.sell} triggered={cotizVisible} />
                            </div>
                          </td>
                          <td style={{ padding: '18px 20px', width: '22%' }}>
                            <Sparkline data={fd.sparkData} trend={trend} width={180} height={32} fluid smoothDraw triggered={cotizVisible} />
                          </td>
                          <td style={{ padding: '18px 20px', textAlign: 'right' as const }}>
                            <AnimatedChange value={fd.change} triggered={cotizVisible} />
                          </td>
                          <td style={{ padding: '18px 20px', textAlign: 'right' as const }}>
                            <span style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>{c.updated}</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div style={{ marginTop: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap' as const, gap: 8 }}>
                <span style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>
                  Datos actualizados al 31/08/2026 · 10:24 h
                </span>
                <a href="#" className="ge-btn-ghost" style={{ fontSize: 13, display: 'inline-flex', alignItems: 'center', gap: 6 }}>Ver histórico <AppIcon name="forward" size={14} /></a>
              </div>
            </div>
          </RevealSection>
        </div>
      </section>

      {/* ── Conversor ── */}
      <section id="conversor" style={{ padding: 'clamp(64px,8vw,96px) clamp(24px,6vw,80px)', background: 'var(--bg-alt)' }}>
        <RevealSection>
          <div style={{ maxWidth: 1140, margin: '0 auto', display: 'grid', gridTemplateColumns: '35fr 65fr', gap: 'clamp(32px,5vw,80px)', alignItems: 'center' }}>
            {/* Left: description */}
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--primary)', letterSpacing: '0.12em', fontFamily: 'DM Sans', marginBottom: 8 }}>
                HERRAMIENTA PÚBLICA
              </div>
              <h2 className="font-display" style={{ fontSize: 'clamp(28px, 3vw, 42px)', fontWeight: 500, color: 'var(--text)', lineHeight: 1.1, letterSpacing: '-0.02em' }}>
                Conversor de Monedas
              </h2>
              <p style={{ marginTop: 12, fontSize: 15, lineHeight: 1.75, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>
                Simula la conversión entre divisas usando las tasas actualizadas
                del mercado. Disponible para todos, sin necesidad de registro.
              </p>
              <div style={{ marginTop: 28, display: 'flex', flexDirection: 'column' as const, gap: 14 }}>
                {[
                  { icon: 'realtime' as const, text: 'Tasas actualizadas en tiempo real' },
                  { icon: 'unlock' as const, text: 'Acceso libre, sin inicio de sesión' },
                  { icon: 'globe' as const, text: 'USD, EUR, BRL, ARS y PYG' },
                  { icon: 'chart' as const, text: 'Solo simulación — no genera transacciones' },
                ].map(b => (
                  <div key={b.icon} style={{ display: 'flex', alignItems: 'center', gap: 12, fontFamily: 'DM Sans', fontSize: 14, color: 'var(--text-2)' }}>
                    <span style={{ width: 24, display: 'flex', justifyContent: 'center' }}><AppIcon name={b.icon} size={18} /></span>
                    {b.text}
                  </div>
                ))}
              </div>
            </div>

            {/* Right: Converter widget */}
            <div className="ge-card" style={{ padding: 32 }}>
              {/* From */}
              <div style={{ marginBottom: 8 }}>
                <label style={{ display: 'block', fontSize: 10, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.12em', marginBottom: 10, fontFamily: 'DM Sans' }}>
                  TÚ ENTREGAS
                </label>
                <div style={{ display: 'flex', gap: 10 }}>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={amount}
                    onChange={e => setAmount(e.target.value.replace(/[^0-9.]/g, ''))}
                    className="ge-input"
                    style={{ fontFamily: 'JetBrains Mono', fontSize: 26, fontWeight: 600, padding: '14px 18px', flex: 1 }}
                    placeholder="0"
                  />
                  <select
                    value={fromCurrency}
                    onChange={e => setFromCurrency(e.target.value)}
                    className="ge-input"
                    style={{ width: 'auto', paddingRight: 36, fontWeight: 700, cursor: 'pointer', flexShrink: 0, fontSize: 15 }}
                  >
                    {availableCurrencies.map(c => (
                      <option key={c.code} value={c.code}>{c.code}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Swap button */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, margin: '20px 0' }}>
                <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
                <button
                  onClick={handleSwap}
                  style={{
                    width: 44, height: 44, borderRadius: '50%',
                    background: 'var(--primary)', border: 'none',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    cursor: 'pointer', color: '#fff', fontSize: 18,
                    transition: 'transform 0.32s ease, box-shadow 0.2s',
                    transform: swapAnim ? 'rotate(180deg)' : 'rotate(0deg)',
                    flexShrink: 0,
                    boxShadow: '0 2px 12px rgba(59,91,255,0.25)',
                  }}
                  title="Intercambiar monedas"
                >
                  <AppIcon name="exchange" size={20} />
                </button>
                <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
              </div>

              {/* To */}
              <div style={{ marginBottom: 24 }}>
                <label style={{ display: 'block', fontSize: 10, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.12em', marginBottom: 10, fontFamily: 'DM Sans' }}>
                  RECIBES APROXIMADAMENTE
                </label>
                <div style={{ display: 'flex', gap: 10 }}>
                  <div className="ge-input" style={{
                    flex: 1, fontFamily: 'JetBrains Mono', fontSize: 26, fontWeight: 600,
                    padding: '14px 18px', background: 'var(--bg-alt)', cursor: 'default',
                    color: 'var(--primary)', display: 'flex', alignItems: 'center',
                  }}>
                    {converted || '0'}
                  </div>
                  <select
                    value={toCurrency}
                    onChange={e => setToCurrency(e.target.value)}
                    className="ge-input"
                    style={{ width: 'auto', paddingRight: 36, fontWeight: 700, cursor: 'pointer', flexShrink: 0, fontSize: 15 }}
                  >
                    {availableCurrencies.map(c => (
                      <option key={c.code} value={c.code}>{c.code}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Rate info */}
              <div style={{
                background: 'var(--surface-2)', borderRadius: 10, padding: '14px 18px',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                flexWrap: 'wrap' as const, gap: 8, marginBottom: 16,
              }}>
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>Tipo de cambio aplicado</div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', fontFamily: 'JetBrains Mono', marginTop: 3 }}>
                    {displayRate}
                  </div>
                </div>
                <div style={{ textAlign: 'right' as const }}>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>Última actualización</div>
                  <div style={{ fontSize: 12, color: 'var(--text-2)', fontFamily: 'DM Sans', marginTop: 3 }}>31/08/2026 · 10:24</div>
                </div>
              </div>

              {/* Simulation note — no login required */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '10px 14px', borderRadius: 8,
                background: 'rgba(59,91,255,0.08)', border: '1px solid rgba(59,91,255,0.15)',
                fontSize: 12, color: 'var(--primary)', fontFamily: 'DM Sans',
              }}>
                <AppIcon name="info" size={15} style={{ opacity: 0.7 }} />
                Simulación gratuita · No genera ninguna transacción ni compromiso.
              </div>
            </div>
          </div>
        </RevealSection>
      </section>

      {/* ── Cómo funciona ── */}
      <section style={{ padding: 'clamp(64px,8vw,96px) clamp(24px,6vw,80px)', background: 'var(--bg)' }}>
        <RevealSection>
          <div style={{ maxWidth: 1100, margin: '0 auto' }}>
            <div style={{ textAlign: 'center', marginBottom: 64 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--primary)', letterSpacing: '0.12em', fontFamily: 'DM Sans', marginBottom: 8 }}>
                PROCESO
              </div>
              <h2 className="font-display" style={{ fontSize: 'clamp(28px, 3vw, 42px)', fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.02em' }}>
                Cómo funciona Global Exchange
              </h2>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 32 }}>
              {[
                { num: '01', title: 'Consulta la cotización', desc: 'Revisa las tasas del día actualizadas en tiempo real para las divisas que necesitas.' },
                { num: '02', title: 'Simula tu conversión', desc: 'Usa nuestro conversor para estimar cuánto recibirás antes de confirmar cualquier operación.' },
                { num: '03', title: 'Confirma tu operación', desc: 'Elige el medio de pago, revisa el resumen y confirma la operación con un solo clic.' },
                { num: '04', title: 'Recibe la confirmación', desc: 'Recibe la confirmación de la operación y accede al comprobante desde tu panel.' },
              ].map(step => (
                <div key={step.num} style={{ position: 'relative' }}>
                  <div style={{
                    fontSize: 'clamp(36px, 4vw, 52px)', fontFamily: 'Fraunces, serif',
                    fontWeight: 700, color: 'var(--primary)', opacity: 0.15, lineHeight: 1,
                    marginBottom: 16, letterSpacing: '-0.04em',
                  }}>
                    {step.num}
                  </div>
                  <div style={{ width: 40, height: 2, background: 'var(--primary)', marginBottom: 16, opacity: 0.6 }} />
                  <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans', marginBottom: 10 }}>
                    {step.title}
                  </h3>
                  <p style={{ fontSize: 14, lineHeight: 1.65, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>
                    {step.desc}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </RevealSection>
      </section>

      {/* ── Beneficios ── */}
      <section style={{ padding: 'clamp(64px,8vw,96px) clamp(24px,6vw,80px)', background: 'var(--bg-alt)' }}>
        <RevealSection>
          <div style={{ maxWidth: 1100, margin: '0 auto' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 80, alignItems: 'start' }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--primary)', letterSpacing: '0.12em', fontFamily: 'DM Sans', marginBottom: 8 }}>
                  VENTAJAS
                </div>
                <h2 className="font-display" style={{ fontSize: 'clamp(28px, 3vw, 42px)', fontWeight: 500, color: 'var(--text)', lineHeight: 1.1, letterSpacing: '-0.02em' }}>
                  Por qué elegir Global Exchange
                </h2>
                <div style={{ width: 40, height: 2, background: 'var(--primary)', margin: '24px 0' }} />
                <p style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>
                  Décadas de experiencia en el mercado cambiario paraguayo, respaldadas por tecnología de vanguardia.
                </p>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, background: 'var(--border)' }}>
                {[
                  { icon: 'chart' as const, title: 'Cotizaciones actualizadas', desc: 'Tasas del mercado actualizadas continuamente a lo largo del día.' },
                  { icon: 'security' as const, title: 'Operaciones seguras', desc: 'Autenticación robusta, control de acceso por roles y trazabilidad completa.' },
                  { icon: 'history' as const, title: 'Historial centralizado', desc: 'Accede a todas tus transacciones, facturas y comprobantes en un solo lugar.' },
                  { icon: 'user' as const, title: 'Atención profesional', desc: 'Soporte especializado con conocimiento cambiario real.' },
                  { icon: 'insight' as const, title: 'Información clara', desc: 'Sin comisiones ocultas. Cada operación muestra exactamente lo que recibirás.' },
                  { icon: 'globe' as const, title: 'Multi-moneda', desc: 'USD, EUR, BRL, ARS, PYG — con posibilidad de ampliar el catálogo.' },
                ].map(b => (
                  <div key={b.title} style={{ background: 'var(--surface)', padding: '28px 24px' }}>
                    <div style={{ marginBottom: 12 }}><AppIcon name={b.icon} size={24} /></div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans', marginBottom: 6 }}>{b.title}</div>
                    <div style={{ fontSize: 13, lineHeight: 1.6, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>{b.desc}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </RevealSection>
      </section>

      {/* ── Seguridad ── */}
      <section id="seguridad" style={{ padding: 'clamp(64px,8vw,96px) clamp(24px,6vw,80px)', background: 'var(--bg)' }}>
        <RevealSection>
          <div style={{ maxWidth: 1100, margin: '0 auto', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 80, alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--primary)', letterSpacing: '0.12em', fontFamily: 'DM Sans', marginBottom: 8 }}>
                CONFIANZA
              </div>
              <h2 className="font-display" style={{ fontSize: 'clamp(28px, 3vw, 42px)', fontWeight: 500, color: 'var(--text)', lineHeight: 1.1, letterSpacing: '-0.02em' }}>
                Tu seguridad es nuestra prioridad
              </h2>
              <p style={{ marginTop: 16, fontSize: 15, lineHeight: 1.7, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>
                Cada operación en Global Exchange está respaldada por múltiples capas de seguridad
                y un sistema de trazabilidad completo.
              </p>
              <div style={{ marginTop: 36, display: 'flex', flexDirection: 'column' as const, gap: 24 }}>
                {[
                  { icon: 'authentication' as const, title: 'Autenticación segura', desc: 'Sistema de identidad robusto con verificación en múltiples pasos.' },
                  { icon: 'roles' as const, title: 'Roles y permisos', desc: 'Cada usuario accede únicamente a las funciones correspondientes a su rol.' },
                  { icon: 'file-check' as const, title: 'Confirmación de operaciones', desc: 'Ninguna operación se registra sin una confirmación explícita del usuario.' },
                  { icon: 'activity' as const, title: 'Trazabilidad completa', desc: 'Historial auditado de cada acción realizada en el sistema.' },
                ].map(item => (
                  <div key={item.title} style={{ display: 'flex', gap: 16 }}>
                    <div style={{
                      width: 40, height: 40, borderRadius: 10,
                      background: 'var(--primary-muted)', border: '1px solid rgba(59,91,255,0.25)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 18, flexShrink: 0,
                    }}><AppIcon name={item.icon} size={20} /></div>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', fontFamily: 'DM Sans', marginBottom: 4 }}>{item.title}</div>
                      <div style={{ fontSize: 13, lineHeight: 1.6, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>{item.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="ge-card" style={{ padding: 32, position: 'relative', overflow: 'hidden' }}>
              <div style={{ position: 'absolute', top: -40, right: -40, width: 180, height: 180, borderRadius: '50%', background: 'var(--primary-muted)', opacity: 0.5 }} />
              <div style={{ position: 'relative' }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.1em', fontFamily: 'DM Sans', marginBottom: 20 }}>
                  ESTADO DEL SISTEMA
                </div>
                {[
                  { label: 'Autenticación', status: 'Operativo' },
                  { label: 'API de tasas', status: 'Operativo' },
                  { label: 'Procesamiento de órdenes', status: 'Operativo' },
                  { label: 'Facturación electrónica', status: 'Operativo' },
                  { label: 'Notificaciones', status: 'Operativo' },
                ].map(item => (
                  <div key={item.label} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '12px 0', borderBottom: '1px solid var(--border-subtle)',
                  }}>
                    <span style={{ fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans' }}>{item.label}</span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 600, color: 'var(--success)', fontFamily: 'DM Sans' }}>
                      <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--success)', display: 'inline-block' }} />
                      {item.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </RevealSection>
      </section>

      {/* ── Monedas disponibles ── */}
      <section style={{ padding: 'clamp(56px,7vw,80px) clamp(24px,6vw,80px)', background: 'var(--bg-alt)' }}>
        <RevealSection>
          <div style={{ maxWidth: 1100, margin: '0 auto', textAlign: 'center' as const }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--primary)', letterSpacing: '0.12em', fontFamily: 'DM Sans', marginBottom: 8 }}>
              CATÁLOGO
            </div>
            <h2 className="font-display" style={{ fontSize: 'clamp(24px, 2.5vw, 36px)', fontWeight: 500, color: 'var(--text)', letterSpacing: '-0.02em', marginBottom: 48 }}>
              Monedas disponibles
            </h2>
            <div style={{ display: 'flex', gap: 20, justifyContent: 'center', flexWrap: 'wrap' as const }}>
              {currencies.map(c => (
                <div key={c.code} className="ge-card" style={{ padding: '20px 28px', display: 'flex', flexDirection: 'column' as const, alignItems: 'center', gap: 8, minWidth: 130 }}>
                  <CurrencyIcon code={c.code} size={32} />
                  <div style={{ fontFamily: 'JetBrains Mono', fontWeight: 700, fontSize: 15, color: 'var(--text)' }}>{c.code}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>{c.name.split(' ').slice(0, 2).join(' ')}</div>
                </div>
              ))}
              <div className="ge-card" style={{ padding: '20px 28px', display: 'flex', flexDirection: 'column' as const, alignItems: 'center', gap: 8, minWidth: 130, border: '1px dashed var(--border)' }}>
                <AppIcon name="plus" size={32} style={{ opacity: 0.4 }} />
                <div style={{ fontFamily: 'DM Sans', fontWeight: 600, fontSize: 13, color: 'var(--text-3)' }}>Próximamente</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>Más monedas</div>
              </div>
            </div>
          </div>
        </RevealSection>
      </section>

      {/* ── Footer ── */}
      <footer style={{ background: 'var(--surface)', borderTop: '1px solid var(--border)', padding: 'clamp(40px,5vw,56px) clamp(24px,6vw,80px) 32px' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 48, marginBottom: 48 }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, color: 'var(--text)' }}>
                <div style={{ color: 'var(--primary)' }}>
                  <AppIcon name="globe" size={24} />
                </div>
                <span style={{ fontFamily: 'Fraunces, serif', fontWeight: 600, fontSize: 16, letterSpacing: '-0.02em' }}>
                  GLOBAL EXCHANGE
                </span>
              </div>
              <p style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text-3)', fontFamily: 'DM Sans', maxWidth: 240 }}>
                Casa de cambios líder en Paraguay. Cotizaciones transparentes y operaciones seguras.
              </p>
            </div>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.1em', marginBottom: 16, fontFamily: 'DM Sans' }}>NAVEGACIÓN</div>
              {['Inicio', 'Cotizaciones', 'Conversor', 'Seguridad'].map(l => (
                <a key={l} href={`#${l.toLowerCase()}`} style={{ display: 'block', fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans', marginBottom: 10, textDecoration: 'none' }}
                  onMouseEnter={e => (e.currentTarget.style.color = 'var(--primary)')}
                  onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-2)')}>
                  {l}
                </a>
              ))}
            </div>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.1em', marginBottom: 16, fontFamily: 'DM Sans' }}>LEGAL</div>
              {['Términos de uso', 'Privacidad'].map(l => (
                <a key={l} href="#" style={{ display: 'block', fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans', marginBottom: 10, textDecoration: 'none' }}>{l}</a>
              ))}
            </div>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '0.1em', marginBottom: 16, fontFamily: 'DM Sans' }}>CONTACTO</div>
              <div style={{ fontSize: 13, color: 'var(--text-2)', fontFamily: 'DM Sans', lineHeight: 1.7 }}>
                <div>Asunción, Paraguay</div>
                <div style={{ marginTop: 8 }}>info@globalexchange.com.py</div>
              </div>
            </div>
          </div>
          <div style={{ borderTop: '1px solid var(--border)', paddingTop: 24, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' as const, gap: 12 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>
              © 2026 Global Exchange. Todos los derechos reservados.
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Sans' }}>
              Asunción, Paraguay · Habilitado por el BCP
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
