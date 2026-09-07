/* Shared rendering helpers used by every page: nav, theme toggle, formatting,
 * probability bars, badges, and pagination. Plain functions on
 * window.PrescoreUI -- no framework, no module system, so this just needs a
 * plain <script src="ui.js"> before a page's own script runs.
 *
 * Pagination is deliberately plain links (?page=2), not client-side state:
 * a full navigation on page change is bookmarkable, makes the back button
 * work for free, and keeps each page's script down to "fetch this page's
 * data, render it" with nothing to manage in between.
 */

(function () {
  "use strict";

  const pct = (p) => Math.round(p * 100) + "%";
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

  // --- theme toggle -------------------------------------------------------

  function initTheme() {
    const btn = document.getElementById("theme-toggle");
    if (!btn) return;
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
      if (icon) icon.textContent = currentTheme() === "dark" ? "☀" : "☾";
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

  // --- nav ------------------------------------------------------------

  const PAGES = [
    { href: "index.html", label: "Overview" },
    { href: "results.html", label: "Results" },
    { href: "markets.html", label: "Markets" },
    { href: "method.html", label: "Method" },
  ];

  function currentPageFile() {
    const path = location.pathname.split("/").pop() || "index.html";
    return path === "" ? "index.html" : path;
  }

  function renderNav() {
    const here = currentPageFile();
    return PAGES.map(
      (p) =>
        `<a href="${p.href}"${p.href === here ? ' class="active" aria-current="page"' : ""}>${p.label}</a>`
    ).join("");
  }

  function mountShell() {
    const navEl = document.getElementById("site-nav");
    if (navEl) navEl.innerHTML = renderNav();
    initTheme();
  }

  // --- probability bars -------------------------------------------------

  /** 3-way (1X2) bar: home/draw/away. */
  function probabilityBar(homeLabel, awayLabel, p) {
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
      `<div class="bar" role="img" aria-label="Home ${pct(p.p_home)}, draw ${pct(p.p_draw)}, away ${pct(p.p_away)}">${bar}</div>` +
      `<div class="bar-key">` +
      `<span><span class="dot dot-h"></span>${escapeHtml(homeLabel)} ${pct(p.p_home)}</span>` +
      `<span><span class="dot dot-d"></span>Draw ${pct(p.p_draw)}</span>` +
      `<span><span class="dot dot-a"></span>${escapeHtml(awayLabel)} ${pct(p.p_away)}</span>` +
      `</div>`
    );
  }

  /** 2-way (BTTS / Over-Under) bar: label pairs like ("Yes","No"). */
  function binaryBar(leftLabel, rightLabel, pLeft, pRight) {
    const bar =
      `<span class="seg-h" style="flex:${pLeft}">${pLeft >= 0.14 ? pct(pLeft) : ""}</span>` +
      `<span class="seg-a" style="flex:${pRight}">${pRight >= 0.14 ? pct(pRight) : ""}</span>`;
    return (
      `<div class="bar" role="img" aria-label="${escapeHtml(leftLabel)} ${pct(pLeft)}, ${escapeHtml(rightLabel)} ${pct(pRight)}">${bar}</div>` +
      `<div class="bar-key">` +
      `<span><span class="dot dot-h"></span>${escapeHtml(leftLabel)} ${pct(pLeft)}</span>` +
      `<span><span class="dot dot-a"></span>${escapeHtml(rightLabel)} ${pct(pRight)}</span>` +
      `</div>`
    );
  }

  function hitBadge(isHit) {
    if (isHit === null || isHit === undefined) return "";
    return isHit
      ? '<span class="badge badge-hit">hit</span>'
      : '<span class="badge badge-miss">miss</span>';
  }

  // --- known data incidents -----------------------------------------------
  // A "finished" flag can arrive from the data source before a match is
  // actually over -- see method.html's Known data incidents section. Grading
  // is now guarded against this going forward, but a graded result is
  // immutable, so a match already caught by it stays wrong on the record.
  // Flagged here rather than left unmarked.
  const KNOWN_DATA_INCIDENTS = {
    4209:
      'Graded on a score TheSportsDB reported 45 minutes after kickoff, ' +
      'before the match had actually finished. See Method → Known data incidents.',
  };

  function incidentBadge(matchId) {
    const note = KNOWN_DATA_INCIDENTS[matchId];
    if (!note) return "";
    return `<span class="badge badge-warn" title="${escapeHtml(note)}">⚠ data incident</span>`;
  }

  // --- confidence buckets -------------------------------------------------
  // Mirrors prescore/backtest/metrics.py's confidence_buckets exactly, so the
  // live page and the Python-computed backtest numbers describe the same
  // buckets. Computed client-side because it needs the whole graded set, not
  // one page of it -- a fundamentally different shape of query than a
  // paginated results list.
  const CONFIDENCE_EDGES = [0.0, 0.4, 0.5, 0.6, 0.7, 1.01];

  function confidenceBuckets(records) {
    // records: [{confidence, is_hit}]
    const out = [];
    for (let i = 0; i < CONFIDENCE_EDGES.length - 1; i++) {
      const lo = CONFIDENCE_EDGES[i];
      const hi = CONFIDENCE_EDGES[i + 1];
      let n = 0;
      let hits = 0;
      for (const r of records) {
        if (r.confidence >= lo && r.confidence < hi) {
          n++;
          if (r.is_hit) hits++;
        }
      }
      if (n > 0) {
        out.push({
          range: `${lo.toFixed(2)}-${Math.min(hi, 1.0).toFixed(2)}`,
          n,
          hits,
          accuracy: hits / n,
        });
      }
    }
    return out;
  }

  // --- pagination -----------------------------------------------------

  function currentPage() {
    const n = parseInt(new URLSearchParams(location.search).get("page") || "1", 10);
    return Number.isFinite(n) && n > 0 ? n : 1;
  }

  function pageUrl(n) {
    const params = new URLSearchParams(location.search);
    if (n <= 1) params.delete("page");
    else params.set("page", String(n));
    const qs = params.toString();
    return location.pathname.split("/").pop() + (qs ? "?" + qs : "");
  }

  function renderPagination(page, pageSize, total) {
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    if (totalPages <= 1) return "";
    page = Math.min(Math.max(1, page), totalPages);

    const links = [];
    const add = (n, label, disabled, extraClass) =>
      links.push(
        disabled
          ? `<span class="page-link disabled ${extraClass || ""}">${label}</span>`
          : `<a class="page-link ${extraClass || ""}" href="${pageUrl(n)}">${label}</a>`
      );

    add(page - 1, "‹ Prev", page <= 1);

    const window_ = 2;
    const shown = new Set();
    for (let n = 1; n <= totalPages; n++) {
      if (n === 1 || n === totalPages || Math.abs(n - page) <= window_) shown.add(n);
    }
    let last = 0;
    for (const n of Array.from(shown).sort((a, b) => a - b)) {
      if (last && n - last > 1) links.push('<span class="page-ellipsis">…</span>');
      add(n, String(n), false, n === page ? "current" : "");
      last = n;
    }

    add(page + 1, "Next ›", page >= totalPages);

    return (
      `<nav class="pagination" aria-label="Results pages">${links.join("")}</nav>` +
      `<p class="pagination-summary muted">Page ${page} of ${totalPages} (${total} total)</p>`
    );
  }

  function showError(containerId, message) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML =
      '<div class="callout error"><strong>Could not load this.</strong>' +
      escapeHtml(message) +
      "</div>";
  }

  window.PrescoreUI = {
    pct,
    pct1,
    escapeHtml,
    formatKickoff,
    mountShell,
    probabilityBar,
    binaryBar,
    hitBadge,
    incidentBadge,
    confidenceBuckets,
    currentPage,
    renderPagination,
    showError,
  };
})();
