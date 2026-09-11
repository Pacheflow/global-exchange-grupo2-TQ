import { useEffect, useRef, useState } from "react";

import { MARKET_RATES, type CurrencyRate } from "../data/landingData";
import { AppIcon } from "./icons/AppIcon";
import { Sparkline } from "./Sparkline";

function formatNumber(value: number): string {
  return value.toLocaleString("es-PY", {
    minimumFractionDigits: value < 100 ? 2 : 0,
    maximumFractionDigits: value < 100 ? 2 : 0,
  });
}

function formatChange(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function useCountUp(target: number, triggered: boolean, duration = 800): number {
  const [value, setValue] = useState(0);
  const rafRef = useRef(0);
  const previousRef = useRef(0);

  useEffect(() => {
    cancelAnimationFrame(rafRef.current);
    if (!triggered) {
      setValue(0);
      previousRef.current = 0;
      return;
    }
    const initial = previousRef.current;
    const start = performance.now();
    const animate = (now: number) => {
      const progress = Math.min((now - start) / duration, 1);
      setValue(initial + (target - initial) * (1 - Math.pow(1 - progress, 3)));
      if (progress < 1) rafRef.current = requestAnimationFrame(animate);
      else previousRef.current = target;
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [duration, target, triggered]);

  return value;
}

export function MarketBoard() {
  const [phase, setPhase] = useState(0);
  const [hoveredCode, setHoveredCode] = useState<CurrencyRate["code"] | null>(null);
  const [selectedCode, setSelectedCode] = useState<CurrencyRate["code"] | null>("USD");
  const [flash, setFlash] = useState<{
    buy: number;
    code: CurrencyRate["code"];
    direction: 1 | -1;
    sell: number;
  } | null>(null);
  const flashTimerRef = useRef(0);

  useEffect(() => {
    const timers = [260, 560, 800, 1000].map((delay, index) => window.setTimeout(() => setPhase(index + 1), delay));
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, []);

  useEffect(() => {
    const interval = window.setInterval(() => {
      const quote = MARKET_RATES[Math.floor(Math.random() * MARKET_RATES.length)];
      const direction: 1 | -1 = Math.random() > 0.45 ? 1 : -1;
      const delta = quote.code === "ARS" ? 0.02 : 1.4;
      setFlash({ buy: quote.buy + direction * delta, code: quote.code, direction, sell: quote.sell + direction * delta });
      window.clearTimeout(flashTimerRef.current);
      flashTimerRef.current = window.setTimeout(() => setFlash(null), 1500);
    }, 7000);
    return () => {
      window.clearInterval(interval);
      window.clearTimeout(flashTimerRef.current);
    };
  }, []);

  const activeCode = hoveredCode ?? selectedCode ?? "USD";
  const active = MARKET_RATES.find((rate) => rate.code === activeCode) ?? MARKET_RATES[0];
  const secondaryRates = MARKET_RATES.filter((rate) => rate.code !== "USD");
  const activeFlash = flash?.code === active.code ? flash : null;
  const buy = useCountUp(activeFlash?.buy ?? active.buy, phase >= 1);
  const sell = useCountUp(activeFlash?.sell ?? active.sell, phase >= 1);
  const variation = useCountUp(Math.abs(active.change), phase >= 3, 600);

  return (
    <article className="ge-market-board" aria-label="Panel demostrativo de mercado">
      <header className="ge-market-board__header">
        <div><span className="ge-market-board__eyebrow">Global Market</span><small>GE · Market 001</small></div>
        <div className="ge-market-board__status"><span><i aria-hidden="true" /> Market Status</span><small>Asunción · Paraguay</small></div>
      </header>

      <div className={`ge-market-board__primary ge-market-stage${phase >= 1 ? " is-visible" : ""}`}>
        <div className="ge-market-board__pair">
          <span><AppIcon name="currency" size={17} /> {active.code} / PYG</span>
          <strong className={activeFlash ? (activeFlash.direction > 0 ? "is-flashing-positive" : "is-flashing-negative") : ""}>{formatNumber(buy)}</strong>
        </div>
        <small className="ge-market-board__subtitle">{active.name} / Guaraní paraguayo</small>
        <div className="ge-market-board__metrics">
          <div><small>Compra · PYG</small><strong>{formatNumber(buy)}</strong></div>
          <div><small>Venta · PYG</small><strong>{formatNumber(sell)}</strong></div>
          <div><small>Variación · PYG</small><strong className={active.change >= 0 ? "is-positive" : "is-negative"}>{active.change >= 0 ? "+" : "-"}{variation.toFixed(2)}%</strong></div>
        </div>
      </div>

      <div className={`ge-market-board__chart ge-market-stage${phase >= 2 ? " is-visible" : ""}`}>
        <Sparkline data={active.series.Hoy} trend={active.change >= 0 ? "up" : "down"} width={560} height={82} color="#3B5BFF" fluid smoothDraw triggered={phase >= 2} label={`Evolución ${active.code} PYG durante 15 minutos`} />
        <div><span>Evolución · 15 min</span><span>{active.code} / PYG</span></div>
      </div>

      <div className={`ge-market-board__market ge-market-stage${phase >= 3 ? " is-visible" : ""}`}>
        <span className="ge-market-board__market-title">Mercado</span>
        <div className="ge-market-board__market-grid">
          {secondaryRates.map((rate, index) => (
            <button
              type="button"
              key={rate.code}
              className={`${activeCode === rate.code ? "is-selected " : ""}${flash?.code === rate.code ? (flash.direction > 0 ? "is-flashing-positive" : "is-flashing-negative") : ""}`}
              style={{ transitionDelay: `${index * 90}ms` }}
              onMouseEnter={() => setHoveredCode(rate.code)}
              onMouseLeave={() => setHoveredCode(null)}
              onClick={() => setSelectedCode((selected) => selected === rate.code ? null : rate.code)}
              aria-label={`Mostrar cotización ${rate.code} PYG`}
            >
              <small>{rate.code} / PYG</small>
              <strong>{formatNumber(flash?.code === rate.code ? flash.buy : rate.buy)}</strong>
              <span className={rate.change >= 0 ? "is-positive" : "is-negative"}>{formatChange(rate.change)}</span>
            </button>
          ))}
        </div>
      </div>

      <footer className={`ge-market-board__footer ge-market-stage${phase >= 4 ? " is-visible" : ""}`}>
        <span>Live Exchange Board · Ref 001</span>
        <span><AppIcon name="clock" size={12} /> Actualizado · hace 2 min</span>
      </footer>
    </article>
  );
}
