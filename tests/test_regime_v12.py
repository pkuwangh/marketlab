from dataclasses import asdict, replace
from datetime import timedelta

import pytest
from test_regime_lifecycle import DAY, inputs, price

from marketlab.regime import _vvix_vs_vix_feature
from marketlab.regime_lifecycle import (
    DEFAULT_CONFIG,
    _causes_repaired,
    _reopen_after_new_low,
    maximum_evidence,
    transition,
)


@pytest.mark.parametrize("original,expected", [(None, False), ((0.4, 0), False), ((0.1, 0), True)])
def test_causal_repair_requires_original_leaf_not_unused_missing_alternative(original, expected):
    evidence = {"credit": maximum_evidence({"hyg_tlt": original, "oas": None})}
    assert _causes_repaired(evidence, {"credit": ["hyg_tlt"]}, 0.35) is expected


def test_repair_does_not_follow_a_different_family_maximum():
    evidence = {"volatility": maximum_evidence({"vix": (0.1, 0), "vvix": (0.8, 0)})}
    assert _causes_repaired(evidence, {"volatility": ["vix"]}, 0.35)
    assert not _causes_repaired(evidence, {"volatility": ["vvix"]}, 0.35)


def test_new_joint_damage_blocks_otherwise_repaired_protection():
    state = {
        "config": asdict(DEFAULT_CONFIG),
        "index": 0,
        "held": {
            "posture": "protected",
            "action": "protect-extension",
            "episode": "test",
            "index": 0,
            "date": str(DAY),
            "families": ["credit"],
            "causal_leaves": {"credit": ["hyg_tlt"]},
            "lows": {"SPY": 100, "QQQ": 100},
        },
    }
    for i in range(1, 7):
        day = DAY + timedelta(days=i)
        snap, signals = inputs(day, stress=0.3, move=0.01, vol=0.2 if i <= 3 else 0, ma50=0.01)
        snap = replace(snap, spy_return_20d=-0.08, qqq_return_20d=-0.10)
        signals = tuple(s for s in signals if s.name != "credit_spread")
        action, _, _ = transition(
            snapshot=snap,
            signals=signals,
            histories={s: [price(day, 100, s)] for s in ("SPY", "QQQ")},
            previous=state,
        )
        state = action.lifecycle
        assert not state["evidence"]["credit"]["exact"]
        if i <= 3:
            assert state["held"]["recovery_streak"] == 0
    assert state["exit_reason"] == "protection_recovered"
    assert state["held"]["posture"] == "neutral"


@pytest.mark.parametrize("move,expected", [(0.01, "no_change"), (-0.04, "protect-break")])
def test_break_needs_recent_selling_not_only_old_medium_term_losses(move, expected):
    state = None
    for i in range(3):
        day = DAY + timedelta(days=i)
        snap, signals = inputs(day, stress=0.3, move=move, vol=0.2)
        snap = replace(snap, spy_return_20d=-0.08, qqq_return_20d=-0.10)
        action, _, _ = transition(
            snapshot=snap,
            signals=signals,
            histories={s: [price(day, 90, s)] for s in ("SPY", "QQQ")},
            previous=state,
        )
        state = action.lifecycle
    assert action.state == expected


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
            "causal_leaves": {"trend": ["5d"]},
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
