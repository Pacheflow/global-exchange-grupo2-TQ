(function () {
  "use strict";

  var RATES = [
    { code: "USD", name: "Dólar estadounidense", buy: 7480, sell: 7560, change: 0.42, series: { Hoy: [7448,7456,7451,7464,7460,7472,7468,7477,7480], "7D": [7390,7410,7350,7430,7450,7420,7460,7470,7480], "30D": [7200,7250,7310,7280,7360,7400,7380,7420,7480], "90D": [7310,7340,7280,7360,7400,7380,7420,7460,7480], "1A": [6820,6950,7100,7050,7200,7350,7300,7420,7480] } },
    { code: "EUR", name: "Euro", buy: 8120, sell: 8210, change: -0.18, series: { Hoy: [8135,8128,8124,8130,8122,8118,8121,8119,8120], "7D": [8190,8175,8160,8145,8130,8140,8125,8121,8120], "30D": [8350,8290,8270,8240,8210,8195,8175,8145,8120], "90D": [8220,8180,8160,8200,8170,8140,8130,8125,8120], "1A": [8850,8720,8640,8560,8480,8400,8310,8210,8120] } },
    { code: "BRL", name: "Real brasileño", buy: 1340, sell: 1380, change: 1.15, series: { Hoy: [1325,1330,1332,1338,1335,1338,1340,1338,1340], "7D": [1290,1305,1315,1320,1328,1332,1338,1340,1340], "30D": [1220,1245,1260,1285,1295,1310,1320,1335,1340], "90D": [1280,1295,1310,1320,1305,1325,1335,1338,1340], "1A": [1120,1150,1180,1210,1240,1270,1295,1320,1340] } },
    { code: "ARS", name: "Peso argentino", buy: 7.4, sell: 7.8, change: -2.3, series: { Hoy: [7.58,7.55,7.52,7.5,7.47,7.45,7.42,7.41,7.4], "7D": [7.9,7.82,7.75,7.68,7.62,7.55,7.48,7.43,7.4], "30D": [9.2,8.9,8.6,8.3,8.1,7.9,7.7,7.55,7.4], "90D": [8.2,8,7.9,7.85,7.8,7.75,7.65,7.55,7.4], "1A": [12.4,11.8,11.2,10.6,10,9.4,8.8,8.1,7.4] } }
  ];
  var PYG_VALUES = { PYG: 1, USD: 7480, EUR: 8120, BRL: 1340, ARS: 7.4 };

  function formatNumber(value, fourDecimals) {
    return value.toLocaleString("es-PY", {
      minimumFractionDigits: fourDecimals ? 0 : (value < 100 ? 2 : 0),
      maximumFractionDigits: fourDecimals ? (value < 100 ? 4 : 0) : (value < 100 ? 2 : 0)
    });
  }

  function makeSparkline(data, width, height, color, label, animate) {
    var minimum = Math.min.apply(null, data);
    var maximum = Math.max.apply(null, data);
    var range = maximum - minimum || 1;
    var points = data.map(function (value, index) {
      return { x: index / (data.length - 1) * width, y: height - (value - minimum) / range * (height - 4) - 2 };
    });
    var line = points.map(function (point, index) { return (index ? "L" : "M") + point.x + "," + point.y; }).join(" ");
    var area = "M" + points[0].x + "," + height + " " + points.map(function (point) { return "L" + point.x + "," + point.y; }).join(" ") + " L" + points[points.length - 1].x + "," + height + " Z";
    var id = "ge-spark-" + Math.random().toString(36).slice(2);
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "ge-sparkline"); svg.setAttribute("viewBox", "0 0 " + width + " " + height); svg.setAttribute("preserveAspectRatio", "none"); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", label);
    svg.innerHTML = '<defs><linearGradient id="' + id + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="' + color + '" stop-opacity=".3"/><stop offset="1" stop-color="' + color + '" stop-opacity="0"/></linearGradient></defs><path d="' + area + '" fill="url(#' + id + ')"/><path data-draw-line d="' + line + '" fill="none" stroke="' + color + '" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/><circle cx="' + points[points.length - 1].x + '" cy="' + points[points.length - 1].y + '" r="3" fill="' + color + '"/>';
    if (animate) {
      var path = svg.querySelector("[data-draw-line]");
      path.style.strokeDasharray = "800"; path.style.strokeDashoffset = "800";
      window.requestAnimationFrame(function () { path.style.transition = "stroke-dashoffset 1s ease-out"; path.style.strokeDashoffset = "0"; });
    }
    return svg;
  }

  function animateNumber(element, from, to, duration, formatter) {
    var started = performance.now();
    function frame(now) {
      var progress = Math.min((now - started) / duration, 1);
      var eased = 1 - Math.pow(1 - progress, 3);
      element.textContent = formatter(from + (to - from) * eased);
      if (progress < 1) window.requestAnimationFrame(frame);
    }
    window.requestAnimationFrame(frame);
  }

  function initMarketBoard(board) {
    var selectedCode = "USD", hoveredCode = null, flash = null, currentBuy = 0, currentSell = 0;
    var primary = board.querySelector("[data-market-primary]");
    var buyElement = board.querySelector("[data-market-buy]");
    var sellElement = board.querySelector("[data-market-sell]");
    var changeElement = board.querySelector("[data-market-change]");
    var chart = board.querySelector("[data-market-chart]");

    function rateFor(code) { return RATES.filter(function (rate) { return rate.code === code; })[0] || RATES[0]; }
    function render(animate) {
      var active = rateFor(hoveredCode || selectedCode || "USD");
      var activeFlash = flash && flash.code === active.code ? flash : null;
      var nextBuy = activeFlash ? activeFlash.buy : active.buy;
      var nextSell = activeFlash ? activeFlash.sell : active.sell;
      board.querySelector("[data-market-pair]").textContent = active.code + " / PYG";
      board.querySelector("[data-market-subtitle]").textContent = active.name + " / Guaraní paraguayo";
      board.querySelector("[data-market-chart-pair]").textContent = active.code + " / PYG";
      chart.setAttribute("aria-label", "Evolución " + active.code + " PYG durante 15 minutos");
      chart.replaceChildren.apply(chart, Array.from(makeSparkline(active.series.Hoy, 560, 82, "#3B5BFF", chart.getAttribute("aria-label"), animate).childNodes));
      [primary, buyElement, sellElement].forEach(function (element) { element.classList.remove("is-flashing-positive", "is-flashing-negative"); if (activeFlash) element.classList.add(activeFlash.direction > 0 ? "is-flashing-positive" : "is-flashing-negative"); });
      changeElement.className = active.change >= 0 ? "is-positive" : "is-negative";
      changeElement.textContent = (active.change >= 0 ? "+" : "-") + Math.abs(active.change).toFixed(2) + "%";
      if (animate) {
        animateNumber(primary, currentBuy, nextBuy, 800, formatNumber); animateNumber(buyElement, currentBuy, nextBuy, 800, formatNumber); animateNumber(sellElement, currentSell, nextSell, 800, formatNumber);
      } else { primary.textContent = formatNumber(nextBuy); buyElement.textContent = formatNumber(nextBuy); sellElement.textContent = formatNumber(nextSell); }
      currentBuy = nextBuy; currentSell = nextSell;
      board.querySelectorAll("[data-market-code]").forEach(function (button) {
        var rate = rateFor(button.dataset.marketCode); var quote = flash && flash.code === rate.code ? flash.buy : rate.buy;
        button.classList.toggle("is-selected", (hoveredCode || selectedCode) === rate.code);
        button.classList.remove("is-flashing-positive", "is-flashing-negative");
        if (flash && flash.code === rate.code) button.classList.add(flash.direction > 0 ? "is-flashing-positive" : "is-flashing-negative");
        button.querySelector("[data-market-quote]").textContent = formatNumber(quote);
      });
    }

    board.querySelectorAll("[data-market-stage]").forEach(function (stage, index) { window.setTimeout(function () { stage.classList.add("is-visible"); }, [260, 560, 800, 1000][index]); });
    board.querySelectorAll("[data-market-code]").forEach(function (button) {
      button.style.transitionDelay = Array.from(button.parentNode.children).indexOf(button) * 90 + "ms";
      button.addEventListener("mouseenter", function () { hoveredCode = button.dataset.marketCode; render(true); });
      button.addEventListener("mouseleave", function () { hoveredCode = null; render(true); });
      button.addEventListener("click", function () { selectedCode = selectedCode === button.dataset.marketCode ? null : button.dataset.marketCode; render(true); });
    });
    render(true);
    window.setInterval(function () {
      var rate = RATES[Math.floor(Math.random() * RATES.length)]; var direction = Math.random() > .45 ? 1 : -1; var delta = rate.code === "ARS" ? .02 : 1.4;
      flash = { code: rate.code, direction: direction, buy: rate.buy + direction * delta, sell: rate.sell + direction * delta }; render(true);
      window.setTimeout(function () { flash = null; render(true); }, 1500);
    }, 7000);
  }

  function initRates(landing) {
    var section = landing.querySelector("[data-rates-section]"); var currentPeriod = "90D"; var shown = false;
    function render(animate) {
      section.querySelector("[data-period-heading]").textContent = currentPeriod;
      section.querySelectorAll("[data-rate-code]").forEach(function (row) {
        var rate = RATES.filter(function (item) { return item.code === row.dataset.rateCode; })[0]; var target = row.querySelector("[data-rate-chart]"); var color = rate.change >= 0 ? "#22C55E" : "#F87171";
        target.replaceChildren(makeSparkline(rate.series[currentPeriod], 180, 32, color, "Evolución " + rate.code + " " + currentPeriod, animate));
        if (animate && !shown) { animateNumber(row.querySelector("[data-buy]"), 0, rate.buy, 700, function (value) { return formatNumber(value, true); }); animateNumber(row.querySelector("[data-sell]"), 0, rate.sell, 700, function (value) { return formatNumber(value, true); }); }
      });
      shown = true;
    }
    section.querySelectorAll("[data-period]").forEach(function (button) { button.addEventListener("click", function () { currentPeriod = button.dataset.period; section.querySelectorAll("[data-period]").forEach(function (item) { item.classList.toggle("active", item === button); }); render(true); }); });
    var observer = new IntersectionObserver(function (entries) { if (entries[0].isIntersecting) { render(true); observer.disconnect(); } }, { threshold: .15 }); observer.observe(section);
  }

  function initConverter(landing) {
    var root = landing.querySelector("[data-public-converter]"); var amount = root.querySelector("#ge-converter-amount"); var from = root.querySelector("[data-converter-from]"); var to = root.querySelector("[data-converter-to]"); var output = root.querySelector("[data-converter-output]"); var rateOutput = root.querySelector("[data-converter-rate]");
    function update() { amount.value = amount.value.replace(/[^0-9.]/g, ""); var rate = PYG_VALUES[from.value] / PYG_VALUES[to.value]; var result = (parseFloat(amount.value) || 0) * rate; output.textContent = formatNumber(result, true); rateOutput.textContent = "1 " + from.value + " = " + rate.toLocaleString("es-PY", { minimumFractionDigits: rate < .01 ? 6 : 0, maximumFractionDigits: rate < .01 ? 6 : 4 }) + " " + to.value; }
    amount.addEventListener("input", update); from.addEventListener("change", update); to.addEventListener("change", update);
    root.querySelector("[data-converter-swap]").addEventListener("click", function (event) { var button = event.currentTarget; var previous = from.value; from.value = to.value; to.value = previous; button.classList.add("is-swapping"); window.setTimeout(function () { button.classList.remove("is-swapping"); }, 320); update(); }); update();
  }

  function initLanding() {
    var landing = document.querySelector("[data-django-landing]"); if (!landing) return;
    landing.querySelectorAll(".reveal").forEach(function (element) { var observer = new IntersectionObserver(function (entries) { if (entries[0].isIntersecting) { element.classList.add("visible"); observer.disconnect(); } }, { threshold: .1 }); observer.observe(element); });
    landing.querySelectorAll('a[href^="#"]').forEach(function (link) { link.addEventListener("click", function (event) { var target = document.querySelector(link.getAttribute("href")); if (!target) return; event.preventDefault(); history.pushState(null, "", link.getAttribute("href")); target.scrollIntoView({ behavior: "smooth" }); }); });
    landing.querySelectorAll("[data-market-board]").forEach(initMarketBoard); initRates(landing); initConverter(landing);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initLanding, { once: true }); else initLanding();
}());
