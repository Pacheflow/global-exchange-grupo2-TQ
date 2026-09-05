import { useEffect, useRef, useState } from "react";
import Sparkline from "@/components/Sparkline";
import { liveQuotes, BASE_CODE, type LiveQuote } from "@/data/liveExchangeData";
import type { PairCode } from "@/data/mapExchangeData";
import CurrencyIcon from "@/components/icons/CurrencyIcon";

export interface LiveExchangeBoardProps {
  variant?: "hero" | "auth";
  animate?: boolean;
}

type FlashState = {
  code: PairCode;
  dir: 1 | -1;
  buy: number;
  sell: number;
} | null;

// Paleta consistente con el fondo navy del Hero y del panel izquierdo del
// Login (zonas permanentemente oscuras dentro del brand actual).
const C = {
  line: "rgba(59, 91, 255, 0.22)",
  lineStrong: "rgba(59, 91, 255, 0.34)",
  accent: "#3B5BFF",
  accentSoft: "#6B8AFF",
  text: "#E8F2FF",
  text2: "#C8DEFF",
  muted: "#8BA8E0",
  faint: "#4E6E9A",
  micro: "#2A4070",
  success: "#22C55E",
  danger: "#F87171",
  panel: "rgba(13, 30, 74, 0.42)",
  hover: "rgba(59, 91, 255, 0.10)",
};

const CAPS: React.CSSProperties = {
  fontFamily: "DM Sans, sans-serif",
  textTransform: "uppercase",
  letterSpacing: "0.16em",
  fontSize: 9,
  fontWeight: 700,
  color: C.faint,
};

const MONO: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace",
  fontVariantNumeric: "tabular-nums",
};

function formatValue(q: LiveQuote, v: number): string {
  return (v / q.scale).toFixed(q.decimals);
}

function formatVariation(value: number): string {
  return `${value >= 0 ? "+" : "-"}${Math.abs(value).toFixed(2)}%`;
}

function useCountUp(target: number, triggered: boolean, duration: number): number {
  const [value, setValue] = useState(0);
  const rafRef = useRef(0);
  const fromRef = useRef(0);

  useEffect(() => {
    cancelAnimationFrame(rafRef.current);
    if (!triggered) {
      setValue(0);
      fromRef.current = 0;
      return;
    }
    const from = fromRef.current;
    const start = performance.now();
    const step = (now: number) => {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      const v = from + (target - from) * eased;
      setValue(v);
      if (p < 1) {
        rafRef.current = requestAnimationFrame(step);
      } else {
        fromRef.current = target;
      }
    };
    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, triggered, duration]);

  return value;
}

function Hairline({ style }: { style?: React.CSSProperties }) {
  return (
    <div
      style={{
        height: 1,
        background: `linear-gradient(90deg, ${C.line}, transparent)`,
        ...style,
      }}
    />
  );
}

function trendFor(status: LiveQuote["status"]): "up" | "down" | "neutral" {
  if (status === "positive") return "up";
  if (status === "negative") return "down";
  return "neutral";
}

function stageStyle(visible: boolean, delay = 0): React.CSSProperties {
  return {
    opacity: visible ? 1 : 0,
    transform: visible ? "translateY(0)" : "translateY(10px)",
    visibility: visible ? "visible" : "hidden",
    pointerEvents: visible ? "auto" : "none",
    transition: "opacity 0.55s ease, transform 0.55s ease, visibility 0s linear",
    transitionDelay: visible ? `${delay}ms` : "0ms",
  };
}

function PairPrice({
  quote,
  target,
  triggered,
  color,
}: {
  quote: LiveQuote;
  target: number;
  triggered: boolean;
  color: string;
}) {
  const value = useCountUp(target, triggered, 700);
  return (
    <div
      style={{
        ...MONO,
        fontSize: 17,
        fontWeight: 600,
        color,
        marginTop: 4,
        transition: "color 0.4s",
      }}
    >
      {formatValue(quote, value)}
    </div>
  );
}

