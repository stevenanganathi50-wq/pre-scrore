/* Markets page: BTTS and Over/Under 2.5, grouped by fixture so both markets
 * show together rather than behind separate tabs.
 *
 * v_market_track_record is one row per (match, market, outcome) -- 4 rows
 * per fixture (2 markets x 2 outcomes). Pagination therefore works in units
 * of MATCHES_PER_PAGE * 4 rows, with kickoff_utc + match_id as the sort key
 * so that if two fixtures share a kickoff time, each match's 4 rows still
 * stay contiguous rather than interleaving across a page boundary.
 */

(function () {
  "use strict";

  const UI = window.PrescoreUI;
  const API = window.PrescoreAPI;
  const cfg = window.PRESCORE_CONFIG || {};
  const MATCHES_PER_PAGE = 20;
  const ROWS_PER_PAGE = MATCHES_PER_PAGE * 4;

  function groupByFixture(rows) {
    const byMatch = new Map();
    for (const r of rows) {
      if (!byMatch.has(r.match_id)) {
        byMatch.set(r.match_id, {
          match_id: r.match_id,
          home_team: r.home_team,
          away_team: r.away_team,
          kickoff_utc: r.kickoff_utc,
          home_goals: r.home_goals,
          away_goals: r.away_goals,
          markets: {},
        });
      }
      const entry = byMatch.get(r.match_id);
      if (!entry.markets[r.market]) entry.markets[r.market] = {};
      entry.markets[r.market][r.outcome] = {
        probability: r.probability,
        is_pick: r.is_pick,
        is_hit: r.is_hit,
        actual_outcome: r.actual_outcome,
      };
    }
    return Array.from(byMatch.values());
  }

  function marketBlock(label, outcomes, leftKey, rightKey, graded) {
    if (!outcomes) return "";
    const left = outcomes[leftKey] || { probability: 0 };
    const right = outcomes[rightKey] || { probability: 0 };
    const pickKey = left.is_pick ? leftKey : rightKey;
    const pickOutcome = left.is_pick ? left : right;
    return (
      `<div class="market-block">` +
      `<div class="market-block-head"><strong>${label}</strong>` +
      `<span class="badge badge-pick">pick: ${pickKey}</span>` +
      (graded ? UI.hitBadge(pickOutcome.is_hit) : "") +
      "</div>" +
      UI.binaryBar(leftKey, rightKey, left.probability, right.probability) +
      "</div>"
    );
  }

  function fixtureCard(entry, graded) {
    const score = graded ? `<span class="score">${entry.home_goals}–${entry.away_goals}</span> ` : "";
    return (
      '<article class="fixture">' +
      '<div class="fixture-head">' +
      `<span class="teams">${UI.escapeHtml(entry.home_team)} ${score}v ${UI.escapeHtml(entry.away_team)}</span>` +
      (graded ? UI.incidentBadge(entry.match_id) : "") +
      `<span class="kickoff">${UI.formatKickoff(entry.kickoff_utc)}</span>` +
      "</div>" +
      marketBlock("BTTS", entry.markets["BTTS"], "Yes", "No", graded) +
      marketBlock("Over/Under 2.5", entry.markets["OU2.5"], "Over", "Under", graded) +
      "</article>"
    );
  }

  function accuracyTable(rows) {
    if (!rows.length) {
      return '<p class="empty-state">No market predictions have been graded yet.</p>';
    }
    const body = rows
      .map(
        (r) =>
          `<tr><td>${UI.escapeHtml(r.market)}</td><td class="num">${r.graded}</td>` +
          `<td class="num">${UI.pct1(r.accuracy)}</td>` +
          `<td class="num">${Number(r.log_loss).toFixed(3)}</td>` +
          `<td class="num">${Number(r.brier).toFixed(3)}</td></tr>`
      )
      .join("");
    return (
      '<div class="table-scroll"><table><thead><tr>' +
      '<th>Market</th><th class="num">Graded</th><th class="num">Accuracy</th>' +
      '<th class="num">Log loss</th><th class="num">Brier</th>' +
      "</tr></thead><tbody>" + body + "</tbody></table></div>"
    );
  }

  async function renderAccuracy() {
    const league = cfg.league || "EPL";
    const { rows } = await API.query("v_market_accuracy", {
      league: `eq.${league}`,
      model_version: `eq.${cfg.modelVersion}`,
      order: "market.asc",
    });
    document.getElementById("market-accuracy-body").innerHTML = accuracyTable(rows);
  }

  async function renderUpcoming() {
    const league = cfg.league || "EPL";
    const { rows } = await API.query("v_market_track_record", {
      league: `eq.${league}`,
      model_version: `eq.${cfg.modelVersion}`,
      is_hit: "is.null",
      order: "kickoff_utc.asc,match_id.asc",
    });
    const fixtures = groupByFixture(rows);
    document.getElementById("market-upcoming-count").textContent =
      fixtures.length ? fixtures.length + (fixtures.length === 1 ? " fixture" : " fixtures") : "";
    const el = document.getElementById("market-upcoming-body");
    el.innerHTML = fixtures.length
      ? '<div class="fixture-list">' + fixtures.map((f) => fixtureCard(f, false)).join("") + "</div>"
      : '<p class="empty-state">No upcoming market predictions right now.</p>';
  }

  async function renderResults() {
    const league = cfg.league || "EPL";
    const page = UI.currentPage();
    const offset = (page - 1) * ROWS_PER_PAGE;

    const { rows, total } = await API.query(
      "v_market_track_record",
      {
        league: `eq.${league}`,
        model_version: `eq.${cfg.modelVersion}`,
        is_hit: "not.is.null",
        order: "kickoff_utc.desc,match_id.desc",
        limit: String(ROWS_PER_PAGE),
        offset: String(offset),
      },
      { exact: true }
    );
    const fixtures = groupByFixture(rows);
    const totalMatches = total != null ? Math.ceil(total / 4) : null;

    document.getElementById("market-results-count").textContent =
      totalMatches != null ? totalMatches + (totalMatches === 1 ? " match" : " matches") : "";

    const el = document.getElementById("market-results-body");
    el.innerHTML = fixtures.length
      ? '<div class="fixture-list">' + fixtures.map((f) => fixtureCard(f, true)).join("") + "</div>"
      : '<p class="empty-state">Nothing graded yet.</p>';

    document.getElementById("market-results-pagination").innerHTML =
      totalMatches != null ? UI.renderPagination(page, MATCHES_PER_PAGE, totalMatches) : "";
  }

  async function main() {
    UI.mountShell();
    try {
      await renderAccuracy();
    } catch (err) {
      UI.showError("market-accuracy-body", err.message);
    }
    try {
      await renderUpcoming();
    } catch (err) {
      UI.showError("market-upcoming-body", err.message);
    }
    try {
      await renderResults();
    } catch (err) {
      UI.showError("market-results-body", err.message);
    }
  }

  main();
})();
