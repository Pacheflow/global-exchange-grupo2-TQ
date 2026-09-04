import { useEffect, useRef, useState, type ReactNode } from "react";

import {
  AVAILABLE_CURRENCIES,
  DEMO_UPDATED_AT,
  MARKET_RATES,
  RATE_PERIODS,
  type CurrencyCode,
  type RatePeriod,
} from "../data/landingData";
import { AppIcon, type AppIconName } from "./icons/AppIcon";
import { MarketBoard } from "./MarketBoard";
import { Sparkline } from "./Sparkline";
import "./landing.css";

export interface LandingProps {
  authenticated?: string;
  primaryActionLabel?: string;
  primaryActionUrl?: string;
  loginUrl?: string;
  registerUrl?: string;
}

interface FeatureItem {
  icon: AppIconName;
  title: string;
  description: string;
}

const SECURITY_FEATURES: FeatureItem[] = [
  { icon: "authentication", title: "Autenticación segura", description: "El acceso se protege mediante el flujo OIDC gestionado por Django y Keycloak." },
  { icon: "roles", title: "Roles y permisos", description: "Cada opción se habilita con los roles que entrega el backend, sin permisos duplicados en React." },
  { icon: "file-check", title: "Confirmación de operaciones", description: "La interfaz está preparada para incorporar confirmaciones explícitas cuando el módulo esté disponible." },
  { icon: "activity", title: "Trazabilidad completa", description: "La experiencia visual contempla el seguimiento de acciones y comprobantes en futuras etapas." },
];

function Reveal({ children, className = "" }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element || !("IntersectionObserver" in window)) {
      element?.classList.add("is-visible");
      return;
    }
    const showFallback = window.setTimeout(() => {
      element.classList.add("is-visible");
    }, 200);
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        element.classList.add("is-visible");
        window.clearTimeout(showFallback);
        observer.disconnect();
      }
    }, { threshold: 0.02, rootMargin: "0px 0px 80px" });
    observer.observe(element);
    return () => {
      window.clearTimeout(showFallback);
      observer.disconnect();
    };
  }, []);

  return <div ref={ref} className={`ge-reveal ${className}`}>{children}</div>;
}

function formatMoney(value: number): string {
  const absolute = Math.abs(value);
  const maximumFractionDigits = absolute > 0 && absolute < 0.01
    ? 6
    : absolute < 100
      ? 4
      : 2;
  return value.toLocaleString("es-PY", {
    minimumFractionDigits: absolute > 0 && absolute < 0.01 ? 6 : 0,
    maximumFractionDigits,
  });
}

function CurrencyConverter() {
  const [amount, setAmount] = useState("100000");
  const [from, setFrom] = useState<CurrencyCode>("PYG");
  const [to, setTo] = useState<CurrencyCode>("BRL");
  const [swapping, setSwapping] = useState(false);
  const fromCurrency = AVAILABLE_CURRENCIES.find((currency) => currency.code === from)!;
  const toCurrency = AVAILABLE_CURRENCIES.find((currency) => currency.code === to)!;
  const numericAmount = Number.parseFloat(amount) || 0;
  const rate = fromCurrency.pygPerUnit / toCurrency.pygPerUnit;
  const result = numericAmount * rate;

  const swap = () => {
    setSwapping(true);
    setFrom(to);
    setTo(from);
    window.setTimeout(() => setSwapping(false), 320);
  };

  return (
    <div className="ge-converter-card">
      <div className="ge-converter-card__field">
        <label htmlFor="ge-converter-amount">Tú entregas</label>
        <div>
          <input
            id="ge-converter-amount"
            inputMode="decimal"
            value={amount}
            onChange={(event) => setAmount(event.target.value.replace(/[^0-9.]/g, ""))}
            aria-label="Monto a convertir"
          />
          <select value={from} onChange={(event) => setFrom(event.target.value as CurrencyCode)} aria-label="Moneda de origen">
            {AVAILABLE_CURRENCIES.map((currency) => <option value={currency.code} key={currency.code}>{currency.code}</option>)}
          </select>
        </div>
      </div>

      <div className="ge-converter-card__swap-row">
        <span />
        <button className={swapping ? "is-swapping" : ""} type="button" onClick={swap} aria-label="Invertir monedas" title="Invertir monedas">
          <AppIcon name="exchange" size={20} />
        </button>
        <span />
      </div>

      <div className="ge-converter-card__field ge-converter-card__field--result">
        <label>Recibes aproximadamente</label>
        <div>
          <output aria-live="polite">{formatMoney(result)}</output>
          <select value={to} onChange={(event) => setTo(event.target.value as CurrencyCode)} aria-label="Moneda de destino">
            {AVAILABLE_CURRENCIES.map((currency) => <option value={currency.code} key={currency.code}>{currency.code}</option>)}
          </select>
        </div>
      </div>

      <div className="ge-converter-card__rate">
        <div><small>Tipo de cambio aplicado</small><strong>1 {from} = {formatMoney(rate)} {to}</strong></div>
        <div><small>Última actualización</small><span>{DEMO_UPDATED_AT}</span></div>
      </div>
      <p className="ge-converter-card__note"><AppIcon name="info" size={16} /> Simulación gratuita · No genera transacciones ni compromisos.</p>
    </div>
  );
}

