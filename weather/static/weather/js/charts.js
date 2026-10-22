// FR-9 AC-3..6: draw the forecast charts from the server's json_script data.
// The server already converted every value to the user's unit, so a unit change
// reloads the page and the charts are redrawn from fresh data. Without
// JavaScript (or if Chart.js fails to load) the summary and table remain.

const CHART_DATA_ID = "forecast-chart-data";

// ---- Pure helpers (no DOM access) ----

function withUnit(value, unit) {
  return `${value}${unit === "%" || unit.startsWith("°") ? "" : " "}${unit}`;
}

function axis(title, extra = {}) {
  return { title: { display: true, text: title }, ...extra };
}

function baseOptions(animate) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: animate ? undefined : false,
    interaction: { mode: "index", intersect: false },
    plugins: { legend: { display: true } },
  };
}

function temperatureConfig(data, colors, animate) {
  const unit = data.temperature_unit;
  return {
    type: "line",
    data: {
      labels: data.labels,
      datasets: [{
        label: `Temperature (${unit})`,
        data: data.temperature,
        borderColor: colors.primary,
        backgroundColor: colors.primary,
        pointRadius: 3,
        tension: 0.3,
      }],
    },
    options: {
      ...baseOptions(animate),
      scales: {
        x: axis("Local time"),
        y: axis(`Temperature (${unit})`),
      },
      plugins: {
        legend: { display: true },
        tooltip: { callbacks: { label: (ctx) => `Temperature: ${withUnit(ctx.parsed.y, unit)}` } },
      },
    },
  };
}

function precipitationConfig(data, colors, animate) {
  const unit = data.precipitation_unit;
  return {
    type: "bar",
    data: {
      labels: data.labels,
      datasets: [
        {
          type: "bar",
          label: "Chance of precipitation (%)",
          data: data.pop,
          backgroundColor: colors.secondary,
          yAxisID: "y",
        },
        {
          type: "line",
          label: `Precipitation (${unit})`,
          data: data.precipitation,
          borderColor: colors.primary,
          backgroundColor: colors.primary,
          pointRadius: 3,
          yAxisID: "y1",
        },
      ],
    },
    options: {
      ...baseOptions(animate),
      scales: {
        x: axis("Local time"),
        y: axis("Chance of precipitation (%)", { min: 0, max: 100 }),
        y1: axis(`Precipitation (${unit})`, { min: 0, position: "right", grid: { drawOnChartArea: false } }),
      },
      plugins: {
        legend: { display: true },
        tooltip: {
          callbacks: {
            label: (ctx) => (ctx.datasetIndex === 0
              ? `Chance of precipitation: ${ctx.parsed.y}%`
              : `Precipitation: ${withUnit(ctx.parsed.y, unit)}`),
          },
        },
      },
    },
  };
}

function describePoint(data, index) {
  return `${data.labels[index]}: ${withUnit(data.temperature[index], data.temperature_unit)}, `
    + `${data.pop[index]}% chance of precipitation, `
    + `${withUnit(data.precipitation[index], data.precipitation_unit)} of precipitation.`;
}

function nextIndex(key, current, length) {
  switch (key) {
    case "ArrowRight": return Math.min(current + 1, length - 1);
    case "ArrowLeft": return Math.max(current - 1, 0);
    case "Home": return 0;
    case "End": return length - 1;
    default: return null;
  }
}

// ---- DOM wiring ----

function readColors() {
  const styles = getComputedStyle(document.documentElement);
  return {
    primary: styles.getPropertyValue("--color-link").trim() || "#0b57d0",
    secondary: styles.getPropertyValue("--color-chart-2").trim() || "#1a7f64",
    text: styles.getPropertyValue("--color-text").trim() || "#1a1d23",
    grid: styles.getPropertyValue("--color-border").trim() || "#d0d5dd",
  };
}

// FR-9 AC-5: show the tooltip for a point from the keyboard, and announce it.
function enableKeyboardTooltips(canvas, chart, data) {
  let active = -1;
  canvas.addEventListener("keydown", (event) => {
    const index = nextIndex(event.key, active < 0 ? -1 : active, data.labels.length);
    if (index === null) {
      return;
    }
    event.preventDefault();
    active = index < 0 ? 0 : index;
    const elements = chart.data.datasets.map((_, datasetIndex) => ({ datasetIndex, index: active }));
    chart.setActiveElements(elements);
    chart.tooltip.setActiveElements(elements, { x: 0, y: 0 });
    chart.update();
    const liveRegion = document.getElementById("live-region");
    if (liveRegion) {
      liveRegion.textContent = describePoint(data, active);
    }
  });
  canvas.addEventListener("blur", () => {
    chart.setActiveElements([]);
    chart.tooltip.setActiveElements([], { x: 0, y: 0 });
    chart.update();
  });
}

function drawCharts() {
  const source = document.getElementById(CHART_DATA_ID);
  const fallback = document.querySelector("[data-chart-fallback]");
  if (!source) {
    return;
  }
  if (typeof Chart === "undefined") {
    if (fallback) {
      fallback.textContent = "The charts couldn't be loaded. The same data is in the table below.";
    }
    return;
  }
  const data = JSON.parse(source.textContent);
  const colors = readColors();
  const animate = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  Chart.defaults.color = colors.text;
  Chart.defaults.borderColor = colors.grid;

  for (const [id, build] of [
    ["temperature-chart", temperatureConfig],
    ["precipitation-chart", precipitationConfig],
  ]) {
    const canvas = document.getElementById(id);
    if (canvas) {
      // Reveal the figure before drawing so Chart.js measures the real container size.
      canvas.closest("figure").hidden = false;
      const chart = new Chart(canvas, build(data, colors, animate));
      enableKeyboardTooltips(canvas, chart, data);
    }
  }
  if (fallback) {
    fallback.hidden = true;
  }
}

drawCharts();
