import { HERO_SERIES, MARKET_RATES } from "../data/landingData";
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

export function MarketBoard() {
  const [usd, ...secondaryRates] = MARKET_RATES;

  return (
    <article className="ge-market-board" aria-label="Panel demostrativo de mercado">
      <header className="ge-market-board__header">
        <div>
          <span className="ge-market-board__eyebrow">Global Market</span>
          <small>GE · Market 001</small>
        </div>
        <div className="ge-market-board__status">
          <span><i aria-hidden="true" /> Market Status</span>
          <small>Asunción · Paraguay</small>
        </div>
      </header>

      <div className="ge-market-board__primary">
        <div className="ge-market-board__pair">
          <span><AppIcon name="currency" size={17} /> USD / PYG</span>
          <strong>{formatNumber(usd.buy)}</strong>
        </div>
        <div className="ge-market-board__metrics">
          <div><small>Compra · PYG</small><strong>{formatNumber(usd.buy)}</strong></div>
          <div><small>Venta · PYG</small><strong>{formatNumber(usd.sell)}</strong></div>
          <div><small>Variación · PYG</small><strong className="is-positive">{formatChange(usd.change)}</strong></div>
        </div>
      </div>

      <div className="ge-market-board__chart">
        <Sparkline data={HERO_SERIES} label="Evolución USD PYG durante 15 minutos" />
        <div><span>Evolución · 15 min</span><span>USD / PYG</span></div>
      </div>

      <div className="ge-market-board__market">
        <span className="ge-market-board__market-title">Mercado</span>
        <div className="ge-market-board__market-grid">
          {secondaryRates.map((rate) => (
            <div key={rate.code}>
              <small>{rate.code} / PYG</small>
              <strong>{formatNumber(rate.buy)}</strong>
              <span className={rate.change >= 0 ? "is-positive" : "is-negative"}>
                {formatChange(rate.change)}
              </span>
            </div>
          ))}
        </div>
      </div>

      <footer className="ge-market-board__footer">
        <span>Datos demo · preparados para API</span>
        <span><AppIcon name="clock" size={12} /> Actualizado · 10:24</span>
      </footer>
    </article>
  );
}