export default function LiveExchangeBoard({
  variant = "hero",
  animate = true,
}: LiveExchangeBoardProps) {
  const isAuth = variant === "auth";

  const [phase, setPhase] = useState(0);
  const [hover, setHover] = useState<PairCode | null>(null);
  const [pinned, setPinned] = useState<PairCode | null>(BASE_CODE);
  const [flash, setFlash] = useState<FlashState>(null);
  const [updatedText, setUpdatedText] = useState("hace 2 min");
  const flashTimerRef = useRef(0);

  // Secuencia de carga: estructura → pares → gráfico → variación → microtexto.
  useEffect(() => {
    if (!animate) {
      setPhase(4);
      return;
    }
    const times = isAuth ? [240, 680] : [260, 560, 800, 1000];
    const timers = times.map((t, i) =>
      setTimeout(() => setPhase((p) => Math.max(p, i + 1)), t),
    );
    return () => timers.forEach((t) => clearTimeout(t));
  }, [animate, isAuth]);

  // Micro-actualizaciones sutiles (solo Hero): un par salta unos puntos y
  // los colorea un instante, luego vuelve. Nada constante ni distractor.
  useEffect(() => {
    if (isAuth || !animate) return;
    const id = window.setInterval(() => {
      const q = liveQuotes[Math.floor(Math.random() * liveQuotes.length)];
      const delta = q.code === "ARS" ? 0.02 : 1.4;
      const dir: 1 | -1 = Math.random() > 0.45 ? 1 : -1;
      setFlash({
        code: q.code,
        dir,
        buy: q.buyValue + dir * delta,
        sell: q.sellValue + dir * delta,
      });
      setUpdatedText("hace 1 min");
      if (flashTimerRef.current) window.clearTimeout(flashTimerRef.current);
      flashTimerRef.current = window.setTimeout(() => setFlash(null), 1500);
    }, 7000);
    return () => {
      window.clearInterval(id);
      if (flashTimerRef.current) window.clearTimeout(flashTimerRef.current);
    };
  }, [isAuth, animate]);

  const displayCode = hover ?? pinned ?? BASE_CODE;
  const active = liveQuotes.find((q) => q.code === displayCode)!;
  const secondaries = liveQuotes.filter(
    (q) => q.code !== BASE_CODE && (isAuth ? q.code !== "ARS" : true),
  );

  const chartPhase = isAuth ? 1 : 2;
  const variationPhase = isAuth ? 2 : 3;

  const flashActive = flash && flash.code === displayCode ? flash : null;
  const bigTarget = flashActive?.buy ?? active.buyValue;
  const sellTarget = flashActive?.sell ?? active.sellValue;
  const flashColor =
    flashActive?.dir === 1 ? C.success : flashActive ? C.danger : C.text2;

  const buyCount = useCountUp(bigTarget, phase >= 1, 850);
  const sellCount = useCountUp(sellTarget, phase >= 1, 850);
  const variationCount = useCountUp(
    Math.abs(active.changeValue),
    phase >= variationPhase,
    600,
  );
  const variationText = `${active.changeValue >= 0 ? "+" : "-"}${variationCount.toFixed(2)}%`;
  const variationColor =
    active.status === "positive" ? C.success : active.status === "negative" ? C.danger : C.faint;

  const sparkTriggered = phase >= chartPhase;

  const statusDot = (
    <span
      className="animate-pulse"
      style={{
        width: 6,
        height: 6,
        borderRadius: "50%",
        background: C.success,
        display: "inline-block",
        flexShrink: 0,
      }}
    />
  );

  return (
    <div
      className="animate-fade-in"
      style={{
        width: "100%",
        maxWidth: isAuth ? 480 : "min(100%, 640px)",
        background: C.panel,
        border: `1px solid ${C.line}`,
        borderRadius: isAuth ? 12 : 14,
        padding: isAuth ? "26px 28px" : "clamp(22px, 2vw, 30px)",
        boxShadow: "inset 0 0 60px rgba(59, 91, 255, 0.05)",
        position: "relative",
      }}
    >
      {isAuth ? (
        <>
          {/* Header microtext */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 22 }}>
            <span style={CAPS}>{`GLOBAL MARKET · REF ${isAuth ? "003" : "001"}`}</span>
            <span style={{ display: "flex", alignItems: "center", gap: 6, ...CAPS }}>
              {statusDot} LIVE
            </span>
          </div>

          {/* Primary quote */}
          <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16 }}>
            <div>
              <div style={{ ...MONO, fontSize: 13, fontWeight: 700, color: C.text2, letterSpacing: "0.02em", display: "flex", alignItems: "center", gap: 7 }}>
                <CurrencyIcon code={active.code} size={15} /> {active.pair}
              </div>
              <div style={{ fontSize: 11, color: C.faint, fontFamily: "DM Sans, sans-serif", marginTop: 3 }}>
                {active.name}
              </div>
            </div>
            <div
              style={{
                ...MONO,
                fontSize: 40,
                fontWeight: 600,
                color: flashColor,
                lineHeight: 1,
                ...stageStyle(phase >= 1),
                transition: "opacity 0.55s ease, transform 0.55s ease, visibility 0s linear, color 0.45s ease",
              }}
            >
              {formatValue(active, buyCount)}
            </div>
          </div>

          <div style={{ marginTop: 18, ...stageStyle(phase >= chartPhase) }}>
              <Sparkline
                data={active.sparkData}
                trend={trendFor(active.status)}
                width={320}
                height={54}
                color="#3B5BFF"
                fluid
                smoothDraw
                triggered={sparkTriggered}
              />
          </div>

          <div style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 14, ...stageStyle(phase >= variationPhase) }}>
              <span style={{ ...MONO, fontSize: 14, fontWeight: 700, color: variationColor }}>
                {variationText}
              </span>
              <span style={{ fontSize: 11, color: C.faint, fontFamily: "DM Sans, sans-serif" }}>
                COMPRA {formatValue(active, buyCount)} · VENTA {formatValue(active, sellCount)}
              </span>
          </div>

          <Hairline style={{ margin: "24px 0 18px" }} />

          {/* Secondary pairs (EUR · BRL) */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, ...stageStyle(phase >= variationPhase) }}>
              {secondaries.map((q, i) => {
                const qFlash = flash && flash.code === q.code ? flash : null;
                const value = qFlash?.buy ?? q.buyValue;
                const color =
                  qFlash?.dir === 1 ? C.success : qFlash?.dir === -1 ? C.danger : C.text2;
                const isSel = displayCode === q.code;
                return (
                  <div
                    key={q.code}
                    style={{
                      ...stageStyle(phase >= variationPhase, i * 90),
                      border: `1px solid ${isSel ? C.lineStrong : "transparent"}`,
                      background: isSel ? C.hover : "transparent",
                      borderRadius: 8,
                      padding: "10px 12px",
                      cursor: "pointer",
                      transition: "opacity 0.55s ease, transform 0.55s ease, visibility 0s linear, border-color 0.2s, background 0.2s",
                    }}
                    onMouseEnter={() => setHover(q.code)}
                    onMouseLeave={() => setHover((h) => (h === q.code ? null : h))}
                    onClick={() => setPinned((p) => (p === q.code ? null : q.code))}
                  >
                    <div style={{ fontSize: 10, color: C.faint, fontFamily: "DM Sans", fontWeight: 600, display: "flex", alignItems: "center", gap: 5 }}>
                      <CurrencyIcon code={q.code} size={12} /> {q.pair}
                    </div>
                    <PairPrice quote={q} target={value} triggered={phase >= variationPhase} color={color} />
                    <div style={{ fontSize: 11, fontWeight: 700, color: variationColor, marginTop: 2, fontFamily: "DM Sans" }}>
                      {formatVariation(q.changeValue)}
                    </div>
                  </div>
                );
              })}
          </div>

          <div style={{ marginTop: 20, display: "flex", justifyContent: "space-between", alignItems: "center", ...stageStyle(phase >= 2) }}>
              <span style={{ fontSize: 10, color: C.micro, fontFamily: "DM Sans", letterSpacing: "0.1em" }}>
                ASUNCIÓN · PARAGUAY · BASE PYG
              </span>
              <span style={{ fontSize: 10, color: C.micro, fontFamily: "DM Sans", letterSpacing: "0.1em" }}>
                ACTUALIZADO · {updatedText}
              </span>
          </div>
        </>
      ) : (
        <>
          {/* Header microtext */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18 }}>
            <div>
              <div style={{ ...CAPS, fontSize: 10, color: C.accentSoft }}>Global Market</div>
              <div style={{ ...CAPS, marginTop: 5 }}>GE · Market 001</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 6, ...CAPS }}>
                {statusDot} Market Status
              </div>
              <div style={{ ...CAPS, marginTop: 5 }}>Asunción · Paraguay</div>
            </div>
          </div>

          <Hairline />

          {/* Primary quote */}
          <div style={{ marginTop: 20, ...stageStyle(phase >= 1) }}>
              <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16 }}>
                <div>
                  <div style={{ ...MONO, fontSize: 14, fontWeight: 700, color: C.text2, letterSpacing: "0.02em", display: "flex", alignItems: "center", gap: 7 }}>
                    <CurrencyIcon code={active.code} size={16} /> {active.pair}
                  </div>
                  <div style={{ fontSize: 12, color: C.faint, fontFamily: "DM Sans, sans-serif", marginTop: 4 }}>
                    {active.subtitle}
                  </div>
                </div>
                <div
                  style={{
                    ...MONO,
                    fontSize: "clamp(38px, 3.6vw, 54px)",
                    fontWeight: 600,
                    color: flashColor,
                    transition: "color 0.45s ease",
                    lineHeight: 0.95,
                  }}
                >
                  {formatValue(active, buyCount)}
                </div>
              </div>

              {/* Compra / Venta / Variación */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", marginTop: 18, border: `1px solid ${C.line}`, borderRadius: 10, overflow: "hidden" }}>
                {[
                  { label: "Compra", value: formatValue(active, buyCount), color: C.text2 },
                  { label: "Venta", value: formatValue(active, sellCount), color: C.text2 },
                  {
                    label: "Variación",
                    value: phase >= variationPhase ? variationText : "···",
                    color: phase >= variationPhase ? variationColor : C.micro,
                  },
                ].map((cell, i) => (
                  <div
                    key={cell.label}
                    style={{
                      padding: "10px 12px",
                      borderLeft: i > 0 ? `1px solid ${C.line}` : "none",
                    }}
                  >
                    <div style={CAPS}>{cell.label} · PYG</div>
                    <div style={{ ...MONO, fontSize: 18, fontWeight: 600, color: cell.color, marginTop: 5, transition: "color 0.4s" }}>
                      {cell.value}
                    </div>
                  </div>
                ))}
              </div>

              {/* Primary chart */}
              <div style={{ marginTop: 18, ...stageStyle(phase >= chartPhase) }}>
                  <Sparkline
                    data={active.sparkData}
                    trend={trendFor(active.status)}
                    width={560}
                    height={82}
                    color="#3B5BFF"
                    fluid
                    smoothDraw
                    triggered={sparkTriggered}
                  />
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
                    <span style={{ fontSize: 9, color: C.micro, fontFamily: "DM Sans", letterSpacing: "0.14em" }}>
                      EVOLUCIÓN · 15 MIN
                    </span>
                    <span style={{ fontSize: 9, color: C.micro, fontFamily: "DM Sans", letterSpacing: "0.14em" }}>
                      {active.pair}
                    </span>
                  </div>
              </div>
            </div>

          <Hairline style={{ marginTop: 20 }} />

          {/* Secondary pairs */}
          <div style={{ marginTop: 12, ...stageStyle(phase >= variationPhase) }}>
              <div style={{ ...CAPS, marginBottom: 8 }}>Mercado</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
                {secondaries.map((q, i) => {
                  const qFlash = flash && flash.code === q.code ? flash : null;
                  const value = qFlash?.buy ?? q.buyValue;
                  const valueColor =
                    qFlash?.dir === 1
                      ? C.success
                      : qFlash?.dir === -1
                        ? C.danger
                        : C.text2;
                  const isSel = displayCode === q.code;
                  return (
                    <div
                      key={q.code}
                      style={{
                        ...stageStyle(phase >= variationPhase, i * 90),
                        border: `1px solid ${isSel ? C.lineStrong : C.line}`,
                        background: isSel ? C.hover : "transparent",
                        borderRadius: 8,
                        padding: "8px 10px",
                        cursor: "pointer",
                        transition: "opacity 0.55s ease, transform 0.55s ease, visibility 0s linear, border-color 0.2s, background 0.2s",
                      }}
                      onMouseEnter={() => setHover(q.code)}
                      onMouseLeave={() => setHover((h) => (h === q.code ? null : h))}
                      onClick={() => setPinned((p) => (p === q.code ? null : q.code))}
                    >
                      <div style={{ fontSize: 10, color: C.faint, fontFamily: "DM Sans", fontWeight: 600, display: "flex", alignItems: "center", gap: 5 }}>
                        <CurrencyIcon code={q.code} size={12} /> {q.pair}
                      </div>
                      <PairPrice quote={q} target={value} triggered={phase >= variationPhase} color={valueColor} />
                      <div style={{ fontSize: 11, fontWeight: 700, color: variationColor, marginTop: 3, fontFamily: "DM Sans" }}>
                        {formatVariation(q.changeValue)}
                      </div>
                    </div>
                  );
                })}
              </div>
          </div>

          {/* Footer microtext */}
          <div style={{ marginTop: 18, display: "flex", justifyContent: "space-between", alignItems: "center", ...stageStyle(phase >= 4) }}>
              <span style={{ fontSize: 9, color: C.micro, fontFamily: "DM Sans", letterSpacing: "0.14em" }}>
                LIVE EXCHANGE BOARD · REF 001
              </span>
              <span style={{ fontSize: 9, color: C.micro, fontFamily: "DM Sans", letterSpacing: "0.14em" }}>
                ACTUALIZADO · {updatedText.toUpperCase()}
              </span>
          </div>
        </>
      )}
    </div>
  );
}
