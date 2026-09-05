export interface Currency {
  code: string;
  name: string;
  buy: number;
  sell: number;
  change: number;
  trend: 'up' | 'down' | 'neutral';
  updated: string;
  sparkData: number[];
}

// Compatibilidad para los módulos existentes que todavía consumen las tasas
// desde mockData. La fuente de verdad vive separada en exchangeRates.ts.
export { exchangeRates } from './exchangeRates';

export const currencies: Currency[] = [
  {
    code: 'USD',
    name: 'Dólar estadounidense',
    buy: 7480,
    sell: 7560,
    change: 0.42,
    trend: 'up',
    updated: 'hace 2 min',
    sparkData: [7310, 7340, 7280, 7360, 7400, 7380, 7420, 7460, 7480],
  },
  {
    code: 'EUR',
    name: 'Euro',
    buy: 8120,
    sell: 8210,
    change: -0.18,
    trend: 'down',
    updated: 'hace 3 min',
    sparkData: [8220, 8180, 8160, 8200, 8170, 8140, 8130, 8125, 8120],
  },
  {
    code: 'BRL',
    name: 'Real brasileño',
    buy: 1340,
    sell: 1380,
    change: 1.15,
    trend: 'up',
    updated: 'hace 5 min',
    sparkData: [1280, 1295, 1310, 1320, 1305, 1325, 1335, 1338, 1340],
  },
  {
    code: 'ARS',
    name: 'Peso argentino',
    buy: 7.4,
    sell: 7.8,
    change: -2.30,
    trend: 'down',
    updated: 'hace 8 min',
    sparkData: [8.2, 8.0, 7.9, 7.85, 7.80, 7.75, 7.65, 7.55, 7.4],
  },
  {
    code: 'PYG',
    name: 'Guaraní paraguayo',
    buy: 1,
    sell: 1,
    change: 0,
    trend: 'neutral',
    updated: 'hace 1 min',
    sparkData: [1, 1, 1, 1, 1, 1, 1, 1, 1],
  },
];

export interface Transaction {
  id: string;
  date: string;
  client: string;
  type: 'Compra' | 'Venta';
  from: string;
  to: string;
  amount: number;
  result: number;
  rate: number;
  status: 'PAGADA' | 'PENDIENTE' | 'CANCELADA' | 'ANULADA';
  paymentMethod: string;
}

export const transactions: Transaction[] = [
  {
    id: 'TXN-2026-00412',
    date: '31/08/2026 · 10:24',
    client: 'KNG S.A.',
    type: 'Compra',
    from: 'PYG',
    to: 'USD',
    amount: 7_480_000,
    result: 1000,
    rate: 7480,
    status: 'PAGADA',
    paymentMethod: 'Cuenta bancaria',
  },
  {
    id: 'TXN-2026-00411',
    date: '30/08/2026 · 16:10',
    client: 'KNG S.A.',
    type: 'Venta',
    from: 'USD',
    to: 'PYG',
    amount: 2500,
    result: 18_900_000,
    rate: 7560,
    status: 'PAGADA',
    paymentMethod: 'Billetera electrónica',
  },
  {
    id: 'TXN-2026-00408',
    date: '29/08/2026 · 09:45',
    client: 'Importadora del Norte',
    type: 'Compra',
    from: 'PYG',
    to: 'EUR',
    amount: 16_240_000,
    result: 2000,
    rate: 8120,
    status: 'PENDIENTE',
    paymentMethod: 'Cuenta bancaria',
  },
  {
    id: 'TXN-2026-00405',
    date: '28/08/2026 · 14:30',
    client: 'Exportaciones Río S.R.L.',
    type: 'Venta',
    from: 'BRL',
    to: 'PYG',
    amount: 5000,
    result: 6_900_000,
    rate: 1380,
    status: 'PAGADA',
    paymentMethod: 'Billetera electrónica',
  },
  {
    id: 'TXN-2026-00401',
    date: '27/08/2026 · 11:15',
    client: 'KNG S.A.',
    type: 'Compra',
    from: 'PYG',
    to: 'BRL',
    amount: 2_680_000,
    result: 2000,
    rate: 1340,
    status: 'CANCELADA',
    paymentMethod: 'Cuenta bancaria',
  },
];

