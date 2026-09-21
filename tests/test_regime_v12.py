import json
from dataclasses import asdict, replace
from datetime import timedelta

import pytest
from test_regime_lifecycle import DAY, inputs, price

from marketlab.regime import _vvix_vs_vix_feature
from marketlab.regime_lifecycle import (
    DEFAULT_CONFIG,
    _any_gates,
    _causes_repaired,
    _reopen_after_new_low,
    maximum_evidence,
    transition,
    update_setup,
)


@pytest.mark.parametrize(
    "values,expected", [((False, None), None), ((True, None), True), ((False, False), False)]
)
def test_alternative_confirmation_preserves_unknown(values, expected):
    assert _any_gates(*values) is expected


@pytest.mark.parametrize(
    "prior_credit,current_credit,expected",
    [
        (True, True, "protect-extension"),
        (False, True, "no_change"),
        (True, False, "no_change"),
    ],
)
def test_internal_extension_confirmation_needs_two_prior_and_current_families(
    prior_credit, current_credit, expected
):
    state = None
    histories = {s: [] for s in ("SPY", "QQQ")}
    for i in range(2):
        day = DAY + timedelta(days=i)
        snap, signals = inputs(day, stress=0.1, move=0.01, vol=0.2, ma50=0.02)
        credit = prior_credit if i == 0 else current_credit
        signals = tuple(
            replace(s, details={"rsp_spy_relative_5d": -0.04, "iwm_spy_relative_5d": -0.04})
            if s.family == "breadth"
            else replace(s, details={"hyg_tlt_relative_5d": -0.04 if credit else 0.04})
            if s.name == "price_proxy" and s.family == "credit"
            else s
            for s in signals
        )
        for symbol in histories:
            histories[symbol].append(price(day, 100 + i, symbol))
        action, _, _ = transition(
            snapshot=snap, signals=signals, histories=histories, previous=state
        )
        state = action.lifecycle
        if i == 0:
            assert action.state == "no_change"
    assert action.state == expected
    if expected != "no_change":
        assert state["held"]["families"] == ["volatility", "breadth", "credit"]


@pytest.mark.parametrize("missing_original", [False, True])
def test_extension_divergence_repairs_original_credit_without_unrelated_oas(missing_original):
    state = None
    histories = {s: [] for s in ("SPY", "QQQ")}
    for i in range(5):
        day = DAY + timedelta(days=i)
        snap, signals = inputs(
            day,
            stress=0.1 if i < 4 else 0.5,
            move=0.04 if i < 4 else -0.04,
            vol=0 if i < 4 else 0.2,
        )
        signals = tuple(
            replace(s, details={"hyg_tlt_relative_5d": -0.04 if i == 0 else 0.04})
            if s.family == "credit"
            else s
            for s in signals
            if s.name != "credit_spread"
            and not (missing_original and 1 <= i <= 3 and s.family == "credit")
        )
        for symbol in histories:
            histories[symbol].append(price(day, 100 + i if i < 4 else 99, symbol))
        action, _, _ = transition(
            snapshot=snap, signals=signals, histories=histories, previous=state
        )
        state = action.lifecycle
    assert state["gates"]["protect-extension"]["divergence"] is missing_original
    assert ("index" in state["divergence"]["credit"]) is missing_original


def test_new_washout_episode_clears_old_retry_metadata():
    kwargs = dict(prices={"SPY": 80}, anchors={"SPY": 100}, kind="washout", config=DEFAULT_CONFIG)
    old = update_setup(None, day="old", index=0, hit=0.9, stress=0.9, **kwargs)
    old.update(retry_date="old-retry", entry_count=2, consumed=True, retry_lows={"SPY": 70})
    new = update_setup(old, day="new", index=16, hit=0.9, stress=0.9, **kwargs)
    assert new["id"] == "washout:new"
    assert "retry_date" not in new
    assert new["entry_count"] == 0
    assert not new["consumed"]
    assert new["retry_lows"] is None


def test_two_washout_attempts_share_setup_but_keep_separate_holding_clocks():
    config = replace(DEFAULT_CONFIG, redeploy_cap=1, break_path=False)
    histories = {s: [price(DAY - timedelta(days=1), 100, s)] for s in ("SPY", "QQQ")}
    state, entries, ids = None, [], []
    for i, (level, stressed) in enumerate(
        (
            (80, True),
            (84, False),
            (84, False),
            (79, True),
            (82, False),
            (82, False),
            (78, True),
            (81, False),
        )
    ):
        day = DAY + timedelta(days=i)
        snap, signals = inputs(
            day,
            stress=0.9 if stressed else 0.5,
            move=-0.04 if stressed else 0.04,
            vol=0.2 if stressed else -0.2,
        )
        for symbol in histories:
            histories[symbol].append(price(day, level, symbol))
        action, _, _ = transition(
            snapshot=snap, signals=signals, histories=histories, previous=state, config=config
        )
        state = json.loads(json.dumps(action.lifecycle))
        ids.append(state["washout"]["id"])
        if action.state == "redeploy-washout":
            entries.append(i)
            assert state["held"]["age"] == 0
            assert state["held"]["date"] == str(day)
    assert entries == [1, 4]
    assert len(set(ids)) == 1
    assert state["washout"]["entry_count"] == 2
    assert state["washout"]["consumed"]
    assert state["held"]["posture"] == "neutral"


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
