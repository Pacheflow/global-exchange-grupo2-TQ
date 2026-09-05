import { currencies } from "./mockData";

export type PairCode = "USD" | "EUR" | "BRL" | "ARS";
export type PairStatus = "positive" | "negative" | "neutral";

export interface ExchangePair {
  code: PairCode;
  label: string;
  buy: string;
  sell: string;
  change: string;
  status: PairStatus;
  updated: string;
}

const PAIR_ORDER: PairCode[] = ["USD", "EUR", "BRL", "ARS"];

// El mock define las tasas en "miles" para USD/EUR/BRL (7480 → 7.480) y en
// unidades directas para ARS (7.4 → 7.40), igual que el resto de la app.
// Se formatea igual que en Landing/Analyst para no duplicar valores distintos.
function formatRate(code: PairCode, value: number): string {
  return code === "ARS" ? value.toFixed(2) : (value / 1000).toFixed(3);
}

function toStatus(trend: string): PairStatus {
  if (trend === "up") return "positive";
  if (trend === "down") return "negative";
  return "neutral";
}

function formatChange(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

export const exchangePairs: ExchangePair[] = PAIR_ORDER.map((code) => {
  const c = currencies.find((x) => x.code === code)!;
  return {
    code,
    label: `${code} / PYG`,
    buy: formatRate(code, c.buy),
    sell: formatRate(code, c.sell),
    change: formatChange(c.change),
    status: toStatus(c.trend),
    updated: c.updated,
  };
});

export const HUB = {
  name: "Asunción",
  longitude: -57.6333,
  latitude: -25.3,
};

export interface MapCity {
  id: string;
  name: string;
  longitude: number;
  latitude: number;
  pairCode: PairCode;
}

export const DESTINATIONS: MapCity[] = [
  { id: "nyc", name: "Nueva York", longitude: -74.006, latitude: 40.714, pairCode: "USD" },
  { id: "lon", name: "Londres", longitude: -0.1276, latitude: 51.5072, pairCode: "EUR" },
  { id: "mad", name: "Madrid", longitude: -3.7038, latitude: 40.4168, pairCode: "EUR" },
  { id: "sao", name: "São Paulo", longitude: -46.6333, latitude: -23.5505, pairCode: "BRL" },
  { id: "bue", name: "Bs. Aires", longitude: -58.3816, latitude: -34.6037, pairCode: "ARS" },
];

export interface MapArcConfig {
  curvature: number;
  width: number;
  opacity: number;
}

export const ARC_CONFIG: Record<string, MapArcConfig> = {
  nyc: { curvature: 0.18, width: 1.7, opacity: 0.8 },
  lon: { curvature: 0.24, width: 1.7, opacity: 0.8 },
  mad: { curvature: 0.24, width: 1.4, opacity: 0.65 },
  sao: { curvature: 0.09, width: 1.9, opacity: 0.9 },
  bue: { curvature: 0.06, width: 1.6, opacity: 0.85 },
};

// Destino principal de cada par, usado para posicionar el popup y el resaltado.
export const PAIR_TO_CITY: Record<PairCode, string> = {
  USD: "nyc",
  EUR: "lon",
  BRL: "sao",
  ARS: "bue",
};

export const HERO_CITY_IDS = ["nyc", "lon", "mad", "sao", "bue"] as const;
export const AUTH_CITY_IDS = ["nyc", "lon", "sao", "bue"] as const;
export const AUTH_VISIBLE_PAIRS: PairCode[] = ["USD", "EUR"];