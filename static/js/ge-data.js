/*
 * MOCK — Datos simulados de referencia para la capa frontend.
 *
 * Separación intencional de datos demostrativos y lógica de presentación.
 * Ningún dato de este archivo proviene del backend: es un contrato tentativo
 * que deberá reemplazarse cuando existan los endpoints correspondientes.
 *
 * Reemplazos previstos por dataset:
 *  - GECURRENCIES        -> GET   /monedas/                    (HU-36)
 *  - GEEXCHANGE          -> GET   /tasas/ (pares calculados)   (HU-17)
 *  - GECURRENCY_DATA_BY_FILTER -> GET /tasas/historico/        (HU-17/HU-21)
 *  - GEEXTERNAL_RATES    -> GET fuente externa (BCP / BCPV)    (HU-21)
 *  - GEPAYMENTS          -> GET   /pagos/                      (HU-37)
 *  - GECLIENTS           -> GET   /clientes/                   (HU-37)
 *  - GEDEMO_UPDATED_AT   -> de la cabecera de cada respuesta.
 *
 * La lógica de conversión del simulador debe permanecer en el backend;
 * este archivo solo alimenta la UI en ausencia de servicios reales.
 */
window.GEData = (function () {
  'use strict';

  var GECURRENCIES = [
    { code: 'USD', name: 'Dólar estadounidense', flag: '\uD83C\uDDFA\uD83C\uDDF8', buy: 7480, sell: 7560, change: 0.42, trend: 'up', updated: 'hace 2 min', symbol: '$', sparkData: [7310, 7340, 7280, 7360, 7400, 7380, 7420, 7460, 7480] },
    { code: 'EUR', name: 'Euro', flag: '\uD83C\uDDEA\uD83C\uDDFA', buy: 8120, sell: 8210, change: -0.18, trend: 'down', updated: 'hace 3 min', symbol: '\u20AC', sparkData: [8220, 8180, 8160, 8200, 8170, 8140, 8130, 8125, 8120] },
    { code: 'BRL', name: 'Real brasileño', flag: '\uD83C\uDDE7\uD83C\uDDF7', buy: 1340, sell: 1380, change: 1.15, trend: 'up', updated: 'hace 5 min', symbol: 'R$', sparkData: [1280, 1295, 1310, 1320, 1305, 1325, 1335, 1338, 1340] },
    { code: 'ARS', name: 'Peso argentino', flag: '\uD83C\uDDE6\uD83C\uDDF7', buy: 7.4, sell: 7.8, change: -2.3, trend: 'down', updated: 'hace 8 min', symbol: 'A$', sparkData: [8.2, 8.0, 7.9, 7.85, 7.8, 7.75, 7.65, 7.55, 7.4] },
    { code: 'PYG', name: 'Guaraní paraguayo', flag: '\uD83C\uDDF5\uD83C\uDDFE', buy: 1, sell: 1, change: 0, trend: 'neutral', updated: 'hace 1 min', symbol: '\u20B2', sparkData: [1, 1, 1, 1, 1, 1, 1, 1, 1] }
  ];

  var GEEXCHANGE = {
    USD: { PYG: 7480, EUR: 0.918, BRL: 5.62, ARS: 1012 },
    EUR: { PYG: 8120, USD: 1.089, BRL: 6.12, ARS: 1102 },
    BRL: { PYG: 1340, USD: 0.178, EUR: 0.163, ARS: 180 },
    ARS: { PYG: 7.4, USD: 0.00099, EUR: 0.00091, BRL: 0.0056 },
    PYG: { USD: 0.000134, EUR: 0.000123, BRL: 0.000746, ARS: 0.135 }
  };

  var GECURRENCY_DATA_BY_FILTER = {
    'Hoy': [
      { code: 'USD', sparkData: [7462, 7455, 7470, 7465, 7478, 7473, 7480, 7478, 7480], change: 0.42, buy: 7480, sell: 7560 },
      { code: 'EUR', sparkData: [8135, 8128, 8124, 8130, 8122, 8118, 8121, 8119, 8120], change: -0.18, buy: 8120, sell: 8210 },
      { code: 'BRL', sparkData: [1325, 1330, 1332, 1338, 1335, 1338, 1340, 1338, 1340], change: 1.15, buy: 1340, sell: 1380 },
      { code: 'ARS', sparkData: [7.58, 7.55, 7.52, 7.5, 7.47, 7.45, 7.42, 7.41, 7.4], change: -2.3, buy: 7.4, sell: 7.8 }
    ],
    '7D': [
      { code: 'USD', sparkData: [7390, 7410, 7350, 7430, 7450, 7420, 7460, 7470, 7480], change: 1.22, buy: 7480, sell: 7560 },
      { code: 'EUR', sparkData: [8190, 8175, 8160, 8145, 8130, 8140, 8125, 8121, 8120], change: -0.85, buy: 8120, sell: 8210 },
      { code: 'BRL', sparkData: [1290, 1305, 1315, 1320, 1328, 1332, 1338, 1340, 1340], change: 3.88, buy: 1340, sell: 1380 },
      { code: 'ARS', sparkData: [7.9, 7.82, 7.75, 7.68, 7.62, 7.55, 7.48, 7.43, 7.4], change: -6.33, buy: 7.4, sell: 7.8 }
    ],
    '30D': [
      { code: 'USD', sparkData: [7200, 7250, 7310, 7280, 7360, 7400, 7380, 7420, 7480], change: 3.89, buy: 7480, sell: 7560 },
      { code: 'EUR', sparkData: [8350, 8290, 8270, 8240, 8210, 8195, 8175, 8145, 8120], change: -2.75, buy: 8120, sell: 8210 },
      { code: 'BRL', sparkData: [1220, 1245, 1260, 1285, 1295, 1310, 1320, 1335, 1340], change: 9.84, buy: 1340, sell: 1380 },
      { code: 'ARS', sparkData: [9.2, 8.9, 8.6, 8.3, 8.1, 7.9, 7.7, 7.55, 7.4], change: -19.57, buy: 7.4, sell: 7.8 }
    ],
    '90D': [
      { code: 'USD', sparkData: [7310, 7340, 7280, 7360, 7400, 7380, 7420, 7460, 7480], change: 2.32, buy: 7480, sell: 7560 },
      { code: 'EUR', sparkData: [8220, 8180, 8160, 8200, 8170, 8140, 8130, 8125, 8120], change: -1.21, buy: 8120, sell: 8210 },
      { code: 'BRL', sparkData: [1280, 1295, 1310, 1320, 1305, 1325, 1335, 1338, 1340], change: 4.69, buy: 1340, sell: 1380 },
      { code: 'ARS', sparkData: [8.2, 8.0, 7.9, 7.85, 7.8, 7.75, 7.65, 7.55, 7.4], change: -9.76, buy: 7.4, sell: 7.8 }
    ],
    '1A': [
      { code: 'USD', sparkData: [6820, 6950, 7100, 7050, 7200, 7350, 7300, 7420, 7480], change: 9.68, buy: 7480, sell: 7560 },
      { code: 'EUR', sparkData: [8850, 8720, 8640, 8560, 8480, 8400, 8310, 8210, 8120], change: -8.25, buy: 8120, sell: 8210 },
      { code: 'BRL', sparkData: [1120, 1150, 1180, 1210, 1240, 1270, 1295, 1320, 1340], change: 19.64, buy: 1340, sell: 1380 },
      { code: 'ARS', sparkData: [12.4, 11.8, 11.2, 10.6, 10.0, 9.4, 8.8, 8.1, 7.4], change: -40.32, buy: 7.4, sell: 7.8 }
    ]
  };

  var GEPAYMENTS = [
    { id: 1, name: 'Banco Familiar', type: 'Cuenta bancaria', account: '***4567', client: 'KNG S.A.', status: 'Activo' },
    { id: 2, name: 'Billetera Tigo', type: 'Billetera electrónica', account: '***8901', client: 'KNG S.A.', status: 'Activo' },
    { id: 3, name: 'Banco Itaú', type: 'Cuenta bancaria', account: '***1234', client: 'Importadora del Norte', status: 'Inactivo' }
  ];

  var GECLIENTS = ['KNG S.A.', 'Importadora del Norte', 'Exportaciones Río S.R.L.'];

  var GEEXTERNAL_RATES = [
    { code: 'USD', source: 'Banco Central del Paraguay', buy: 7445, sell: 7455, updated: '31/08/2026 · 09:30' },
    { code: 'EUR', source: 'Banco Central del Paraguay', buy: 8080, sell: 8105, updated: '31/08/2026 · 09:30' },
    { code: 'BRL', source: 'Banco Central del Paraguay', buy: 1330, sell: 1342, updated: '31/08/2026 · 09:30' },
    { code: 'ARS', source: 'Banco Central del Paraguay', buy: 7.38, sell: 7.42, updated: '31/08/2026 · 09:30' }
  ];

  var GEDEMO_UPDATED_AT = '31/08/2026 · 10:24';

  function currencyByCode(code) {
    for (var i = 0; i < GECURRENCIES.length; i++) {
      if (GECURRENCIES[i].code === code) return GECURRENCIES[i];
    }
    return null;
  }

  function rate(from, to) {
    if (from === to) return 1;
    var table = GEEXCHANGE[from];
    if (table && typeof table[to] === 'number') return table[to];
    var buyFrom = currencyByCode(from);
    var buyTo = currencyByCode(to);
    if (buyFrom && buyTo) return buyFrom.buy / buyTo.buy;
    return 1;
  }

  return {
    currencies: GECURRENCIES,
    exchange: GEEXCHANGE,
    dataByFilter: GECURRENCY_DATA_BY_FILTER,
    externalRates: GEEXTERNAL_RATES,
    payments: GEPAYMENTS,
    clients: GECLIENTS,
    updatedAt: GEDEMO_UPDATED_AT,
    currencyByCode: currencyByCode,
    rate: rate
  };
})();