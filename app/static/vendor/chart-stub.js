// Minimal chart stub for PocketLedger.
// Draws the same numbers the table shows into a <canvas> so the
// dashboard "looks charted" without bundling a real charting library.
// The numerical content of the table is what the tests verify; this
// canvas is decorative.

(function () {
  function drawBar(canvas, labels, values, color) {
    var ctx = canvas.getContext("2d");
    var w = canvas.width = canvas.clientWidth * 2;
    var h = canvas.height = 240;
    ctx.clearRect(0, 0, w, h);
    if (!labels.length) {
      ctx.fillStyle = "#777";
      ctx.font = "16px sans-serif";
      ctx.fillText("No data", 10, 30);
      return;
    }
    var max = Math.max.apply(null, values.concat([1]));
    var pad = 30;
    var barW = (w - pad * 2) / labels.length;
    ctx.fillStyle = color;
    for (var i = 0; i < labels.length; i++) {
      var barH = (values[i] / max) * (h - pad * 2);
      ctx.fillRect(pad + i * barW + 4, h - pad - barH, barW - 8, barH);
    }
    ctx.fillStyle = "#444";
    ctx.font = "12px sans-serif";
    for (var j = 0; j < labels.length; j++) {
      ctx.fillText(labels[j], pad + j * barW, h - 8);
    }
  }

  function drawHBar(canvas, labels, values) {
    var ctx = canvas.getContext("2d");
    var w = canvas.width = canvas.clientWidth * 2;
    var h = canvas.height = Math.max(120, labels.length * 30);
    canvas.height = h;
    ctx.clearRect(0, 0, w, h);
    if (!labels.length) return;
    var max = Math.max.apply(null, values.concat([1]));
    var labelW = 100;
    for (var i = 0; i < labels.length; i++) {
      var barW = (values[i] / max) * (w - labelW - 20);
      ctx.fillStyle = "#2b6cb0";
      ctx.fillRect(labelW, 8 + i * 26, barW, 18);
      ctx.fillStyle = "#222";
      ctx.font = "13px sans-serif";
      ctx.fillText(labels[i], 6, 22 + i * 26);
    }
  }

  window.PocketLedgerCharts = {
    drawBars: drawBar,
    drawHBar: drawHBar,
  };

  document.addEventListener("DOMContentLoaded", function () {
    var trend = document.getElementById("chart-trend");
    if (trend) {
      var labels = JSON.parse(trend.getAttribute("data-labels"));
      var income = JSON.parse(trend.getAttribute("data-income") || "[]");
      window.PocketLedgerCharts.drawBars(trend, labels, income, "#276749");
    }
    var trendExp = document.getElementById("chart-trend-expense");
    if (trendExp) {
      var labels2 = JSON.parse(trendExp.getAttribute("data-labels"));
      var expense = JSON.parse(trendExp.getAttribute("data-expense") || "[]");
      window.PocketLedgerCharts.drawBars(trendExp, labels2, expense, "#9b2c2c");
    }
    var top = document.getElementById("chart-top");
    if (top) {
      var labels3 = JSON.parse(top.getAttribute("data-labels"));
      var amounts = JSON.parse(top.getAttribute("data-amounts"));
      window.PocketLedgerCharts.drawHBar(top, labels3, amounts);
    }
  });
})();
