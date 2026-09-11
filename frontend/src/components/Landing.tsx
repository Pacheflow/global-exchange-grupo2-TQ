import "@fontsource-variable/dm-sans";
import "@fontsource-variable/fraunces/wght.css";
import "@fontsource-variable/fraunces/wght-italic.css";
import "@fontsource-variable/jetbrains-mono";
import { useEffect, useRef, useState, type CSSProperties, type MouseEvent, type ReactNode } from "react";

import { AVAILABLE_CURRENCIES, DEMO_UPDATED_AT, MARKET_RATES, RATE_PERIODS, type CurrencyCode, type RatePeriod } from "../data/landingData";
import { getRateDirection } from "../utils/rateDirection";
import { AppIcon, type AppIconName } from "./icons/AppIcon";
import MarketBoard from "./MarketBoard";
import { Sparkline } from "./Sparkline";
import "./landing.css";

function RevealSection({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element || !("IntersectionObserver" in window)) {
      element?.classList.add("visible");
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        element.classList.add("visible");
        observer.disconnect();
      }
    }, { threshold: 0.1 });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return <div ref={ref} className="reveal" style={style}>{children}</div>;
}

function useAnimatedNumber(value: number, triggered: boolean, duration: number): number {
  const [display, setDisplay] = useState(value);
  const rafRef = useRef(0);
  useEffect(() => {
    cancelAnimationFrame(rafRef.current);
    if (!triggered) {
      setDisplay(value);
      return;
    }
    const start = performance.now();
    const animate = (now: number) => {
      const progress = Math.min((now - start) / duration, 1);
      setDisplay(value * (1 - Math.pow(1 - progress, 2)));
      if (progress < 1) rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [duration, triggered, value]);
  return display;
}

function formatValue(value: number): string {
  return value.toLocaleString("es-PY", { maximumFractionDigits: value < 100 ? 4 : 0 });
}

function AnimatedPrice({ value, triggered }: { value: number; triggered: boolean }) {
  return <span className="ge-animated-price">{formatValue(useAnimatedNumber(value, triggered, 700))}</span>;
}

function AnimatedChange({ value, triggered }: { value: number; triggered: boolean }) {
  const display = useAnimatedNumber(Math.abs(value), triggered, 900);
  const direction = getRateDirection(value);
  const prefix = direction === "up" ? "+" : direction === "down" ? "-" : "";
  return <span className={`is-${direction}`}>{prefix}{display.toFixed(2)}%</span>;
}

function CurrencyConverter() {
  const [amount, setAmount] = useState("100000");
  const [from, setFrom] = useState<CurrencyCode>("PYG");
  const [to, setTo] = useState<CurrencyCode>("BRL");
  const [swapping, setSwapping] = useState(false);
  const fromCurrency = AVAILABLE_CURRENCIES.find((currency) => currency.code === from)!;
  const toCurrency = AVAILABLE_CURRENCIES.find((currency) => currency.code === to)!;
  const rate = fromCurrency.pygPerUnit / toCurrency.pygPerUnit;
  const result = (Number.parseFloat(amount) || 0) * rate;
  const decimals = Math.abs(rate) < 0.01 ? 6 : 4;

  const swap = () => {
    setSwapping(true);
    setFrom(to);
    setTo(from);
    window.setTimeout(() => setSwapping(false), 320);
  };

  return (
    <div className="ge-figma-card ge-figma-converter">
      <div className="ge-figma-field">
        <label htmlFor="ge-converter-amount">Tú entregas</label>
        <div><input id="ge-converter-amount" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value.replace(/[^0-9.]/g, ""))} aria-label="Monto a convertir" /><select value={from} onChange={(event) => setFrom(event.target.value as CurrencyCode)} aria-label="Moneda de origen">{AVAILABLE_CURRENCIES.map((currency) => <option value={currency.code} key={currency.code}>{currency.code}</option>)}</select></div>
      </div>
      <div className="ge-figma-swap"><span /><button className={swapping ? "is-swapping" : ""} type="button" onClick={swap} title="Intercambiar monedas" aria-label="Intercambiar monedas"><AppIcon name="exchange" size={20} /></button><span /></div>
      <div className="ge-figma-field ge-figma-field--result">
        <label>Recibes aproximadamente</label>
        <div><output aria-live="polite">{result.toLocaleString("es-PY", { maximumFractionDigits: result < 100 ? 4 : 0 })}</output><select value={to} onChange={(event) => setTo(event.target.value as CurrencyCode)} aria-label="Moneda de destino">{AVAILABLE_CURRENCIES.map((currency) => <option value={currency.code} key={currency.code}>{currency.code}</option>)}</select></div>
      </div>
      <div className="ge-figma-rate"><div><small>Tipo de cambio aplicado</small><strong>1 {from} = {rate.toLocaleString("es-PY", { minimumFractionDigits: rate < 0.01 ? 6 : 0, maximumFractionDigits: decimals })} {to}</strong></div><div><small>Última actualización</small><span>{DEMO_UPDATED_AT}</span></div></div>
      <div className="ge-figma-simulation"><AppIcon name="info" size={15} /> Simulación gratuita · No genera ninguna transacción ni compromiso.</div>
    </div>
  );
}