export interface Notification {
  id: string;
  type: 'info' | 'success' | 'warning' | 'rate';
  title: string;
  message: string;
  time: string;
  read: boolean;
}

export const notifications: Notification[] = [
  {
    id: 'n1',
    type: 'success',
    title: 'Operación confirmada',
    message: 'TXN-2026-00412 completada exitosamente por 1.000 USD.',
    time: 'hace 12 min',
    read: false,
  },
  {
    id: 'n2',
    type: 'rate',
    title: 'Cambio de tasa USD',
    message: 'La tasa de compra del USD subió a 7.480 PYG (+0.42%).',
    time: 'hace 1 hora',
    read: false,
  },
  {
    id: 'n3',
    type: 'warning',
    title: 'Operación pendiente',
    message: 'TXN-2026-00408 está esperando confirmación de pago.',
    time: 'hace 2 horas',
    read: true,
  },
  {
    id: 'n4',
    type: 'info',
    title: 'Factura emitida',
    message: 'Factura FAC-2026-00188 generada para KNG S.A.',
    time: 'hace 3 horas',
    read: true,
  },
];

export interface CashierData {
  cajaName: string;
  cajero: string;
  openTime: string;
  status: 'ABIERTA' | 'CERRADA';
  balances: { currency: string; amount: number }[];
  movements: {
    id: string;
    date: string;
    type: string;
    currency: string;
    entrada: number;
    salida: number;
    saldo: number;
    ref: string;
  }[];
}

export const cashierData: CashierData = {
  cajaName: 'Caja Central 01',
  cajero: 'Ana González',
  openTime: '08:00',
  status: 'ABIERTA',
  balances: [
    { currency: 'PYG', amount: 85_400_000 },
    { currency: 'USD', amount: 12_500 },
    { currency: 'EUR', amount: 3_200 },
    { currency: 'BRL', amount: 8_000 },
  ],
  movements: [
    { id: 'MOV-001', date: '31/08 · 10:24', type: 'Compra', currency: 'USD', entrada: 7_480_000, salida: 0, saldo: 85_400_000, ref: 'TXN-2026-00412' },
    { id: 'MOV-002', date: '31/08 · 09:15', type: 'Venta', currency: 'USD', entrada: 1_000, salida: 0, saldo: 78_000_000, ref: 'TXN-2026-00410' },
    { id: 'MOV-003', date: '31/08 · 08:50', type: 'Apertura', currency: 'PYG', entrada: 70_000_000, salida: 0, saldo: 70_000_000, ref: 'APE-001' },
  ],
};

export const adminStats = {
  activeUsers: 47,
  clients: 183,
  operationsToday: 28,
  operationsMonth: 614,
  activeCaixas: 3,
  pendingTransactions: 6,
  gainToday: 1_840_000,
  gainMonth: 48_200_000,
  gainCurrency: 'PYG',
};

export const analystRates = [
  { currency: 'USD', buy: 7480, sell: 7560, prevBuy: 7449, prevSell: 7528, updated: '31/08 · 09:00' },
  { currency: 'EUR', buy: 8120, sell: 8210, prevBuy: 8135, prevSell: 8228, updated: '31/08 · 09:00' },
  { currency: 'BRL', buy: 1340, sell: 1380, prevBuy: 1325, prevSell: 1364, updated: '31/08 · 09:00' },
  { currency: 'ARS', buy: 7.4, sell: 7.8, prevBuy: 7.58, prevSell: 7.96, updated: '31/08 · 09:00' },
];

export interface FilterCurrencyData {
  code: string;
  sparkData: number[];
  change: number;
  buy: number;
  sell: number;
}

