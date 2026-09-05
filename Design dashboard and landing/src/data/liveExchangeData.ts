import { currencies } from "./mockData";
import { exchangePairs, type PairCode, type PairStatus } from "./mapExchangeData";

// Fuente única de cotizaciones para el Live Exchange Board (Hero y Login).
// Se deriva de mockData (vía mapExchangeData) para no duplicar valores:
// la misma compra/venta/variación que usan Cotizaciones del Día y Conversor.

export interface LiveQuote {
  code: PairCode;
  pair: string;
  name: string;
  subtitle: string;
  buy: string;
  sell: string;
  buyValue: number;
  sellValue: number;
  change: string;
  changeValue: number;
  status: PairStatus;
  updated: string;
  decimals: number;
  scale: number;
  sparkData: number[];
}

function scaleFor(code: PairCode): number {
  return code === "ARS" ? 1 : 1000;
}

function decimalsFor(code: PairCode): number {
  return code === "ARS" ? 2 : 3;
}

export const liveQuotes: LiveQuote[] = exchangePairs.map((p) => {
  const c = currencies.find((x) => x.code === p.code)!;
  return {
    code: p.code,
    pair: p.label,
    name: c.name,
    subtitle: `${c.name} / Guaraní paraguayo`,
    buy: p.buy,
    sell: p.sell,
    buyValue: c.buy,
    sellValue: c.sell,
    change: p.change,
    changeValue: c.change,
    status: p.status,
    updated: p.updated,
    decimals: decimalsFor(p.code),
    scale: scaleFor(p.code),
    sparkData: c.sparkData,
  };
});

export const BASE_CODE = "USD" as const;

export const QUOTE_ORDER: PairCode[] = ["USD", "EUR", "BRL", "ARS"];