export function Landing({
  authenticated = "false",
  primaryActionLabel,
  primaryActionUrl = "/registro/",
  loginUrl = "/login/",
  registerUrl = "/registro/",
}: LandingProps) {
  const [period, setPeriod] = useState<RatePeriod>("Hoy");
  const isAuthenticated = authenticated === "true";
  const ctaLabel = primaryActionLabel || (isAuthenticated ? "Ir al dashboard" : "Crear una cuenta");

  return (
    <div className="ge-landing">
      <section className="ge-hero" id="inicio">
        <div className="ge-hero__texture" aria-hidden="true" />
        <div className="ge-hero__content">
          <div className="ge-hero__copy">
            <span className="ge-hero__badge"><i aria-hidden="true" /> Cotizaciones en tiempo real</span>
            <h1><span>Líderes en</span><strong>cambios</strong><span>en <em>Paraguay</em></span></h1>
            <div className="ge-hero__rule" />
            <p>Operaciones seguras y transparentes. Una experiencia de cambio de divisas diseñada para el mercado paraguayo.</p>
            <div className="ge-hero__actions">
              <a className="ge-landing-button ge-landing-button--primary" href="#cotizaciones">Ver cotizaciones</a>
              <a className="ge-landing-button ge-landing-button--secondary" href="#conversor">Convertir moneda</a>
            </div>
          </div>
          <div className="ge-hero__board"><MarketBoard /></div>
        </div>
        <a className="ge-hero__scroll" href="#cotizaciones" aria-label="Ir a cotizaciones del día"><AppIcon name="chevron-down" size={20} /></a>
      </section>

      <section className="ge-landing-section" id="cotizaciones">
        <Reveal>
          <header className="ge-section-header ge-section-header--split">
            <div><span>Mercado</span><h2>Cotizaciones del Día</h2><p>Valores de referencia con base en guaraní paraguayo. Datos demostrativos hasta integrar la API.</p></div>
            <div className="ge-periods" aria-label="Período de cotizaciones">
              {RATE_PERIODS.map((item) => <button type="button" key={item} className={period === item ? "is-active" : ""} onClick={() => setPeriod(item)}>{item}</button>)}
            </div>
          </header>
          <div className="ge-rate-grid">
            {MARKET_RATES.map((rate) => (
              <article className="ge-rate-card" key={rate.code}>
                <header><div><span>{rate.code}</span><small>{rate.name}</small></div><strong className={rate.change >= 0 ? "is-positive" : "is-negative"}>{rate.change >= 0 ? "+" : ""}{rate.change.toFixed(2)}%</strong></header>
                <div className="ge-rate-card__chart"><Sparkline data={rate.series[period]} positive={rate.change >= 0} compact label={`Evolución ${rate.code} ${period}`} /></div>
                <dl><div><dt>Compra</dt><dd>{formatMoney(rate.buy)}</dd></div><div><dt>Venta</dt><dd>{formatMoney(rate.sell)}</dd></div><div><dt>Actualizado</dt><dd>{rate.updated}</dd></div></dl>
              </article>
            ))}
          </div>
          <p className="ge-demo-note"><AppIcon name="info" size={15} /> Datos demo; la cotización final se confirmará al momento de cada operación.</p>
        </Reveal>
      </section>

      <section className="ge-landing-section ge-landing-section--alternate" id="conversor">
        <Reveal className="ge-converter-layout">
          <div className="ge-converter-copy"><span className="ge-section-kicker">Herramienta pública</span><h2>Conversor de Monedas</h2><p>Simulá conversiones entre las divisas disponibles. La lógica demo está separada para sustituirse por tasas reales sin rehacer esta interfaz.</p>
            <ul><li><AppIcon name="realtime" size={18} /> Preparado para tasas desde API</li><li><AppIcon name="globe" size={18} /> USD, EUR, BRL, ARS y PYG</li><li><AppIcon name="chart" size={18} /> Solo simulación; no genera transacciones</li></ul>
          </div>
          <CurrencyConverter />
        </Reveal>
      </section>

      <section className="ge-landing-section" id="seguridad">
        <Reveal className="ge-security-layout">
          <div className="ge-security-copy"><span className="ge-section-kicker">Confianza</span><h2>Tu seguridad es nuestra prioridad</h2><p>La nueva interfaz conserva el modelo de seguridad del sistema: Django controla la sesión y los permisos; Keycloak gestiona la identidad.</p>
            <div className="ge-security-list">{SECURITY_FEATURES.map((item) => <article key={item.title}><span><AppIcon name={item.icon} size={21} /></span><div><h3>{item.title}</h3><p>{item.description}</p></div></article>)}</div>
          </div>
          <aside className="ge-security-panel"><div className="ge-security-panel__icon"><AppIcon name="security" size={38} /></div><span>Arquitectura protegida</span><h3>Una sola fuente de identidad y permisos</h3><p>React representa las opciones que Django proporciona. No almacena tokens, no inventa roles y no reemplaza el flujo de Keycloak.</p><ul><li><AppIcon name="check" size={16} /> Sesión administrada por Django</li><li><AppIcon name="check" size={16} /> Identidad administrada por Keycloak</li><li><AppIcon name="check" size={16} /> Permisos definidos en backend</li></ul></aside>
        </Reveal>
      </section>

      <section className="ge-landing-section ge-landing-section--alternate" id="monedas">
        <Reveal>
          <header className="ge-section-header ge-section-header--center"><span>Catálogo</span><h2>Monedas disponibles</h2><p>Una vista preparada para consumir el catálogo real cuando el módulo correspondiente esté disponible.</p></header>
          <div className="ge-currency-grid">{AVAILABLE_CURRENCIES.map((currency) => <article key={currency.code}><span>{currency.symbol}</span><strong>{currency.code}</strong><small>{currency.name}</small></article>)}<article className="ge-currency-card--future"><AppIcon name="plus" size={26} /><strong>Próximamente</strong><small>Más monedas</small></article></div>
        </Reveal>
      </section>

      <section className="ge-landing-cta">
        <Reveal><span>Global Exchange</span><h2>Tu próxima operación comienza con información clara.</h2><p>Consultá el mercado, simulá una conversión y accedé a tu espacio seguro cuando estés listo.</p><div><a className="ge-landing-button ge-landing-button--primary" href={primaryActionUrl}>{ctaLabel}<AppIcon name="forward" size={17} /></a>{!isAuthenticated ? <a className="ge-landing-button ge-landing-button--secondary" href={loginUrl}>Ya tengo una cuenta</a> : null}</div></Reveal>
      </section>

      <footer className="ge-landing-footer">
        <div className="ge-landing-footer__grid"><div className="ge-landing-footer__brand"><AppIcon name="globe" size={27} /><strong>GLOBAL EXCHANGE</strong><p>Casa de cambios en Paraguay. Información transparente y acceso protegido.</p></div><nav aria-label="Navegación del pie"><strong>Navegación</strong><a href="#inicio">Inicio</a><a href="#cotizaciones">Cotizaciones</a><a href="#conversor">Conversor</a><a href="#seguridad">Seguridad</a></nav><div><strong>Plataforma</strong><a href={isAuthenticated ? primaryActionUrl : loginUrl}>{isAuthenticated ? "Dashboard" : "Iniciar sesión"}</a><a href={registerUrl}>Registrarse</a><span>Operaciones · En desarrollo</span></div><div><strong>Ubicación</strong><span>Asunción, Paraguay</span><span>Atención digital</span></div></div>
        <div className="ge-landing-footer__bottom"><span>© 2026 Global Exchange. Todos los derechos reservados.</span><span>Datos de mercado demostrativos</span></div>
      </footer>
    </div>
  );
}
