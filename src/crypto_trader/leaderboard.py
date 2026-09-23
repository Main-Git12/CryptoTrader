import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from .metrics import PerformanceMetrics

DEFAULT_KEEP = 25


@dataclass
class LeaderboardEntry:
    name: str
    kind: str
    params: dict[str, float]
    symbol: str
    timeframe: str
    metrics: PerformanceMetrics


def load_leaderboard(path: str) -> list[LeaderboardEntry]:
    """Returns [] when the file doesn't exist yet — a first run, not an error."""
    target = Path(path)
    if not target.exists():
        return []

    payload = json.loads(target.read_text())
    return [
        LeaderboardEntry(
            name=row["name"],
            kind=row["kind"],
            params=row["params"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            metrics=PerformanceMetrics(**row["metrics"]),
        )
        for row in payload["entries"]
    ]


def save_leaderboard(path: str, entries: Sequence[LeaderboardEntry]) -> None:
    """Written write-then-rename, so an interrupted save can't leave a
    half-written leaderboard that the next run fails to parse."""
    payload = {
        "entries": [
            {
                "name": entry.name,
                "kind": entry.kind,
                "params": entry.params,
                "symbol": entry.symbol,
                "timeframe": entry.timeframe,
                "metrics": asdict(entry.metrics),
            }
            for entry in entries
        ]
    }
    target = Path(path)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2))
    tmp_path.replace(target)


def merge_leaderboard(
    existing: Sequence[LeaderboardEntry],
    new_entries: Sequence[LeaderboardEntry],
    keep: int = DEFAULT_KEEP,
) -> list[LeaderboardEntry]:
    """Combines a previous leaderboard with this run's results, keeping the
    best `keep` by total return.

    A configuration re-tested in a later run replaces its older entry for
    the same symbol and timeframe rather than appearing twice: the newer
    measurement covers more recent history, so it's the one worth keeping.
    Entries for different symbols or timeframes are independent — the same
    parameters can be great on one market and useless on another.
    """
    by_key = {(entry.name, entry.symbol, entry.timeframe): entry for entry in existing}
    for entry in new_entries:
        by_key[(entry.name, entry.symbol, entry.timeframe)] = entry

    ranked = sorted(by_key.values(), key=lambda entry: entry.metrics.total_return_pct, reverse=True)
    return ranked[:keep]
