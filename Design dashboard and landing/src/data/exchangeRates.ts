export type CurrencyCode = 'USD' | 'EUR' | 'BRL' | 'ARS' | 'PYG';

export type ExchangeRateTable = Record<
  string,
  Partial<Record<string, number>>
>;

// Fuente única de tasas del conversor. Una futura integración puede reemplazar
// este snapshot por la respuesta normalizada de una API sin modificar la UI.
export const exchangeRates: ExchangeRateTable = {
  USD: { PYG: 7480, EUR: 0.918, BRL: 5.62, ARS: 1012 },
  EUR: { PYG: 8120, USD: 1.089, BRL: 6.12, ARS: 1102 },
  BRL: { PYG: 1340, USD: 0.178, EUR: 0.163, ARS: 180 },
  ARS: { PYG: 7.4, USD: 0.00099, EUR: 0.00091, BRL: 0.0056 },
  PYG: { USD: 0.000134, EUR: 0.000123, BRL: 0.000746, ARS: 0.135 },
};

export function getExchangeRate(
  fromCurrency: CurrencyCode,
  toCurrency: CurrencyCode,
  rates: ExchangeRateTable = exchangeRates,
): number {
  if (fromCurrency === toCurrency) return 1;

  const directRate = rates[fromCurrency]?.[toCurrency];
  if (directRate !== undefined) return directRate;

  const inverseRate = rates[toCurrency]?.[fromCurrency];
  if (inverseRate !== undefined && inverseRate !== 0) return 1 / inverseRate;

  throw new Error(`No existe una tasa para ${fromCurrency}/${toCurrency}`);
}
