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

  // --- theme toggle ---------------------------------------------------

  function initTheme() {
    const btn = document.getElementById("theme-toggle");
    const icon = document.getElementById("theme-icon");
    const root = document.documentElement;

    function systemPrefersDark() {
      return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    }

    function currentTheme() {
      const explicit = root.getAttribute("data-theme");
      if (explicit === "light" || explicit === "dark") return explicit;
      return systemPrefersDark() ? "dark" : "light";
    }

    function paintIcon() {
      icon.textContent = currentTheme() === "dark" ? "☀" : "☾";
    }

    btn.addEventListener("click", function () {
      const next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {
        localStorage.setItem("prescore-theme", next);
      } catch (e) {}
      paintIcon();
    });

    paintIcon();
  }

  // --- shared bits ------------------------------------------------------

  const OUTCOME_LABEL = { H: "Home", D: "Draw", A: "Away" };

  function pickLabel(match, pick) {
    if (pick === "H") return escapeHtml(match.home);
    if (pick === "A") return escapeHtml(match.away);
    return "Draw";
  }

  /* A stacked bar is more honest than a single headline number: it shows how
   * much of the probability mass actually sits behind the pick. */
  function probabilityBar(home, away, p) {
    const segs = [
      { key: "h", value: p.p_home },
      { key: "d", value: p.p_draw },
      { key: "a", value: p.p_away },
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
      `<div class="bar" role="img" aria-label="Home ${pct(p.p_home)}, ` +
      `draw ${pct(p.p_draw)}, away ${pct(p.p_away)}">${bar}</div>` +
      `<div class="bar-key">` +
      `<span><span class="dot dot-h"></span>${escapeHtml(home)} ${pct(p.p_home)}</span>` +
      `<span><span class="dot dot-d"></span>Draw ${pct(p.p_draw)}</span>` +
      `<span><span class="dot dot-a"></span>${escapeHtml(away)} ${pct(p.p_away)}</span>` +
      `</div>`
    );
  }

  function thinHistoryBadge(match) {
    if (!match.thin_history || !match.thin_history.length) return "";
    const names = match.thin_history.map(escapeHtml).join(", ");
    return (
      `<span class="badge badge-warn" title="Little or no Premier League ` +
      `history in our data, so this team is rated near league average.">` +
      `thin history: ${names}</span>`
    );
  }

  /* Every model version that predicted a fixture, in one compact table --
   * "alongside the others" rather than picking a winner and hiding the rest. */
  function versionsTable(match, graded) {
    if (match.predictions.length < 2) return "";

    const rows = match.predictions
      .map((p) => {
        const gradeCell = !graded
          ? ""
          : p.is_hit === null
          ? "—"
          : p.is_hit
          ? '<span class="badge badge-hit">hit</span>'
          : '<span class="badge badge-miss">miss</span>';
        return (
          `<tr class="${p.is_current ? "is-current" : ""}">` +
          `<td><span class="version-pill">${escapeHtml(p.model_version)}` +
          (p.is_current ? '<span class="version-current-tag">current</span>' : "") +
          `</span></td>` +
          `<td class="num">${pct(p.p_home)}</td>` +
          `<td class="num">${pct(p.p_draw)}</td>` +
          `<td class="num">${pct(p.p_away)}</td>` +
          `<td>${pickLabel(match, p.pick)}</td>` +
          (graded ? `<td>${gradeCell}</td>` : "") +
          `</tr>`
        );
      })
      .join("");

    return (
      '<details class="versions-toggle">' +
      `<summary class="versions-summary"><span class="chev">▸</span> ` +
      `all ${match.predictions.length} model versions</summary>` +
      '<div class="versions-table-wrap"><table class="versions-table"><thead><tr>' +
      `<th>Version</th><th class="num">Home</th><th class="num">Draw</th>` +
      `<th class="num">Away</th><th>Pick</th>` +
      (graded ? "<th>Result</th>" : "") +
      `</tr></thead><tbody>${rows}</tbody></table></div>` +
      "</details>"
    );
  }

  function renderUpcoming(matches) {
    const el = document.getElementById("upcoming-body");
    document.getElementById("upcoming-count").textContent = matches.length
      ? matches.length + (matches.length === 1 ? " fixture" : " fixtures")
      : "";

    if (!matches.length) {
      el.innerHTML =
        '<p class="muted">No upcoming fixtures have been predicted yet. ' +
        "Run <code>python -m prescore run</code> to sync fixtures and publish.</p>";
      return;
    }

    el.innerHTML =
      '<div class="fixture-list">' +
      matches
        .map(function (m) {
          const current = m.predictions[0];
          return (
            '<article class="fixture">' +
            '<div class="fixture-head">' +
            `<span class="teams">${escapeHtml(m.home)} v ${escapeHtml(m.away)}</span>` +
            `<span class="badge badge-pick">pick: ${pickLabel(m, current.pick)}</span>` +
            thinHistoryBadge(m) +
            `<span class="kickoff">${formatKickoff(m.kickoff_utc)}</span>` +
            "</div>" +
            probabilityBar(m.home, m.away, current) +
            versionsTable(m, false) +
            "</article>"
          );
        })
        .join("") +
      "</div>";
  }

  function renderResults(matches) {
    const el = document.getElementById("results-body");
    document.getElementById("results-count").textContent = matches.length
      ? matches.length + (matches.length === 1 ? " match" : " matches")
      : "";

    if (!matches.length) {
      el.innerHTML =
        '<p class="muted">Nothing graded yet. Results appear here once ' +
        "predicted matches have been played — wins and losses alike.</p>";
      return;
    }

    el.innerHTML =
      '<div class="fixture-list">' +
      matches
        .map(function (m) {
          const current = m.predictions[0];
          const badge =
            current.is_hit === null
              ? ""
              : current.is_hit
              ? '<span class="badge badge-hit">hit</span>'
              : '<span class="badge badge-miss">miss</span>';
          return (
            '<article class="fixture">' +
            '<div class="fixture-head">' +
            `<span class="teams">${escapeHtml(m.home)} ` +
            `<span class="score">${m.home_goals}–${m.away_goals}</span> ` +
            `${escapeHtml(m.away)}</span>` +
            badge +
            `<span class="badge badge-pick">picked: ${pickLabel(m, current.pick)}</span>` +
            `<span class="kickoff">${formatKickoff(m.kickoff_utc)}</span>` +
            "</div>" +
            probabilityBar(m.home, m.away, current) +
            versionsTable(m, true) +
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

  /* Side-by-side accuracy once more than one version has graded predictions.
   * Nothing here until then -- an empty comparison table is worse than none. */
  function versionComparisonTable(accuracyByVersion, currentVersion) {
    const versions = Object.keys(accuracyByVersion || {});
    if (versions.length < 2) return "";

    const rows = versions
      .map(function (v) {
        const a = accuracyByVersion[v].overall;
        const isCurrent = v === currentVersion;
        return (
          `<tr class="${isCurrent ? "is-current-row" : ""}">` +
          `<td><span class="version-pill">${escapeHtml(v)}` +
          (isCurrent ? '<span class="version-current-tag">current</span>' : "") +
          `</span></td>` +
          `<td class="num">${a.n}</td>` +
          `<td class="num">${pct1(a.accuracy)}</td>` +
          `<td class="num">${a.log_loss.toFixed(3)}</td>` +
          `<td class="num">${a.rps.toFixed(3)}</td>` +
          "</tr>"
        );
      })
      .join("");

    return (
      "<h3>Compare model versions</h3>" +
      '<div class="table-scroll"><table><thead><tr>' +
      "<th>Version</th><th class=\"num\">Graded</th>" +
      '<th class="num">Accuracy</th><th class="num">Log loss</th>' +
      '<th class="num">RPS</th>' +
      "</tr></thead><tbody>" +
      rows +
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
      { label: "Accuracy", value: pct1(overall.accuracy), highlight: true },
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
            `<div class="stat-value${s.highlight ? " stat-highlight" : ""}">${escapeHtml(s.value)}</div>` +
            `<div class="stat-label">${escapeHtml(s.label)}</div>` +
            "</div>"
        )
        .join("") +
      "</div>" +
      confidenceTable(data.accuracy.by_confidence) +
      versionComparisonTable(data.accuracy_by_version, data.model_version) +
      backtestCallout(data.backtest, true);
  }

  function modelMetaText(data) {
    const versions = data.model_versions || [];
    let meta = "Currently predicting with model " + data.model_version + ".";
    if (versions.length > 1) {
      const others = versions
        .filter((v) => v.version !== data.model_version)
        .map((v) => escapeHtml(v.version))
        .join(", ");
      meta +=
        " " +
        versions.length +
        " versions have published into this record (" +
        others +
        " and the current one). Every fixture above shows all of them side by" +
        " side under “all model versions” — nothing is deleted or" +
        " hidden, and the headline accuracy figure only ever reflects one" +
        " version at a time.";
    }
    return meta;
  }

  function render(data) {
    document.getElementById("league-name").textContent =
      data.league + " predictions";
    document.getElementById("disclaimer").textContent = data.disclaimer || "";
    document.getElementById("model-meta").textContent = modelMetaText(data);
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

  initTheme();

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
