from dataclasses import asdict, replace
from datetime import timedelta

import pytest
from test_regime_lifecycle import DAY, inputs, price

from marketlab.regime import _vvix_vs_vix_feature
from marketlab.regime_lifecycle import DEFAULT_CONFIG, _reopen_after_new_low, transition


def test_retry_remembers_intervening_low_without_moving_entry_thesis():
    config = replace(DEFAULT_CONFIG, protect_cap=3)
    state = {
        "config": asdict(config),
        "index": 0,
        "break": {"id": "test", "armed": True, "consumed": True, "entry_count": 1},
        "held": {
            "posture": "protected",
            "action": "protect-break",
            "episode": "test",
            "index": 0,
            "date": str(DAY),
            "families": ["trend"],
            "lows": {"SPY": 100, "QQQ": 100},
        },
    }
    for i, level in enumerate((90, 85, 88), 1):
        day = DAY + timedelta(days=i)
        snap, signals = inputs(day, stress=0.2)
        action, _, _ = transition(
            snapshot=snap,
            signals=signals,
            histories={s: [price(day, level, s)] for s in ("SPY", "QQQ")},
            previous=state,
            config=config,
        )
        state = action.lifecycle
    assert state["exit_reason"] == "holding_expired"
    assert state["closed_holding"]["lows"] == {"SPY": 100, "QQQ": 100}
    assert state["break"]["retry_lows"] == {"SPY": 85, "QQQ": 85}
    _reopen_after_new_low(
        state["break"], {"SPY": 87, "QQQ": 87}, allowed=True, day="later", config=config
    )
    assert state["break"]["consumed"]


@pytest.mark.parametrize(
    "prices,allowed,count,reopens",
    [
        ({"SPY": 79, "QQQ": 79}, True, 1, True),
        ({"SPY": 79, "QQQ": 81}, True, 1, False),
        ({"SPY": 79, "QQQ": 79}, False, 1, False),
        ({"SPY": 79, "QQQ": 79}, True, 2, False),
    ],
)
def test_episode_retry_needs_new_joint_low_and_remaining_budget(prices, allowed, count, reopens):
    episode = {
        "id": "washout:old",
        "armed": True,
        "consumed": True,
        "entry_count": count,
        "retry_lows": {"SPY": 80, "QQQ": 80},
        "index": 0,
    }
    _reopen_after_new_low(episode, prices, allowed=allowed, day="new", config=DEFAULT_CONFIG)
    assert episode["consumed"] is not reopens
    assert episode["index"] == 0
    assert episode["id"] == "washout:old"
    assert episode["entry_count"] == count


@pytest.mark.parametrize(
    "vix_move,vvix_move,expected",
    [(-0.46, -0.30, 0), (-0.15, 0, 0), (-0.05, 0.12, 1), (0.05, 0.17, 1)],
)
def test_relative_volatility_deterioration_requires_actual_vvix_rise(vix_move, vvix_move, expected):
    snap, signals = inputs()
    snap = replace(snap, vix_close=32)
    signals = tuple(
        replace(s, details={"vix_return_5d": vix_move})
        if s.family == "volatility" and s.name == "price_proxy"
        else replace(s, details={"vvix_return_5d": vvix_move})
        if s.family == "volatility" and s.name == "vol_of_vol"
        else s
        for s in signals
    )
    feature = _vvix_vs_vix_feature(snapshot=snap, signals=signals)
    assert feature.deterioration_score == pytest.approx(expected)
    if vvix_move < 0:
        assert feature.stabilization_score > 0
