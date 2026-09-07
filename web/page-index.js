/* Home page: track record summary + all upcoming 1X2 predictions. */

(function () {
  "use strict";

  const UI = window.PrescoreUI;
  const API = window.PrescoreAPI;
  const cfg = window.PRESCORE_CONFIG || {};

  function pickLabel(row) {
    if (row.pick === "H") return UI.escapeHtml(row.home_team);
    if (row.pick === "A") return UI.escapeHtml(row.away_team);
    return "Draw";
  }

  function fixtureCard(row, graded) {
    const badge = graded
      ? UI.hitBadge(row.is_hit)
      : "";
    const score = graded
      ? `<span class="score">${row.home_goals}–${row.away_goals}</span> `
      : "";
    return (
      '<article class="fixture">' +
      '<div class="fixture-head">' +
      `<span class="teams">${UI.escapeHtml(row.home_team)} ${score}v ${UI.escapeHtml(row.away_team)}</span>` +
      badge +
      `<span class="badge badge-pick">pick: ${pickLabel(row)}</span>` +
      `<span class="kickoff">${UI.formatKickoff(row.kickoff_utc)}</span>` +
      "</div>" +
      UI.probabilityBar(row.home_team, row.away_team, row) +
      "</article>"
    );
  }

  function renderUpcoming(rows) {
    document.getElementById("upcoming-count").textContent = rows.length
      ? rows.length + (rows.length === 1 ? " fixture" : " fixtures")
      : "";
    const el = document.getElementById("upcoming-body");
    if (!rows.length) {
      el.innerHTML = '<p class="empty-state">No upcoming fixtures published right now.</p>';
      return;
    }
    el.innerHTML = '<div class="fixture-list">' + rows.map((r) => fixtureCard(r, false)).join("") + "</div>";
  }

  function confidenceTable(buckets) {
    if (!buckets.length) return "";
    return (
      "<h3>By confidence</h3>" +
      '<div class="table-scroll"><table><thead><tr>' +
      '<th>Confidence in the pick</th><th class="num">Predictions</th>' +
      '<th class="num">Hits</th><th class="num">Accuracy</th>' +
      "</tr></thead><tbody>" +
      buckets
        .map(
          (b) =>
            `<tr><td>${b.range}</td><td class="num">${b.n}</td>` +
            `<td class="num">${b.hits}</td><td class="num">${UI.pct1(b.accuracy)}</td></tr>`
        )
        .join("") +
      "</tbody></table></div>"
    );
  }

  function versionComparisonTable(rows, current) {
    if (rows.length < 2) return "";
    const body = rows
      .map((r) => {
        const isCurrent = r.model_version === current;
        return (
          `<tr class="${isCurrent ? "is-current-row" : ""}">` +
          `<td><span class="version-pill">${UI.escapeHtml(r.model_version)}` +
          (isCurrent ? '<span class="version-current-tag">current</span>' : "") +
          "</span></td>" +
          `<td class="num">${r.graded}</td>` +
          `<td class="num">${UI.pct1(r.accuracy)}</td>` +
          `<td class="num">${Number(r.log_loss).toFixed(3)}</td>` +
          `<td class="num">${r.rps == null ? "—" : Number(r.rps).toFixed(3)}</td>` +
          "</tr>"
        );
      })
      .join("");
    return (
      "<h3>Compare model versions</h3>" +
      '<div class="table-scroll"><table><thead><tr>' +
      '<th>Version</th><th class="num">Graded</th><th class="num">Accuracy</th>' +
      '<th class="num">Log loss</th><th class="num">RPS</th>' +
      "</tr></thead><tbody>" + body + "</tbody></table></div>"
    );
  }

  async function renderRecord() {
    const el = document.getElementById("record-body");
    const league = cfg.league || "EPL";
    const current = cfg.modelVersion;

    const [{ rows: headline }, { rows: allVersions }, { rows: gradedRows }] = await Promise.all([
      API.query("v_accuracy", { league: `eq.${league}`, model_version: `eq.${current}` }),
      API.query("v_accuracy", { league: `eq.${league}` }),
      API.query("v_track_record", {
        league: `eq.${league}`,
        model_version: `eq.${current}`,
        is_hit: "not.is.null",
        select: "confidence,is_hit",
      }),
    ]);

    const overall = headline[0];
    if (!overall || !overall.graded) {
      el.innerHTML =
        '<p class="empty-state">No predictions have been graded yet, so there is no ' +
        "published accuracy figure. There will be no retroactive edits when there is.</p>";
      return;
    }

    const stats = [
      { label: "Accuracy", value: UI.pct1(overall.accuracy), highlight: true },
      { label: "Graded", value: overall.graded },
      { label: "Hits", value: overall.hits },
      { label: "Misses", value: overall.misses },
      { label: "Log loss", value: Number(overall.log_loss).toFixed(3) },
      { label: "RPS", value: overall.rps == null ? "—" : Number(overall.rps).toFixed(3) },
    ];

    const buckets = UI.confidenceBuckets(gradedRows);

    el.innerHTML =
      '<div class="stat-row">' +
      stats
        .map(
          (s) =>
            `<div><div class="stat-value${s.highlight ? " stat-highlight" : ""}">${UI.escapeHtml(s.value)}</div>` +
            `<div class="stat-label">${UI.escapeHtml(s.label)}</div></div>`
        )
        .join("") +
      "</div>" +
      confidenceTable(buckets) +
      versionComparisonTable(allVersions, current);
  }

  async function main() {
    UI.mountShell();
    document.getElementById("generated-at").textContent = "Live data, loaded " + UI.formatKickoff(new Date().toISOString()) + ".";

    try {
      await renderRecord();
    } catch (err) {
      UI.showError("record-body", err.message);
    }

    try {
      const league = cfg.league || "EPL";
      const { rows } = await API.query("v_track_record", {
        league: `eq.${league}`,
        model_version: `eq.${cfg.modelVersion}`,
        is_hit: "is.null",
        order: "kickoff_utc.asc",
      });
      renderUpcoming(rows);
    } catch (err) {
      UI.showError("upcoming-body", err.message);
    }
  }

  main();
})();
