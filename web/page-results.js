/* Results page: paginated, live-queried graded 1X2 predictions.
 *
 * Real pagination -- limit/offset pushed to PostgREST, not a slice of an
 * already-fetched array. Page size is fixed and the page number lives in
 * the URL (?page=N), so results are bookmarkable and the back button works
 * without any client-side state to manage.
 */

(function () {
  "use strict";

  const UI = window.PrescoreUI;
  const API = window.PrescoreAPI;
  const cfg = window.PRESCORE_CONFIG || {};
  const PAGE_SIZE = 20;

  function pickLabel(row) {
    if (row.pick === "H") return UI.escapeHtml(row.home_team);
    if (row.pick === "A") return UI.escapeHtml(row.away_team);
    return "Draw";
  }

  function resultCard(row) {
    return (
      '<article class="fixture">' +
      '<div class="fixture-head">' +
      `<span class="teams">${UI.escapeHtml(row.home_team)} ` +
      `<span class="score">${row.home_goals}–${row.away_goals}</span> ` +
      `${UI.escapeHtml(row.away_team)}</span>` +
      UI.hitBadge(row.is_hit) +
      UI.incidentBadge(row.match_id) +
      `<span class="badge badge-pick">picked: ${pickLabel(row)}</span>` +
      `<span class="kickoff">${UI.formatKickoff(row.kickoff_utc)}</span>` +
      "</div>" +
      UI.probabilityBar(row.home_team, row.away_team, row) +
      "</article>"
    );
  }

  async function main() {
    UI.mountShell();
    const league = cfg.league || "EPL";
    const page = UI.currentPage();
    const offset = (page - 1) * PAGE_SIZE;

    try {
      const { rows, total } = await API.query(
        "v_track_record",
        {
          league: `eq.${league}`,
          model_version: `eq.${cfg.modelVersion}`,
          is_hit: "not.is.null",
          order: "kickoff_utc.desc",
          limit: String(PAGE_SIZE),
          offset: String(offset),
        },
        { exact: true }
      );

      document.getElementById("results-count").textContent =
        total != null ? total + (total === 1 ? " match" : " matches") : "";

      const body = document.getElementById("results-body");
      if (!rows.length) {
        body.innerHTML = page > 1
          ? '<p class="empty-state">Nothing on this page. <a href="results.html">Back to the first page</a>.</p>'
          : '<p class="empty-state">Nothing graded yet. Results appear here once predicted matches have been played — wins and losses alike.</p>';
      } else {
        body.innerHTML = '<div class="fixture-list">' + rows.map(resultCard).join("") + "</div>";
      }

      document.getElementById("results-pagination").innerHTML =
        total != null ? UI.renderPagination(page, PAGE_SIZE, total) : "";
    } catch (err) {
      UI.showError("results-body", err.message);
    }
  }

  main();
})();
