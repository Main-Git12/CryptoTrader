from crypto_trader.leaderboard import (
    LeaderboardEntry,
    load_leaderboard,
    merge_leaderboard,
    save_leaderboard,
)
from crypto_trader.metrics import PerformanceMetrics


def _entry(name: str, total_return_pct: float, symbol: str = "BTC/USD", timeframe: str = "1h") -> LeaderboardEntry:
    return LeaderboardEntry(
        name=name,
        kind="sma",
        params={"fast": 10, "slow": 30},
        symbol=symbol,
        timeframe=timeframe,
        metrics=PerformanceMetrics(
            total_return_pct=total_return_pct,
            max_drawdown_pct=5.0,
            win_rate=0.5,
            trade_count=4,
            sharpe_ratio=0.1,
        ),
    )


def test_load_returns_empty_list_when_file_is_missing(tmp_path):
    assert load_leaderboard(str(tmp_path / "nope.json")) == []


def test_save_then_load_round_trips_entries(tmp_path):
    path = str(tmp_path / "leaderboard.json")
    entries = [_entry("sma(fast=10,slow=30)", 12.5)]

    save_leaderboard(path, entries)
    loaded = load_leaderboard(path)

    assert loaded == entries


def test_merge_keeps_best_by_total_return(tmp_path):
    existing = [_entry("a", 5.0), _entry("b", 1.0)]
    new_entries = [_entry("c", 9.0)]

    merged = merge_leaderboard(existing, new_entries, keep=2)

    assert [e.name for e in merged] == ["c", "a"]


def test_merge_replaces_an_earlier_measurement_of_the_same_config():
    # Same config, same market: the newer run covers more recent history, so
    # it should replace the old row rather than both surviving.
    existing = [_entry("sma(fast=10,slow=30)", 5.0)]
    new_entries = [_entry("sma(fast=10,slow=30)", -2.0)]

    merged = merge_leaderboard(existing, new_entries)

    assert len(merged) == 1
    assert merged[0].metrics.total_return_pct == -2.0


def test_merge_keeps_the_same_config_separately_per_market():
    existing = [_entry("sma(fast=10,slow=30)", 5.0, symbol="BTC/USD")]
    new_entries = [
        _entry("sma(fast=10,slow=30)", 7.0, symbol="ETH/USD"),
        _entry("sma(fast=10,slow=30)", 6.0, symbol="BTC/USD", timeframe="4h"),
    ]

    merged = merge_leaderboard(existing, new_entries)

    assert len(merged) == 3


def test_save_leaves_no_tmp_file_behind(tmp_path):
    path = tmp_path / "leaderboard.json"
    save_leaderboard(str(path), [_entry("a", 1.0)])

    assert path.exists()
    assert not path.with_suffix(".json.tmp").exists()