const BENEFITS: { icon: AppIconName; title: string; description: string }[] = [
  { icon: "chart", title: "Cotizaciones actualizadas", description: "Tasas del mercado actualizadas continuamente a lo largo del día." },
  { icon: "security", title: "Operaciones seguras", description: "Autenticación robusta, control de acceso por roles y trazabilidad completa." },
  { icon: "history", title: "Historial centralizado", description: "Accedé a todas tus transacciones, facturas y comprobantes en un solo lugar." },
  { icon: "user", title: "Atención profesional", description: "Soporte especializado con conocimiento cambiario real." },
  { icon: "sparkles", title: "Información clara", description: "Cada operación mostrará exactamente lo que recibirás antes de confirmarla." },
  { icon: "globe", title: "Multi-moneda", description: "USD, EUR, BRL, ARS y PYG, con posibilidad de ampliar el catálogo." },
];

function scrollFromFooter(event: MouseEvent<HTMLAnchorElement>, sectionId: string) {
  const section = document.getElementById(sectionId);
  if (!section) return;

  event.preventDefault();
  event.stopPropagation();
  window.history.pushState(null, "", `#${sectionId}`);
  window.scrollTo({
    top: window.scrollY + section.getBoundingClientRect().top,
    behavior: "smooth",
  });
}