export const currencyDataByFilter: Record<string, FilterCurrencyData[]> = {
  'Hoy': [
    { code: 'USD', sparkData: [7462, 7455, 7470, 7465, 7478, 7473, 7480, 7478, 7480], change: 0.42, buy: 7480, sell: 7560 },
    { code: 'EUR', sparkData: [8135, 8128, 8124, 8130, 8122, 8118, 8121, 8119, 8120], change: -0.18, buy: 8120, sell: 8210 },
    { code: 'BRL', sparkData: [1325, 1330, 1332, 1338, 1335, 1338, 1340, 1338, 1340], change: 1.15, buy: 1340, sell: 1380 },
    { code: 'ARS', sparkData: [7.58, 7.55, 7.52, 7.50, 7.47, 7.45, 7.42, 7.41, 7.40], change: -2.30, buy: 7.4, sell: 7.8 },
  ],
  '7D': [
    { code: 'USD', sparkData: [7390, 7410, 7350, 7430, 7450, 7420, 7460, 7470, 7480], change: 1.22, buy: 7480, sell: 7560 },
    { code: 'EUR', sparkData: [8190, 8175, 8160, 8145, 8130, 8140, 8125, 8121, 8120], change: -0.85, buy: 8120, sell: 8210 },
    { code: 'BRL', sparkData: [1290, 1305, 1315, 1320, 1328, 1332, 1338, 1340, 1340], change: 3.88, buy: 1340, sell: 1380 },
    { code: 'ARS', sparkData: [7.90, 7.82, 7.75, 7.68, 7.62, 7.55, 7.48, 7.43, 7.40], change: -6.33, buy: 7.4, sell: 7.8 },
  ],
  '30D': [
    { code: 'USD', sparkData: [7200, 7250, 7310, 7280, 7360, 7400, 7380, 7420, 7480], change: 3.89, buy: 7480, sell: 7560 },
    { code: 'EUR', sparkData: [8350, 8290, 8270, 8240, 8210, 8195, 8175, 8145, 8120], change: -2.75, buy: 8120, sell: 8210 },
    { code: 'BRL', sparkData: [1220, 1245, 1260, 1285, 1295, 1310, 1320, 1335, 1340], change: 9.84, buy: 1340, sell: 1380 },
    { code: 'ARS', sparkData: [9.20, 8.90, 8.60, 8.30, 8.10, 7.90, 7.70, 7.55, 7.40], change: -19.57, buy: 7.4, sell: 7.8 },
  ],
  '90D': [
    { code: 'USD', sparkData: [7310, 7340, 7280, 7360, 7400, 7380, 7420, 7460, 7480], change: 2.32, buy: 7480, sell: 7560 },
    { code: 'EUR', sparkData: [8220, 8180, 8160, 8200, 8170, 8140, 8130, 8125, 8120], change: -1.21, buy: 8120, sell: 8210 },
    { code: 'BRL', sparkData: [1280, 1295, 1310, 1320, 1305, 1325, 1335, 1338, 1340], change: 4.69, buy: 1340, sell: 1380 },
    { code: 'ARS', sparkData: [8.20, 8.00, 7.90, 7.85, 7.80, 7.75, 7.65, 7.55, 7.40], change: -9.76, buy: 7.4, sell: 7.8 },
  ],
  '1A': [
    { code: 'USD', sparkData: [6820, 6950, 7100, 7050, 7200, 7350, 7300, 7420, 7480], change: 9.68, buy: 7480, sell: 7560 },
    { code: 'EUR', sparkData: [8850, 8720, 8640, 8560, 8480, 8400, 8310, 8210, 8120], change: -8.25, buy: 8120, sell: 8210 },
    { code: 'BRL', sparkData: [1120, 1150, 1180, 1210, 1240, 1270, 1295, 1320, 1340], change: 19.64, buy: 1340, sell: 1380 },
    { code: 'ARS', sparkData: [12.40, 11.80, 11.20, 10.60, 10.00, 9.40, 8.80, 8.10, 7.40], change: -40.32, buy: 7.4, sell: 7.8 },
  ],
};

export const gainData = [
  { date: 'Ago 1', gain: 1_200_000 },
  { date: 'Ago 5', gain: 1_850_000 },
  { date: 'Ago 10', gain: 1_400_000 },
  { date: 'Ago 15', gain: 2_100_000 },
  { date: 'Ago 20', gain: 1_950_000 },
  { date: 'Ago 25', gain: 2_400_000 },
  { date: 'Ago 31', gain: 1_840_000 },
];
