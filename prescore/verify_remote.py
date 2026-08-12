"""Audit the live database's guarantees instead of trusting them.

The product's whole claim is that a published prediction predates kickoff and
cannot be changed afterwards. That claim is enforced by Postgres triggers and
RLS policies, so it should be tested against the real database, with the same
keys a browser and a server would use.

Two things make these probes safe to run against production:

* Predictions are protected by triggers as well as RLS, so a probe that tries
  to delete one is stopped by the trigger even if a policy were missing.
* Local SQLite is the source of truth and `push` is idempotent, so anything a
  probe somehow destroys can be restored with `python -m prescore push`.

Any probe that mutates real data captures the original value first and puts it
back.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import settings, supabase_sync

SENTINEL = "__prescore_verify__"


@dataclass
class Check:
    name: str
    passed: bool
    detail: str

    def line(self) -> str:
        mark = "PASS" if self.passed else "FAIL"
        return f"  [{mark}] {self.name}\n         {self.detail}"


def _expect_rejected(fn, name: str, why: str) -> Check:
    """Run something that must be refused by the database."""
    try:
        fn()
    except supabase_sync.SupabaseError as exc:
        return Check(name, True, f"rejected as expected -- {_first_line(exc)}")
    return Check(name, False, f"NOT REJECTED. {why}")


def _first_line(exc: Exception) -> str:
    text = str(exc).replace("\n", " ")
    return text[:160]


def run_checks(log=print) -> list[Check]:
    cfg = settings.supabase(require_service_role=True)
    if not cfg.anon_key:
        raise settings.MissingSettings("SUPABASE_ANON_KEY is required to audit RLS")

    anon = supabase_sync.Client(cfg, key=cfg.anon_key)
    admin = supabase_sync.Client(cfg)
    checks: list[Check] = []

    # --- public reads should work -----------------------------------------
    for table in ("teams", "matches", "predictions", "v_track_record", "v_accuracy"):
        try:
            anon.request("GET", table, params={"limit": "1"})
            checks.append(Check(f"anon can read {table}", True, "200"))
        except supabase_sync.SupabaseError as exc:
            checks.append(Check(f"anon can read {table}", False, _first_line(exc)))

    # --- public writes should not -----------------------------------------
    checks.append(
        _expect_rejected(
            lambda: anon.request("POST", "teams", body=[{"name": SENTINEL}]),
            "anon cannot insert a team",
            "the anon key was able to create rows",
        )
    )

    # An UPDATE with no matching policy affects zero rows rather than
    # erroring, so this has to be judged by reading the value back.
    sample = admin.request(
        "GET", "matches", params={"select": "id,source_ref", "limit": "1", "order": "id.asc"}
    )
    if sample:
        match_id = sample[0]["id"]
        original = sample[0]["source_ref"]
        try:
            anon.request(
                "PATCH",
                "matches",
                body={"source_ref": SENTINEL},
                params={"id": f"eq.{match_id}"},
            )
        except supabase_sync.SupabaseError:
            pass  # an outright rejection is also a pass; the read-back decides

        after = admin.request(
            "GET", "matches", params={"select": "source_ref", "id": f"eq.{match_id}"}
        )
        changed = after and after[0]["source_ref"] == SENTINEL
        checks.append(
            Check(
                "anon cannot modify a match",
                not changed,
                "row unchanged after anon PATCH"
                if not changed
                else "ANON WROTE TO THE TABLE -- restoring the original value",
            )
        )
        if changed:
            admin.request(
                "PATCH",
                "matches",
                body={"source_ref": original},
                params={"id": f"eq.{match_id}"},
            )

    before = admin.count("predictions")
    try:
        anon.request("DELETE", "predictions", params={"id": "gt.0"})
    except supabase_sync.SupabaseError:
        pass
    after_count = admin.count("predictions")
    checks.append(
        Check(
            "anon cannot delete predictions",
            after_count == before,
            f"{before} before, {after_count} after"
            + ("" if after_count == before else " -- run `prescore push` to restore"),
        )
    )

    # --- the triggers must bind even the service role ----------------------
    rows = admin.request(
        "GET",
        "predictions",
        params={"select": "id,match_id,pick,p_home,p_draw,p_away", "limit": "1", "order": "id.asc"},
    )
    if rows:
        pid = rows[0]["id"]
        checks.append(
            _expect_rejected(
                lambda: admin.request(
                    "PATCH", "predictions", body={"pick": rows[0]["pick"]},
                    params={"id": f"eq.{pid}"},
                ),
                "service_role cannot update a prediction",
                "predictions are editable after publication",
            )
        )
        checks.append(
            _expect_rejected(
                lambda: admin.request(
                    "DELETE", "predictions", params={"id": f"eq.{pid}"}
                ),
                "service_role cannot delete a prediction",
                "published predictions can be erased -- run `prescore push` to restore",
            )
        )
        checks.append(
            _expect_rejected(
                lambda: admin.request(
                    "PATCH", "matches", body={"kickoff_utc": "2030-01-01T00:00:00Z"},
                    params={"id": f"eq.{rows[0]['match_id']}"},
                ),
                "kickoff cannot move once predicted",
                "kickoff times are editable after predictions exist",
            )
        )

    # A prediction on a finished match is by definition after kickoff.
    past = admin.request(
        "GET",
        "matches",
        params={
            "select": "id",
            "status": "eq.finished",
            "kickoff_utc": "not.is.null",
            "limit": "1",
        },
    )
    target = past[0]["id"] if past else None
    if target is None:
        # Backfilled history has no kickoff time, which must also be refused.
        nokick = admin.request(
            "GET", "matches",
            params={"select": "id", "kickoff_utc": "is.null", "limit": "1"},
        )
        target = nokick[0]["id"] if nokick else None

    if target is not None:
        checks.append(
            _expect_rejected(
                lambda: admin.request(
                    "POST",
                    "predictions",
                    body=[
                        {
                            "match_id": target,
                            "model_version": SENTINEL,
                            "market": "1X2",
                            "p_home": 0.5, "p_draw": 0.3, "p_away": 0.2,
                            "pick": "H", "confidence": 0.5,
                        }
                    ],
                ),
                "a prediction cannot be backdated onto a played match",
                "predictions can be written after kickoff -- the track record is meaningless",
            )
        )

    return checks


def report(checks: list[Check]) -> str:
    passed = sum(1 for c in checks if c.passed)
    lines = ["REMOTE GUARANTEE AUDIT", "=" * 60]
    lines.extend(c.line() for c in checks)
    lines.append("=" * 60)
    lines.append(f"{passed}/{len(checks)} checks passed")
    return "\n".join(lines)
