// AthleteHub — comportamiento del cliente (sin scripts en línea, compatible con la CSP).
(function () {
  "use strict";

  // Anchos de barras de progreso desde data-width
  document.querySelectorAll("[data-width]").forEach(function (el) {
    var v = Math.max(0, Math.min(100, parseFloat(el.dataset.width) || 0));
    el.style.width = v + "%";
  });

  // Confirmación antes de acciones destructivas
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.dataset.confirm)) e.preventDefault();
    });
  });

  // Medidor de contraseña en registro / cambio de contraseña
  var pass = document.querySelector("[data-password-meter]");
  if (pass) {
    var meter = document.getElementById("pass-meter");
    var rules = document.querySelectorAll("#pass-rules li");
    var checks = {
      len: function (v) { return v.length >= 8; },
      upper: function (v) { return /[A-Z]/.test(v); },
      lower: function (v) { return /[a-z]/.test(v); },
      digit: function (v) { return /\d/.test(v); },
      symbol: function (v) { return /[^A-Za-z0-9]/.test(v); }
    };
    pass.addEventListener("input", function () {
      var ok = 0;
      rules.forEach(function (li) {
        var pasa = checks[li.dataset.rule](pass.value);
        li.classList.toggle("ok", pasa);
        if (pasa) ok++;
      });
      meter.style.width = (ok / rules.length) * 100 + "%";
      meter.classList.toggle("ok", ok === rules.length);
    });
  }

  // Mostrar el selector correcto según el alcance del aviso
  var alcance = document.getElementById("alcance");
  if (alcance) {
    var sync = function () {
      document.querySelectorAll("[data-alcance]").forEach(function (el) {
        el.classList.toggle("hidden", el.dataset.alcance !== alcance.value);
      });
    };
    alcance.addEventListener("change", sync);
    sync();
  }

  // Marcar a todos con un estado en la lista de asistencia
  document.querySelectorAll("[data-marcar-todos]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var estado = btn.dataset.marcarTodos;
      document.querySelectorAll('input[type=radio][value="' + estado + '"]').forEach(function (r) {
        r.checked = true;
      });
    });
  });

  // Mostrar u ocultar el método de pago en el formulario de pago nuevo
  var pagado = document.getElementById("pagado");
  if (pagado) {
    var metodo = document.getElementById("metodo-field");
    var syncPago = function () { metodo.classList.toggle("hidden", pagado.value !== "1"); };
    pagado.addEventListener("change", syncPago);
    syncPago();
  }

  // Gráficas (Chart.js) a partir de data-chart
  if (window.Chart) {
    Chart.defaults.color = "#8B95A4";
    Chart.defaults.borderColor = "#ECEFF2";
    Chart.defaults.font.family = "'Plus Jakarta Sans', system-ui, sans-serif";
    document.querySelectorAll("canvas[data-chart]").forEach(function (canvas) {
      var datos = JSON.parse(canvas.dataset.chart);
      var tipo = canvas.dataset.type || "bar";
      new Chart(canvas, {
        type: tipo,
        data: {
          labels: datos.labels,
          datasets: [{
            data: datos.valores,
            backgroundColor: tipo === "line" ? "rgba(11,31,58,.08)" : "#0B1F3A",
            borderColor: "#0B1F3A",
            borderWidth: tipo === "line" ? 2 : 0,
            borderRadius: 8,
            fill: tipo === "line",
            tension: 0.3,
            pointBackgroundColor: "#0B1F3A",
            maxBarThickness: 46
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: function (c) { return c.parsed.y + "% de asistencia"; } } }
          },
          scales: {
            y: { beginAtZero: true, max: 100, ticks: { callback: function (v) { return v + "%"; } } },
            x: { grid: { display: false } }
          }
        }
      });
    });
  }
})();