export function Landing() {
  const [period, setPeriod] = useState<RatePeriod>("90D");
  const ratesRef = useRef<HTMLDivElement>(null);
  const [ratesVisible, setRatesVisible] = useState(false);

  useEffect(() => {
    const element = ratesRef.current;
    if (!element) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setRatesVisible(true);
        observer.disconnect();
      }
    }, { threshold: 0.15 });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="ge-figma-landing">
      <section id="inicio" className="landing-hero">
        <div className="landing-dot-grid" aria-hidden="true" />
        <div className="landing-hero-content">
          <div className="landing-hero-copy">
            <div className="landing-badge animate-fade-up"><i /> Cotizaciones en tiempo real</div>
            <h1 className="animate-fade-up delay-200 font-display"><span className="landing-hero-heading-line">Líderes en</span><span className="landing-hero-heading-line landing-hero-heading-strong">cambios</span><span className="landing-hero-heading-line landing-hero-country-line">en <em className="gradient-text landing-hero-country">Paraguay</em></span></h1>
            <div className="landing-accent animate-fade-up delay-300" />
            <p className="animate-fade-up delay-400">Operaciones seguras y transparentes. La plataforma de cambio de divisas más confiable del mercado paraguayo.</p>
            <div className="landing-actions animate-fade-up delay-600"><a href="#cotizaciones" className="ge-btn-primary">Ver cotizaciones</a><a href="#conversor" className="ge-btn-outline">Convertir moneda</a></div>
          </div>
          <div className="landing-hero-board animate-fade-in delay-300"><MarketBoard variant="hero" animate /></div>
        </div>
        <a href="#cotizaciones" aria-label="Ir a Cotizaciones del Día" className="landing-hero-chevron"><AppIcon name="chevron-down" size={14} /><i /></a>
      </section>

      <section id="cotizaciones" className="figma-section figma-section--base" ref={ratesRef}>
        <RevealSection><div className="figma-content"><header className="figma-section-heading figma-section-heading--split"><div><span>Mercado</span><h2>Cotizaciones del Día</h2><p>Cotizaciones actualizadas en tiempo real. Base: Guaraní paraguayo (PYG).</p></div><div className="figma-filters">{RATE_PERIODS.map((item) => <button type="button" key={item} className={period === item ? "active" : ""} onClick={() => setPeriod(item)}>{item}</button>)}</div></header>
          <div className="figma-rates-table-wrap"><table className="figma-rates-table"><thead><tr>{["Moneda", "Compra", "Venta", period, "Variación", "Actualización"].map((heading) => <th key={heading}>{heading}</th>)}</tr></thead><tbody>{MARKET_RATES.map((rate) => {
            const direction = getRateDirection(rate.change);
            const directionIcon = direction === "up" ? "arrow-up" : direction === "down" ? "arrow-down" : "equal";
            const sparkTrend = direction === "flat" ? "neutral" : direction;
            return <tr key={rate.code}><td><strong>{rate.code}</strong><small>{rate.name}</small></td><td><span><AppIcon className={`figma-rate-direction is-${direction}`} name={directionIcon} size={15} /><AnimatedPrice value={rate.buy} triggered={ratesVisible} /></span></td><td><span><AppIcon className={`figma-rate-direction is-${direction}`} name={directionIcon} size={15} /><AnimatedPrice value={rate.sell} triggered={ratesVisible} /></span></td><td><div className="figma-table-chart"><Sparkline data={rate.series[period]} trend={sparkTrend} width={180} height={32} fluid smoothDraw triggered={ratesVisible} label={`Evolución ${rate.code} ${period}`} /></div></td><td><AnimatedChange value={rate.change} triggered={ratesVisible} /></td><td><small>{rate.updated}</small></td></tr>;
          })}</tbody></table></div>
          <div className="figma-table-footer"><span>Datos demo · actualizados al {DEMO_UPDATED_AT}</span><span>Histórico · En desarrollo <AppIcon name="forward" size={14} /></span></div>
        </div></RevealSection>
      </section>

      <section id="conversor" className="figma-section figma-section--alternate"><RevealSection><div className="figma-converter-layout"><div className="figma-copy"><span>Herramienta pública</span><h2>Conversor de Monedas</h2><p>Simula la conversión entre divisas usando las tasas actualizadas del mercado. Disponible para todos, sin necesidad de registro.</p><ul><li><AppIcon name="realtime" size={18} /> Tasas demo preparadas para conexión real</li><li><AppIcon name="globe" size={18} /> USD, EUR, BRL, ARS y PYG</li><li><AppIcon name="chart" size={18} /> Solo simulación — no genera transacciones</li></ul></div><CurrencyConverter /></div></RevealSection></section>

      <section className="figma-section figma-section--base"><RevealSection><div className="figma-content"><header className="figma-section-heading figma-section-heading--center"><span>Proceso</span><h2>Cómo funciona Global Exchange</h2></header><div className="figma-process">{[
        ["01", "Consulta la cotización", "Revisa las tasas del día para las divisas que necesitas."],
        ["02", "Simula tu conversión", "Usa nuestro conversor para estimar cuánto recibirás antes de operar."],
        ["03", "Confirma tu operación", "Elige el medio de pago y confirma cuando el módulo esté disponible."],
        ["04", "Recibe la confirmación", "Accede al comprobante desde tu panel cuando esta función esté implementada."],
      ].map(([number, title, description]) => <article key={number}><strong>{number}</strong><i /><h3>{title}</h3><p>{description}</p></article>)}</div></div></RevealSection></section>

      <section className="figma-section figma-section--alternate"><RevealSection><div className="figma-benefits"><div className="figma-copy"><span>Ventajas</span><h2>Por qué elegir Global Exchange</h2><i /><p>Una experiencia cambiaria paraguaya respaldada por acceso seguro e información clara.</p></div><div className="figma-benefits-grid">{BENEFITS.map((benefit) => <article key={benefit.title}><AppIcon name={benefit.icon} size={24} /><h3>{benefit.title}</h3><p>{benefit.description}</p></article>)}</div></div></RevealSection></section>

      <section id="seguridad" className="figma-section figma-section--base"><RevealSection><div className="figma-security"><div className="figma-copy"><span>Confianza</span><h2>Tu seguridad es nuestra prioridad</h2><p>Cada acceso a Global Exchange conserva las capas de seguridad y autorización del sistema real.</p><div className="figma-security-list">{[
        ["authentication" as AppIconName, "Autenticación segura", "Identidad administrada mediante Django y Keycloak."],
        ["roles" as AppIconName, "Roles y permisos", "Cada usuario accede únicamente a las funciones correspondientes a su rol."],
        ["file-check" as AppIconName, "Confirmación de operaciones", "Interfaz prevista para confirmaciones explícitas cuando el módulo esté disponible."],
        ["activity" as AppIconName, "Trazabilidad completa", "Interfaz prevista para el historial auditado de acciones."],
      ].map(([icon, title, description]) => <article key={title}><span><AppIcon name={icon as AppIconName} size={20} /></span><div><h3>{title}</h3><p>{description}</p></div></article>)}</div></div><div className="ge-figma-card figma-system-status"><i /><div><span>Estado del sistema</span>{[
        ["Autenticación", "Operativo", true], ["Roles y permisos", "Operativo", true], ["API de tasas", "En desarrollo", false], ["Procesamiento de órdenes", "En desarrollo", false], ["Facturación electrónica", "En desarrollo", false], ["Notificaciones", "En desarrollo", false],
      ].map(([label, status, ready]) => <div className="figma-status-row" key={String(label)}><span>{label}</span><strong className={ready ? "ready" : "pending"}><i />{status}</strong></div>)}</div></div></div></RevealSection></section>

      <section className="figma-section figma-section--alternate figma-currencies"><RevealSection><div className="figma-content"><header className="figma-section-heading figma-section-heading--center"><span>Catálogo</span><h2>Monedas disponibles</h2></header><div className="figma-currency-list">{AVAILABLE_CURRENCIES.map((currency) => <article className="ge-figma-card" key={currency.code}><AppIcon name="currency" size={32} /><strong>{currency.code}</strong><small>{currency.name.split(" ").slice(0, 2).join(" ")}</small></article>)}<article className="ge-figma-card future"><AppIcon name="plus" size={32} /><strong>Próximamente</strong><small>Más monedas</small></article></div></div></RevealSection></section>

      <footer className="figma-footer"><div className="figma-footer-grid"><div><div className="figma-footer-brand"><AppIcon name="globe" size={24} /><strong>GLOBAL EXCHANGE</strong></div><p>Casa de cambios líder en Paraguay. Cotizaciones transparentes y operaciones seguras.</p></div><nav {...{ "up-nav": "false" }} aria-label="Navegación del pie"><strong>Navegación</strong><a {...{ "up-follow": "false" }} href="#inicio" onClick={(event) => scrollFromFooter(event, "inicio")}>Inicio</a><a {...{ "up-follow": "false" }} href="#cotizaciones" onClick={(event) => scrollFromFooter(event, "cotizaciones")}>Cotizaciones</a><a {...{ "up-follow": "false" }} href="#conversor" onClick={(event) => scrollFromFooter(event, "conversor")}>Conversor</a><a {...{ "up-follow": "false" }} href="#seguridad" onClick={(event) => scrollFromFooter(event, "seguridad")}>Seguridad</a></nav><div><strong>Legal</strong><span>Términos de uso · En desarrollo</span><span>Privacidad · En desarrollo</span></div><div><strong>Contacto</strong><span>Asunción, Paraguay</span><span>info@globalexchange.com.py</span></div></div><div className="figma-footer-bottom"><span>© 2026 Global Exchange. Todos los derechos reservados.</span><span>Asunción, Paraguay</span></div></footer>
    </div>
  );
}
