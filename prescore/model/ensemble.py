"""Combine two predictors into one set of probabilities.

An ensemble only earns its complexity when its members are wrong about
different things. The Poisson model reasons about goals scored and conceded;
ELO reasons about results alone. That is a genuine difference, so it is worth
testing -- but it has to be tested, not assumed.

Linear pooling (a weighted average of probabilities) is used rather than log
pooling. Averaging probabilities pulls the result toward the middle, which is
the conservative direction; log pooling multiplies them and can end up more
confident than either member, which is the wrong way to fail for a public
record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .poisson import Outcome


@dataclass
class Ensemble:
    """A weighted blend of two fitted models."""

    primary: object
    secondary: object
    weight: float  # share given to `primary`
    fitted_through: date
    version: str = field(default="ensemble-1.0")

    def knows(self, team: str) -> bool:
        return self.primary.knows(team) or self.secondary.knows(team)

    def predict(self, home: str, away: str) -> Outcome:
        a = self.primary.predict(home, away)
        b = self.secondary.predict(home, away)
        w = self.weight

        probs = tuple(
            w * pa + (1.0 - w) * pb for pa, pb in zip(a.as_tuple(), b.as_tuple())
        )
        total = sum(probs)
        p_home, p_draw, p_away = (p / total for p in probs)

        # Expected goals come from whichever member models them; ELO does not.
        expected_home = a.expected_home_goals
        expected_away = a.expected_away_goals

        return Outcome(p_home, p_draw, p_away, expected_home, expected_away)
