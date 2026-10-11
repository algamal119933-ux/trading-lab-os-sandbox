"""AUTH-2 judged engine (research/auth2/engine/, research/auth2/engine_io.py): the follower's frozen
semantics, the amount precision, the paper-safe run config, and, where freqtrade 2026.7 is
installed, the proof that the launcher's skipped trade copy changes no result byte (CI runs the
same self-test inside the pinned image).

PAPER / RESEARCH ONLY. Backtesting only; dry_run true; keyless; synthetic data.
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("pyarrow")

from auth2 import engine_io as EIO  # noqa: E402
from auth2.engine import markets as MK  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FOLLOWER = REPO / "research/auth2/engine/AUTH2ScheduleFollower.py"


def class_attrs() -> dict:
    tree = ast.parse(FOLLOWER.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AUTH2ScheduleFollower")
    out = {}
    for n in cls.body:
        target = n.target if isinstance(n, ast.AnnAssign) else (n.targets[0] if isinstance(n, ast.Assign) else None)
        if isinstance(target, ast.Name) and n.value is not None:
            try:
                out[target.id] = ast.literal_eval(n.value)
            except ValueError:
                pass
    return out


def test_the_follower_has_no_stop_and_no_roi_and_is_long_only_spot():
    attrs = class_attrs()
    assert attrs["stoploss"] == -1.0
    assert attrs["minimal_roi"] == {}
    assert attrs.get("can_short", False) is False
    assert attrs["timeframe"] == "4h"


@pytest.mark.parametrize("price", [0.0001, 0.00123, 1.0, 37.5, 65000.0])
def test_amount_tick_keeps_15_significant_digits(price):
    tick = MK.amount_tick(price)
    max_amount = MK.NOTIONAL_CEILING / price
    assert max_amount / tick < 10 ** MK.SIGNIFICANT_DIGITS
    assert tick == 10.0 ** round(math.log10(tick))  # a power of ten: exact decimal truncation


def test_the_frozen_market_table_is_neutral_spot(tmp_path):
    body = MK.write(["AAA/USDT", "BBB/USDT"], tmp_path / "m.json", {"AAA/USDT": 0.5, "BBB/USDT": 100.0})
    markets = json.loads(body)
    rows = markets if isinstance(markets, list) else list(markets.values())
    for m in rows:
        assert m["spot"] is True and m["quote"] == "USDT" and m["active"] is True
        assert m["precision"]["price"] is None
        assert not m.get("margin") and not m.get("future") and not m.get("swap")


def test_a_prepared_run_is_paper_safe(tmp_path):
    t = np.arange(10, dtype=np.int64) * 14_400_000 + 1_546_300_800_000
    bars = np.column_stack([t, np.full(10, 1.0), np.full(10, 1.1), np.full(10, 0.9), np.full(10, 1.0),
                            np.full(10, 5.0)])
    doc = {"rows": [{"t": int(t[1]), "w": {"AAA/USDT": 0.5}}], "forced_exits": []}
    spec = EIO.prepare_run(tmp_path, ["AAA/USDT"], {"AAA/USDT": bars}, doc, 0.0015, int(t[0]), int(t[-1]))
    cfg = json.loads((tmp_path / "config.json").read_text())
    assert cfg["dry_run"] is True and cfg["trading_mode"] == "spot"
    assert not cfg["exchange"].get("key") and not cfg["exchange"].get("secret")
    assert EIO.guard_config(cfg, tmp_path / "config.json") == []
    assert spec["fee"] == 0.0015
    cmd = EIO.command(spec)
    assert cmd[:6] == ["docker", "run", "--rm", "--network", "none", "-v"]
    assert "freqtradeorg/freqtrade:2026.7" in cmd and "backtesting" in cmd
    assert "--keep-trade-copy" not in cmd and "--keep-trade-copy" in EIO.command(spec, keep_trade_copy=True)


def _freqtrade_2026_7() -> bool:
    # the repository's own freqtrade/ directory is importable as a namespace package, so
    # ask for the installed distribution, not for an importable name
    from importlib import metadata

    try:
        return metadata.version("freqtrade") == "2026.7"
    except metadata.PackageNotFoundError:
        return False


@pytest.mark.skipif(not _freqtrade_2026_7(), reason="freqtrade 2026.7 is not installed here; CI runs "
                    "research/auth2/engine_selftest.py inside the pinned image instead")
def test_skipping_the_trade_copy_changes_no_result(tmp_path):
    import sys

    from auth2 import engine_selftest as ES

    res = ES.one("A3", sys.executable, tmp_path)
    assert res["status"] == "PASS", res
