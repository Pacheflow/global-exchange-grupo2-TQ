export type CurrencyCode = "PYG" | "USD" | "EUR" | "BRL" | "ARS";
export type RatePeriod = "Hoy" | "7D" | "30D" | "90D" | "1A";

export interface CurrencyRate {
  code: Exclude<CurrencyCode, "PYG">;
  name: string;
  buy: number;
  sell: number;
  change: number;
  updated: string;
  series: Record<RatePeriod, number[]>;
}

export interface AvailableCurrency {
  code: CurrencyCode;
  name: string;
  symbol: string;
  pygPerUnit: number;
}

export const RATE_PERIODS: RatePeriod[] = ["Hoy", "7D", "30D", "90D", "1A"];

export const MARKET_RATES: CurrencyRate[] = [
  {
    code: "USD",
    name: "Dólar estadounidense",
    buy: 7480,
    sell: 7560,
    change: 0.42,
    updated: "10:24",
    series: {
      Hoy: [7448, 7456, 7451, 7464, 7460, 7472, 7468, 7477, 7480],
      "7D": [7390, 7410, 7350, 7430, 7450, 7420, 7460, 7470, 7480],
      "30D": [7200, 7250, 7310, 7280, 7360, 7400, 7380, 7420, 7480],
      "90D": [7310, 7340, 7280, 7360, 7400, 7380, 7420, 7460, 7480],
      "1A": [6820, 6950, 7100, 7050, 7200, 7350, 7300, 7420, 7480],
    },
  },
  {
    code: "EUR",
    name: "Euro",
    buy: 8120,
    sell: 8210,
    change: -0.18,
    updated: "10:22",
    series: {
      Hoy: [8135, 8128, 8124, 8130, 8122, 8118, 8121, 8119, 8120],
      "7D": [8190, 8175, 8160, 8145, 8130, 8140, 8125, 8121, 8120],
      "30D": [8350, 8290, 8270, 8240, 8210, 8195, 8175, 8145, 8120],
      "90D": [8220, 8180, 8160, 8200, 8170, 8140, 8130, 8125, 8120],
      "1A": [8850, 8720, 8640, 8560, 8480, 8400, 8310, 8210, 8120],
    },
  },
  {
    code: "BRL",
    name: "Real brasileño",
    buy: 1340,
    sell: 1380,
    change: 1.15,
    updated: "10:23",
    series: {
      Hoy: [1325, 1330, 1332, 1338, 1335, 1338, 1340, 1338, 1340],
      "7D": [1290, 1305, 1315, 1320, 1328, 1332, 1338, 1340, 1340],
      "30D": [1220, 1245, 1260, 1285, 1295, 1310, 1320, 1335, 1340],
      "90D": [1280, 1295, 1310, 1320, 1305, 1325, 1335, 1338, 1340],
      "1A": [1120, 1150, 1180, 1210, 1240, 1270, 1295, 1320, 1340],
    },
  },
  {
    code: "ARS",
    name: "Peso argentino",
    buy: 7.4,
    sell: 7.8,
    change: -2.3,
    updated: "10:21",
    series: {
      Hoy: [7.58, 7.55, 7.52, 7.5, 7.47, 7.45, 7.42, 7.41, 7.4],
      "7D": [7.9, 7.82, 7.75, 7.68, 7.62, 7.55, 7.48, 7.43, 7.4],
      "30D": [9.2, 8.9, 8.6, 8.3, 8.1, 7.9, 7.7, 7.55, 7.4],
      "90D": [8.2, 8, 7.9, 7.85, 7.8, 7.75, 7.65, 7.55, 7.4],
      "1A": [12.4, 11.8, 11.2, 10.6, 10, 9.4, 8.8, 8.1, 7.4],
    },
  },
];

export const AVAILABLE_CURRENCIES: AvailableCurrency[] = [
  { code: "PYG", name: "Guaraní paraguayo", symbol: "₲", pygPerUnit: 1 },
  { code: "USD", name: "Dólar estadounidense", symbol: "$", pygPerUnit: 7480 },
  { code: "EUR", name: "Euro", symbol: "€", pygPerUnit: 8120 },
  { code: "BRL", name: "Real brasileño", symbol: "R$", pygPerUnit: 1340 },
  { code: "ARS", name: "Peso argentino", symbol: "$", pygPerUnit: 7.4 },
];

export const HERO_SERIES = [7448, 7457, 7452, 7462, 7458, 7471, 7466, 7476, 7472, 7480];

export const DEMO_UPDATED_AT = "31/08/2026 · 10:24";
