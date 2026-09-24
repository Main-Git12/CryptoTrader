import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist

# Euler-Mascheroni constant, from the expected value of the maximum of N
# draws from a standard normal (Bailey & López de Prado 2014).
_EULER_MASCHERONI = 0.5772156649015329


@dataclass
class DeflatedSharpe:
    probability: float  # P(true Sharpe > 0), after correcting for the search
    observed_sharpe: float
    benchmark_sharpe: float  # SR*: the best a lucky no-skill search would find
    trials: int


def expected_max_sharpe(trial_sharpes: Sequence[float]) -> float:
    """SR* — the highest Sharpe ratio you would expect to see from this many
    strategies *even if every one of them had zero real skill*, given how
    much the observed Sharpes vary.

    This is the bar a search result has to clear. Testing more
    configurations raises it: the maximum of many noisy draws grows with the
    number of draws, so a headline Sharpe that would be impressive from one
    strategy can be unremarkable as the best of fifty.
    """
    trials = len(trial_sharpes)
    if trials < 2:
        return 0.0

    spread = math.sqrt(statistics.variance(trial_sharpes))
    if spread <= 0:
        return 0.0

    normal = NormalDist()
    return spread * (
        (1 - _EULER_MASCHERONI) * normal.inv_cdf(1 - 1 / trials)
        + _EULER_MASCHERONI * normal.inv_cdf(1 - 1 / (trials * math.e))
    )


def deflated_sharpe_ratio(
    observed_sharpe: float,
    trial_sharpes: Sequence[float],
    return_count: int,
    skewness: float | None = None,
    kurtosis: float | None = None,
) -> DeflatedSharpe | None:
    """The probability that the selected strategy's true Sharpe is above
    zero, given that it was picked as the best of `len(trial_sharpes)`
    attempts (Bailey & López de Prado, 2014).

    An ordinary Sharpe ratio asks "is this good?". This asks "is this good
    *given how hard we looked*?" — which is the question that matters after
    a parameter search, because the winner of a large search is partly
    selected for luck. Roughly: above 0.95 the result survives the
    correction; below that, the search itself plausibly explains it.

    `skewness` and `kurtosis` correct the Sharpe's normality assumption:
    negative skew and fat tails both make a given Sharpe less trustworthy.
    Omitted, they default to a normal distribution's values.

    Returns None when there isn't enough to compute it — fewer than two
    trials, too few returns, or a degenerate distribution. None means
    "unknown", which is different from "failed", and callers should say so
    rather than printing a zero.
    """
    if return_count < 2 or len(trial_sharpes) < 2:
        return None

    benchmark = expected_max_sharpe(trial_sharpes)
    skew = 0.0 if skewness is None else skewness
    kurt = 3.0 if kurtosis is None else kurtosis

    # Standard error of the Sharpe estimate, widened for skew and fat tails.
    variance = 1 - skew * observed_sharpe + (kurt - 1) / 4 * observed_sharpe**2
    if variance <= 0:
        return None

    test_statistic = (observed_sharpe - benchmark) * math.sqrt(return_count - 1) / math.sqrt(variance)
    return DeflatedSharpe(
        probability=NormalDist().cdf(test_statistic),
        observed_sharpe=observed_sharpe,
        benchmark_sharpe=benchmark,
        trials=len(trial_sharpes),
    )
