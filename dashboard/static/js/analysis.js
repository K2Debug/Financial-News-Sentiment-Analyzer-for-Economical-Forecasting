/** EF-02 analysis charts — conclusion first */
window.EF02Analysis = (function () {
const COLOR = {
        bg: "#0B1220",
        card: "#0F1B33",
        text: "#E6F0FF",
        muted: "#9FB3D1",
        primary: "#00B3FF",
        positive: "#17E88A",
        negative: "#FF4D4D",
        neutral: "rgba(0, 179, 255, 0.65)",
      };

      let charts = {};
      let cachedCorrelation = null;

      function parseCSV(text) {
        const lines = text.trim().split(/\r?\n/);
        if (!lines.length) return { headers: [], rows: [] };
        const headers = lines[0].split(",");
        const rows = lines.slice(1).map((line) => {
          const parts = line.split(",");
          const obj = {};
          for (let i = 0; i < headers.length; i++) obj[headers[i]] = parts[i];
          return obj;
        });
        return { headers, rows };
      }

      function toNumber(v) {
        const n = Number(String(v).trim());
        return Number.isFinite(n) ? n : NaN;
      }

      function mean(arr) {
        const valid = arr.filter((x) => Number.isFinite(x));
        if (!valid.length) return NaN;
        return valid.reduce((a, b) => a + b, 0) / valid.length;
      }

      function pearsonR(a, b) {
        // Pearson correlation coefficient for paired numeric arrays.
        const n = Math.min(a.length, b.length);
        let count = 0;
        let sumX = 0;
        let sumY = 0;
        let sumXX = 0;
        let sumYY = 0;
        let sumXY = 0;

        for (let i = 0; i < n; i++) {
          const x = a[i];
          const y = b[i];
          if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
          count++;
          sumX += x;
          sumY += y;
          sumXX += x * x;
          sumYY += y * y;
          sumXY += x * y;
        }

        if (count < 2) return NaN;
        const numerator = count * sumXY - sumX * sumY;
        const denomPart1 = count * sumXX - sumX * sumX;
        const denomPart2 = count * sumYY - sumY * sumY;
        const denom = Math.sqrt(denomPart1 * denomPart2);
        if (!Number.isFinite(denom) || denom === 0) return NaN;
        return numerator / denom;
      }

      function renderCorrelationHeatmap(sentimentVars, economicVars, matrix) {
        const wrap = document.getElementById("corrHeatmapWrap");
        const clamp01 = (x) => Math.max(0, Math.min(1, x));

        const makeCell = (r) => {
          if (!Number.isFinite(r)) {
            return `<td class="heatmap-cell heatmap-na">—</td>`;
          }
          const magnitude = clamp01(Math.abs(r));
          const alpha = 0.15 + magnitude * 0.75; // stays bright but not overwhelming
          const isPositive = r >= 0;
          const bg = isPositive
            ? `rgba(0, 179, 255, ${alpha.toFixed(3)})`
            : `rgba(255, 77, 77, ${alpha.toFixed(3)})`;

          return `<td class="heatmap-cell" style="background:${bg}">${r.toFixed(2)}</td>`;
        };

        const headerRow = `
          <thead>
            <tr>
              <th class="heatmap-corner"></th>
              ${economicVars.map((ev) => `<th class="heatmap-col">${ev.name}</th>`).join("")}
            </tr>
          </thead>
        `;

        const bodyRows = sentimentVars
          .map((sv, i) => {
            return `
              <tr>
                <th class="heatmap-row">${sv.name}</th>
                ${economicVars.map((ev, j) => makeCell(matrix[i][j])).join("")}
              </tr>
            `;
          })
          .join("");

        wrap.innerHTML = `
          <table class="heatmap-table">
            ${headerRow}
            <tbody>${bodyRows}</tbody>
          </table>
        `;
      }

      function destroyChart(key) {
        if (charts[key] && typeof charts[key].destroy === "function") charts[key].destroy();
        charts[key] = null;
      }

      function setNarrativeTop(d) {
        const totalMonths = d.labels.length;
        const domN = d.dominantNeutralCount;
        const domP = d.dominantPositiveCount;
        const netPosMonths = d.netPositiveCount;
        const avgNeg = d.avgNegative;

        document.getElementById("monthsCount").textContent = `${totalMonths}`;
        document.getElementById("dominantSentiment").textContent = `Neutral ${domN}/${totalMonths}, Positive ${domP}/${totalMonths}`;
        document.getElementById("avgNegative").textContent = `${avgNeg.toFixed(1)}%`;
        document.getElementById("netSign").textContent = `${netPosMonths}/${totalMonths} net-positive months`;

        document.getElementById("narrativeTop").innerHTML =
          `<strong>Notebook alignment:</strong> Net sentiment stays positive across the period, while Neutral and Positive dominate about equally; Negative stays comparatively low.`;
      }

      function computeCorrelationTableForModel(corrJson, modelKey) {
        const model = corrJson[modelKey];
        if (!model) return [];
        return [
          ["Negative % vs USD/TZS Rate", "Negative % vs USD/TZS_Rate"],
          ["Net Sentiment vs USD/TZS Rate", "Net_Sentiment vs USD/TZS_Rate"],
          ["Positive % vs USD/TZS Rate", "Positive % vs USD/TZS_Rate"],
          ["Net Sentiment vs Inflation %", "Net_Sentiment vs Inflation %"],
        ].map(([display, key]) => {
          const row = model[key] || {};
          const r = row.r ?? NaN;
          const p = row.p ?? NaN;
          const significant = !!row.significant;
          return { display, r, p, significant };
        });
      }

      function renderCorrelationTable(rows) {
        const tbody = document.getElementById("corrTableBody");
        tbody.innerHTML = "";
        for (const r of rows) {
          const tr = document.createElement("tr");
          const rSignColor = Number.isFinite(r.r)
            ? r.r >= 0
              ? "var(--positive)"
              : "var(--negative)"
            : "var(--muted)";

          tr.innerHTML = `
            <td>${r.display}</td>
            <td class="r-cell" style="color: ${rSignColor}">${Number.isFinite(r.r) ? r.r.toFixed(3) : "—"}</td>
            <td>${Number.isFinite(r.p) ? r.p.toFixed(4) : "—"}</td>
            <td class="${r.significant ? "sig-yes" : "sig-no"}">${r.significant ? "Yes" : "No"}</td>
          `;
          tbody.appendChild(tr);
        }
      }

      function setCorrelationNarrative() {
        const pLine = "Significance threshold: p ≤ 0.05.";
        document.getElementById("corrNarrative").innerHTML =
          `<strong>OpenAI run:</strong> correlations computed from this job's monthly data. <span class="muted">${pLine}</span>`;
      }

      async function loadAndRender(csvUrl, correlationJSONUrl) {
        const corrJson = await fetch(correlationJSONUrl).then((r) => r.json());
        cachedCorrelation = corrJson;

        const text = await fetch(csvUrl).then((r) => r.text());
        const parsed = parseCSV(text);
        const headers = parsed.headers;
        const rows = parsed.rows;

        // Columns from Visualization_Data.csv
        const get = (row, name) => row[name];

        const labels = [];
        const negative = [];
        const neutral = [];
        const positive = [];
        const inflation = [];
        const fx = [];
        const rateChange = [];
        for (const row of rows) {
          labels.push(get(row, "YearMonth"));
          negative.push(toNumber(get(row, "Negative %")));
          neutral.push(toNumber(get(row, "Neutral %")));
          positive.push(toNumber(get(row, "Positive %")));
          inflation.push(toNumber(get(row, "Inflation %")));
          fx.push(toNumber(get(row, "USD/TZS_Rate")));
          rateChange.push(toNumber(get(row, "Rate_Change_%")));
        }

        const netSentiment = positive.map((p, i) => p - negative[i]);

        // Dominant sentiment counts (by maximum share each month)
        let dominantPositiveCount = 0;
        let dominantNeutralCount = 0;
        let netPositiveCount = 0;
        for (let i = 0; i < labels.length; i++) {
          if (netSentiment[i] > 0) netPositiveCount++;
          const maxVal = Math.max(neutral[i], positive[i], negative[i]);
          if (positive[i] === maxVal) dominantPositiveCount++;
          else if (neutral[i] === maxVal) dominantNeutralCount++;
        }

        const avgNegative = mean(negative);
        setNarrativeTop({
          labels,
          dominantNeutralCount,
          dominantPositiveCount,
          netPositiveCount,
          avgNegative,
        });

        // Correlation outcomes
        const corrRows = computeCorrelationTableForModel(corrJson, "openai");
        renderCorrelationTable(corrRows);
        setCorrelationNarrative();

        // Render charts
        destroyChart("sentimentChart");
        destroyChart("netSentimentChart");
        destroyChart("inflationChart");
        destroyChart("fxChart");
        destroyChart("netVsRateChangeChart");
        destroyChart("sentimentInflationScatter");
        destroyChart("sentimentFxScatter");

        const optionsCommon = {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { labels: { color: COLOR.text } },
            tooltip: {
              callbacks: {
                label: (ctx) => `${ctx.dataset.label}: ${ctx.raw}`,
              },
            },
          },
          scales: {
            x: { ticks: { color: COLOR.muted }, grid: { color: "rgba(159, 179, 209, 0.12)" } },
            y: { ticks: { color: COLOR.muted }, grid: { color: "rgba(159, 179, 209, 0.12)" } },
          },
        };

        charts.sentimentChart = new Chart(document.getElementById("sentimentChart"), {
          type: "bar",
          data: {
            labels,
            datasets: [
              {
                label: "Neutral",
                data: neutral,
                backgroundColor: COLOR.neutral,
                stack: "sentiment",
                borderWidth: 0,
              },
              {
                label: "Positive",
                data: positive,
                backgroundColor: "rgba(23, 232, 138, 0.85)",
                stack: "sentiment",
                borderWidth: 0,
              },
              {
                label: "Negative",
                data: negative,
                backgroundColor: "rgba(255, 77, 77, 0.85)",
                stack: "sentiment",
                borderWidth: 0,
              },
            ],
          },
          options: {
            ...optionsCommon,
            scales: {
              ...optionsCommon.scales,
              y: {
                ...optionsCommon.scales.y,
                stacked: true,
                min: 0,
                max: 100,
                ticks: {
                  color: COLOR.muted,
                  callback: (v) => `${v}%`,
                },
              },
            },
          },
        });

        charts.netSentimentChart = new Chart(document.getElementById("netSentimentChart"), {
          type: "bar",
          data: {
            labels,
            datasets: [
              {
                label: "Net Sentiment",
                data: netSentiment.map((v) => Number(v.toFixed(2))),
                backgroundColor: netSentiment.map((v) =>
                  v >= 0 ? "rgba(23, 232, 138, 0.85)" : "rgba(255, 77, 77, 0.85)"
                ),
                borderWidth: 0,
              },
            ],
          },
          options: {
            ...optionsCommon,
            scales: {
              ...optionsCommon.scales,
              y: {
                ...optionsCommon.scales.y,
                min: Math.min(...netSentiment) - 3,
                max: Math.max(...netSentiment) + 3,
                ticks: {
                  color: COLOR.muted,
                  callback: (v) => `${v}%`,
                },
              },
            },
          },
        });

        charts.inflationChart = new Chart(document.getElementById("inflationChart"), {
          type: "line",
          data: {
            labels,
            datasets: [
              {
                label: "Inflation %",
                data: inflation.map((v) => Number(v.toFixed(3))),
                borderColor: "rgba(0, 179, 255, 0.95)",
                backgroundColor: "rgba(0, 179, 255, 0.15)",
                fill: true,
                tension: 0.32,
                pointRadius: 3,
              },
            ],
          },
          options: {
            ...optionsCommon,
            scales: {
              x: { ticks: { color: COLOR.muted }, grid: { color: "rgba(159, 179, 209, 0.12)" } },
              y: { ticks: { color: COLOR.muted }, grid: { color: "rgba(159, 179, 209, 0.12)" } },
            },
          },
        });

        charts.fxChart = new Chart(document.getElementById("fxChart"), {
          type: "line",
          data: {
            labels,
            datasets: [
              {
                label: "USD/TZS Rate",
                data: fx.map((v) => Number(v.toFixed(2))),
                borderColor: "rgba(0, 179, 255, 0.95)",
                backgroundColor: "rgba(0, 179, 255, 0.15)",
                fill: true,
                tension: 0.32,
                pointRadius: 3,
              },
            ],
          },
          options: {
            ...optionsCommon,
            scales: {
              x: { ticks: { color: COLOR.muted }, grid: { color: "rgba(159, 179, 209, 0.12)" } },
              y: { ticks: { color: COLOR.muted }, grid: { color: "rgba(159, 179, 209, 0.12)" } },
            },
          },
        });

        charts.netVsRateChangeChart = new Chart(document.getElementById("netVsRateChangeChart"), {
          type: "bar",
          data: {
            labels,
            datasets: [
              {
                type: "bar",
                label: "Net Sentiment",
                data: netSentiment.map((v) => Number(v.toFixed(2))),
                backgroundColor: netSentiment.map((v) =>
                  v >= 0 ? "rgba(23, 232, 138, 0.85)" : "rgba(255, 77, 77, 0.85)"
                ),
                borderWidth: 0,
                yAxisID: "y",
              },
              {
                type: "line",
                label: "Rate Change %",
                data: rateChange.map((v) => Number(v.toFixed(3))),
                borderColor: "rgba(0, 179, 255, 0.95)",
                backgroundColor: "rgba(0, 179, 255, 0.15)",
                fill: false,
                borderDash: [6, 4],
                tension: 0.2,
                pointRadius: 3,
                yAxisID: "y1",
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { labels: { color: COLOR.text } },
            },
            scales: {
              x: {
                ticks: { color: COLOR.muted },
                grid: { color: "rgba(159, 179, 209, 0.12)" },
              },
              y: {
                position: "left",
                ticks: { color: COLOR.muted, callback: (v) => `${v}%` },
                grid: { color: "rgba(159, 179, 209, 0.12)" },
              },
              y1: {
                position: "right",
                ticks: { color: COLOR.muted, callback: (v) => `${v}%` },
                grid: { drawOnChartArea: false },
              },
            },
          },
        });

        const inflationPointsPos = labels.map((_, i) => ({ x: inflation[i], y: positive[i] }));
        const inflationPointsNeg = labels.map((_, i) => ({ x: inflation[i], y: negative[i] }));

        charts.sentimentInflationScatter = new Chart(document.getElementById("sentimentInflationScatter"), {
          type: "scatter",
          data: {
            datasets: [
              {
                label: "Positive %",
                data: inflationPointsPos,
                backgroundColor: "rgba(23, 232, 138, 0.85)",
                borderColor: "rgba(23, 232, 138, 0.85)",
                pointRadius: 4,
              },
              {
                label: "Negative %",
                data: inflationPointsNeg,
                backgroundColor: "rgba(255, 77, 77, 0.85)",
                borderColor: "rgba(255, 77, 77, 0.85)",
                pointRadius: 4,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { labels: { color: COLOR.text } },
              tooltip: {
                callbacks: {
                  label: (ctx) => {
                    const y = ctx.parsed.y;
                    const x = ctx.parsed.x;
                    return `${ctx.dataset.label}: ${y}% at Inflation=${x}`;
                  },
                },
              },
            },
            scales: {
              x: {
                title: { display: true, text: "Inflation %", color: COLOR.muted },
                ticks: { color: COLOR.muted },
                grid: { color: "rgba(159, 179, 209, 0.12)" },
              },
              y: {
                title: { display: true, text: "Sentiment %", color: COLOR.muted },
                ticks: { color: COLOR.muted },
                grid: { color: "rgba(159, 179, 209, 0.12)" },
              },
            },
          },
        });

        const fxPointsPos = labels.map((_, i) => ({ x: fx[i], y: positive[i] }));
        const fxPointsNeg = labels.map((_, i) => ({ x: fx[i], y: negative[i] }));

        charts.sentimentFxScatter = new Chart(document.getElementById("sentimentFxScatter"), {
          type: "scatter",
          data: {
            datasets: [
              {
                label: "Positive %",
                data: fxPointsPos,
                backgroundColor: "rgba(23, 232, 138, 0.85)",
                borderColor: "rgba(23, 232, 138, 0.85)",
                pointRadius: 4,
              },
              {
                label: "Negative %",
                data: fxPointsNeg,
                backgroundColor: "rgba(255, 77, 77, 0.85)",
                borderColor: "rgba(255, 77, 77, 0.85)",
                pointRadius: 4,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { labels: { color: COLOR.text } },
              tooltip: {
                callbacks: {
                  label: (ctx) => {
                    const y = ctx.parsed.y;
                    const x = ctx.parsed.x;
                    return `${ctx.dataset.label}: ${y}% at USD/TZS=${x}`;
                  },
                },
              },
            },
            scales: {
              x: {
                title: { display: true, text: "USD/TZS Rate", color: COLOR.muted },
                ticks: { color: COLOR.muted },
                grid: { color: "rgba(159, 179, 209, 0.12)" },
              },
              y: {
                title: { display: true, text: "Sentiment %", color: COLOR.muted },
                ticks: { color: COLOR.muted },
                grid: { color: "rgba(159, 179, 209, 0.12)" },
              },
            },
          },
        });

        // Correlation matrix heatmap (Pearson r) computed from the loaded dataset
        const sentimentVars = [
          { name: "Positive %", values: positive },
          { name: "Negative %", values: negative },
          { name: "Neutral %", values: neutral },
          { name: "Net_Sentiment", values: netSentiment },
        ];

        const economicVars = [
          { name: "Inflation %", values: inflation },
          { name: "USD/TZS_Rate", values: fx },
          { name: "Rate_Change_%", values: rateChange },
        ];

        const matrix = sentimentVars.map((sv) => economicVars.map((ev) => pearsonR(sv.values, ev.values)));
        renderCorrelationHeatmap(sentimentVars, economicVars, matrix);
      }

      
  async function render(jobId) {
    const analysisRes = await fetch(`/api/jobs/${jobId}/analysis`);
    if (!analysisRes.ok) throw new Error("Analysis not ready");
    const { summary } = await analysisRes.json();
    renderConclusion(summary);
    const csvUrl = `/api/jobs/${jobId}/visualization-data`;
    const correlationJSONUrl = `/api/jobs/${jobId}/correlations`;
    await loadAndRender(csvUrl, correlationJSONUrl);
  }

  function renderConclusion(summary) {
    const el = document.getElementById("conclusionPanel");
    if (!el || !summary) return;
    el.className = "conclusion-panel " + (summary.any_significant ? "significant" : "not-significant");
    const sig = (summary.significant_pairs || [])
      .map((s) => `<li><strong>${s.pair}</strong>: r=${Number(s.r).toFixed(3)}, p=${Number(s.p).toFixed(4)}</li>`)
      .join("") || "<li>No pairs reached p ≤ 0.05</li>";
    el.innerHTML = `<h3 style="margin:0 0 8px">Research conclusion</h3><p>${summary.verdict}</p><ul style="margin:8px 0 0;padding-left:18px;font-size:13px;color:var(--muted)">${sig}</ul>`;
    document.getElementById("analysisEmpty").style.display = "none";
    document.getElementById("analysisContent").style.display = "block";
  }

  return { render };
})();
