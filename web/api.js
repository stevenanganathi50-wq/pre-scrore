/* Minimal PostgREST client. No SDK, no build step -- plain fetch() against
 * the same REST endpoints prescore/supabase_sync.py already talks to, just
 * with the anon key instead of the service role key.
 *
 * Row Level Security is what makes this safe to run from a browser: the
 * anon key can read the public tables/views and cannot write anything (see
 * supabase/migrations/ and the RLS policies there). "Live" here means every
 * page load queries this directly -- no persistent connection, no
 * websocket, just fresh data on every visit.
 */

(function () {
  "use strict";

  const cfg = window.PRESCORE_CONFIG || {};
  const BASE = (cfg.supabaseUrl || "").replace(/\/$/, "") + "/rest/v1";

  function headers(extra) {
    return Object.assign(
      {
        apikey: cfg.anonKey || "",
        Authorization: "Bearer " + (cfg.anonKey || ""),
      },
      extra || {}
    );
  }

  /**
   * Query one table or view. `params` are raw PostgREST query params, e.g.
   * {select: "*", model_version: "eq.poisson-dc-1.3", order: "kickoff_utc.desc",
   *  limit: "20", offset: "40"}.
   *
   * Pass {exact: true} to also get a total row count back (via the
   * Content-Range response header) -- needed for real pagination controls,
   * since PostgREST only returns that when explicitly asked for it.
   */
  async function query(table, params, opts) {
    opts = opts || {};
    if (!cfg.supabaseUrl || !cfg.anonKey) {
      throw new Error(
        "PRESCORE_CONFIG is missing supabaseUrl/anonKey -- config.js did not load"
      );
    }
    const qs = new URLSearchParams(params || {}).toString();
    const url = BASE + "/" + table + (qs ? "?" + qs : "");
    const res = await fetch(url, {
      headers: headers(opts.exact ? { Prefer: "count=exact" } : {}),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${table} request failed: HTTP ${res.status} ${text}`.trim());
    }
    const rows = await res.json();
    let total = null;
    const range = res.headers.get("content-range"); // "0-19/143"
    if (range) {
      const m = /\/(\d+)$/.exec(range);
      if (m) total = parseInt(m[1], 10);
    }
    return { rows, total };
  }

  window.PrescoreAPI = { query, config: cfg };
})();
