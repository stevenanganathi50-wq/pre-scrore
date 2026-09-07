/* Method page: only the model-versions comparison is live; the rest of the
 * page is static prose (see method.html). */

(function () {
  "use strict";

  const UI = window.PrescoreUI;
  const API = window.PrescoreAPI;
  const cfg = window.PRESCORE_CONFIG || {};

  function table(rows) {
    if (!rows.length) return '<p class="empty-state">No graded predictions yet.</p>';
    const body = rows
      .map((r) => {
        const isCurrent = r.model_version === cfg.modelVersion;
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
      '<div class="table-scroll"><table><thead><tr>' +
      '<th>Version</th><th class="num">Graded</th><th class="num">Accuracy</th>' +
      '<th class="num">Log loss</th><th class="num">RPS</th>' +
      "</tr></thead><tbody>" + body + "</tbody></table></div>"
    );
  }

  async function main() {
    UI.mountShell();
    try {
      const league = cfg.league || "EPL";
      const { rows } = await API.query("v_accuracy", { league: `eq.${league}`, order: "model_version.asc" });
      document.getElementById("versions-body").innerHTML = table(rows);
    } catch (err) {
      UI.showError("versions-body", err.message);
    }
  }

  main();
})();
