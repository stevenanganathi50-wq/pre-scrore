/* pre-scrore frontend. No framework, no build step.
 *
 * Data arrives one of two ways: data.js sets window.PRESCORE_DATA (works when
 * index.html is opened straight from disk), otherwise we fetch data.json
 * (the normal path when hosted).
 */

(function () {
  "use strict";

  // Whole percent for the bars, where a decimal would be visual noise.
  const pct = (p) => Math.round(p * 100) + "%";
  // One decimal for accuracy figures -- the headline number should not be
  // blurrier than the record behind it.
  const pct1 = (p) => (p * 100).toFixed(1) + "%";

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(
      /[&<>"']/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  function formatKickoff(iso) {
    if (!iso) return "";
    const when = new Date(iso);
    if (isNaN(when)) return escapeHtml(iso);
    return when.toLocaleString(undefined, {
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  const OUTCOME_LABEL = { H: "Home", D: "Draw", A: "Away" };

  function pickLabel(entry) {
    if (entry.pick === "H") return escapeHtml(entry.home);
    if (entry.pick === "A") return escapeHtml(entry.away);
    return "Draw";
  }

  /* A stacked bar is more honest than a single headline number: it shows how
   * much of the probability mass actually sits behind the pick. */
  function probabilityBar(entry) {
    const segs = [
      { key: "h", value: entry.p_home },
      { key: "d", value: entry.p_draw },
      { key: "a", value: entry.p_away },
    ];
    const bar = segs
      .map(
        (s) =>
          `<span class="seg-${s.key}" style="flex:${s.value}">` +
          (s.value >= 0.12 ? pct(s.value) : "") +
          `</span>`
      )
      .join("");

    return (
      `<div class="bar" role="img" aria-label="Home ${pct(entry.p_home)}, ` +
      `draw ${pct(entry.p_draw)}, away ${pct(entry.p_away)}">${bar}</div>` +
      `<div class="bar-key">` +
      `<span>${escapeHtml(entry.home)} ${pct(entry.p_home)}</span>` +
      `<span>Draw ${pct(entry.p_draw)}</span>` +
      `<span>${escapeHtml(entry.away)} ${pct(entry.p_away)}</span>` +
      `</div>`
    );
  }

  function thinHistoryBadge(entry) {
    if (!entry.thin_history || !entry.thin_history.length) return "";
    const names = entry.thin_history.map(escapeHtml).join(", ");
    return (
      `<span class="badge badge-warn" title="Little or no Premier League ` +
      `history in our data, so this team is rated near league average.">` +
      `thin history: ${names}</span>`
    );
  }

  function renderUpcoming(entries) {
    const el = document.getElementById("upcoming-body");
    if (!entries.length) {
      el.innerHTML =
        '<p class="muted">No upcoming fixtures have been predicted yet. ' +
        "Run <code>python -m prescore run</code> to sync fixtures and publish.</p>";
      return;
    }

    el.innerHTML =
      '<div class="fixture-list">' +
      entries
        .map(
          (e) =>
            '<article class="fixture">' +
            '<div class="fixture-head">' +
            `<span class="teams">${escapeHtml(e.home)} v ${escapeHtml(e.away)}</span>` +
            `<span class="badge badge-pick">pick: ${pickLabel(e)}</span>` +
            thinHistoryBadge(e) +
            `<span class="kickoff">${formatKickoff(e.kickoff_utc)}</span>` +
            "</div>" +
            probabilityBar(e) +
            "</article>"
        )
        .join("") +
      "</div>";
  }

  function renderResults(entries) {
    const el = document.getElementById("results-body");
    if (!entries.length) {
      el.innerHTML =
        '<p class="muted">Nothing graded yet. Results appear here once ' +
        "predicted matches have been played — wins and losses alike.</p>";
      return;
    }

    el.innerHTML =
      '<div class="fixture-list">' +
      entries
        .map(function (e) {
          const badge = e.is_hit
            ? '<span class="badge badge-hit">hit</span>'
            : '<span class="badge badge-miss">miss</span>';
          return (
            '<article class="fixture">' +
            '<div class="fixture-head">' +
            `<span class="teams">${escapeHtml(e.home)} ` +
            `<span class="score">${e.home_goals}–${e.away_goals}</span> ` +
            `${escapeHtml(e.away)}</span>` +
            badge +
            `<span class="badge badge-pick">picked: ${pickLabel(e)}</span>` +
            `<span class="kickoff">${formatKickoff(e.kickoff_utc)}</span>` +
            "</div>" +
            probabilityBar(e) +
            "</article>"
          );
        })
        .join("") +
      "</div>";
  }

  function confidenceTable(buckets) {
    if (!buckets || !buckets.length) return "";
    return (
      "<h3>By confidence</h3>" +
      '<div class="table-scroll"><table><thead><tr>' +
      '<th>Confidence in the pick</th><th class="num">Predictions</th>' +
      '<th class="num">Hits</th><th class="num">Accuracy</th>' +
      "</tr></thead><tbody>" +
      buckets
        .map(
          (b) =>
            "<tr>" +
            `<td>${escapeHtml(b.range)}</td>` +
            `<td class="num">${b.n}</td>` +
            `<td class="num">${b.hits}</td>` +
            `<td class="num">${pct1(b.accuracy)}</td>` +
            "</tr>"
        )
        .join("") +
      "</tbody></table></div>"
    );
  }

  function backtestCallout(backtest, hasLiveRecord) {
    if (!backtest) return "";
    const heading = hasLiveRecord
      ? "For context: the backtest."
      : "No live record yet — here is the backtest instead.";
    return (
      '<div class="callout">' +
      `<strong>${heading}</strong>` +
      `Replaying ${backtest.test_from} to ${backtest.test_to}, refitting the ` +
      `model before every match date and predicting only from data available ` +
      `at that moment, it called <strong>${backtest.hits} of ` +
      `${backtest.n}</strong> matches correctly ` +
      `(${pct1(backtest.accuracy)}). A backtest is not a track record: it is ` +
      "what the model would have done, not what it did in public. The numbers " +
      "above this line are the ones that count." +
      "</div>"
    );
  }

  function renderRecord(data) {
    const el = document.getElementById("record-body");
    const overall = data.accuracy && data.accuracy.overall;

    if (!overall || !overall.n) {
      el.innerHTML =
        '<p class="muted">No predictions have been graded yet, so there is no ' +
        "published accuracy figure. There will be no retroactive edits when " +
        "there is.</p>" +
        backtestCallout(data.backtest, false);
      return;
    }

    const stats = [
      { label: "Accuracy", value: pct1(overall.accuracy) },
      { label: "Graded", value: overall.n },
      { label: "Hits", value: overall.hits },
      { label: "Misses", value: overall.n - overall.hits },
      { label: "Log loss", value: overall.log_loss.toFixed(3) },
      { label: "RPS", value: overall.rps.toFixed(3) },
    ];

    el.innerHTML =
      '<div class="stat-row">' +
      stats
        .map(
          (s) =>
            "<div>" +
            `<div class="stat-value">${escapeHtml(s.value)}</div>` +
            `<div class="stat-label">${escapeHtml(s.label)}</div>` +
            "</div>"
        )
        .join("") +
      "</div>" +
      confidenceTable(data.accuracy.by_confidence) +
      backtestCallout(data.backtest, true);
  }

  function render(data) {
    document.getElementById("league-name").textContent =
      data.league + " predictions";
    document.getElementById("disclaimer").textContent = data.disclaimer || "";
    const versions = data.model_versions || [];
    let meta = "Showing model " + data.model_version + ".";
    if (versions.length > 1) {
      const others = versions
        .filter((v) => v.version !== data.model_version)
        .map((v) => `${escapeHtml(v.version)} (${v.published})`)
        .join(", ");
      meta +=
        " Earlier versions remain in the database and are not counted in the" +
        " figures above, because averaging two different predictors into one" +
        " accuracy number would misrepresent both. Superseded: " +
        others +
        ". Nothing has been deleted — published predictions cannot be.";
    }
    document.getElementById("model-meta").textContent = meta;
    document.getElementById("generated-at").textContent =
      "Data generated " + formatKickoff(data.generated_at) + ".";

    renderRecord(data);
    renderUpcoming(data.upcoming || []);
    renderResults(data.results || []);
  }

  function showError(message) {
    document.getElementById("main").insertAdjacentHTML(
      "afterbegin",
      '<div class="panel"><div class="callout error"><strong>Could not load ' +
        "predictions.</strong>" +
        escapeHtml(message) +
        "</div></div>"
    );
  }

  if (window.PRESCORE_DATA) {
    render(window.PRESCORE_DATA);
  } else {
    fetch("data.json")
      .then((r) => {
        if (!r.ok) throw new Error("data.json returned " + r.status);
        return r.json();
      })
      .then(render)
      .catch(() =>
        showError(
          "Run `python -m prescore export` to generate it, then serve this " +
            "folder with `python -m http.server` and open the localhost URL."
        )
      );
  }
})();
