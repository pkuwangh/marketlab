import json
from dataclasses import replace
from datetime import timedelta

import pytest
from test_regime_lifecycle import DAY, inputs, price

from marketlab.regime_lifecycle import DEFAULT_CONFIG, transition


def step(state, index, *, ma50=-0.02, qqq_ma50=-0.02, selling=True, config=DEFAULT_CONFIG):
    day = DAY + timedelta(days=index * 2)
    snapshot, signals = inputs(
        day,
        stress=0.5,
        ma50=ma50,
        move=-0.04 if selling else 0,
        vol=0.2 if selling else 0,
    )
    snapshot = replace(
        snapshot, qqq_ma50_distance=qqq_ma50, spy_return_20d=0.02, qqq_return_20d=0.02
    )
    action, _, _ = transition(
        snapshot=snapshot,
        signals=signals,
        histories={s: [price(day, 100 - index, s)] for s in ("SPY", "QQQ")},
        previous=state,
        config=config,
    )
    return action, json.loads(json.dumps(action.lifecycle))


def repaired(config=DEFAULT_CONFIG):
    state = None
    for i in range(3):
        action, state = step(state, i, ma50=0.02, qqq_ma50=0.02, selling=False, config=config)
        assert action.state == "no_change"
        assert state["break"].get("ready", False) is (i == 2)
    return state


def test_break_can_confirm_first_support_loss_without_negative_20d_returns():
    action, state = step(repaired(), 3)
    assert action.state == "protect-break"
    assert state["break"]["age"] == 0
    assert state["break"]["entry_count"] == 1


def test_sequential_support_loss_keeps_original_watch_clock():
    action, state = step(repaired(), 3, qqq_ma50=0.02)
    assert action.state == "no_change"
    assert state["break"]["armed"]
    episode = state["break"]["id"]
    action, state = step(state, 4)
    assert action.state == "protect-break"
    assert state["break"]["id"] == episode
    assert state["break"]["age"] == 1


@pytest.mark.parametrize("window", [3, 5])
def test_watch_uses_snapshot_sessions_and_continued_selling_cannot_refresh_it(window):
    config = replace(DEFAULT_CONFIG, break_watch_sessions=window)
    state = repaired(config)
    for i in range(3, 3 + window):
        action, state = step(state, i, selling=False, config=config)
        assert state["break"]["armed"]
        assert action.state == "no_change"
    episode = state["break"]["id"]
    for i in range(3 + window, 8 + window):
        action, state = step(state, i, config=config)
        assert not state["break"]["armed"]
        assert state["break"]["id"] == episode
        assert action.state == "no_change"


def test_new_lows_after_exit_do_not_retry_break_and_real_repair_allows_new_episode():
    config = replace(DEFAULT_CONFIG, protect_cap=1)
    state = repaired(config)
    action, state = step(state, 3, config=config)
    first = state["break"]["id"]
    assert action.state == "protect-break"
    _, state = step(state, 4, config=config)
    assert state["exit_reason"] == "holding_expired"
    for i in (5, 6):
        action, state = step(state, i, config=config)
        assert action.state == "no_change"
        assert state["break"]["consumed"]
    for i in (7, 8):
        _, state = step(state, i, ma50=0.02, qqq_ma50=0.02, selling=False, config=config)
    action, state = step(state, 9, config=config)
    assert action.state == "no_change"
    assert state["break"]["id"] == first
    for i in (10, 11, 12):
        _, state = step(state, i, ma50=0.02, qqq_ma50=0.02, selling=False, config=config)
    action, state = step(state, 13, config=config)
    assert action.state == "protect-break"
    assert state["break"]["id"] != first
    assert state["break"]["entry_count"] == 1


def test_already_broken_bootstrap_is_not_a_new_support_loss():
    state = None
    for i in range(10):
        action, state = step(state, i)
        assert action.state == "no_change"
        assert not state["break"].get("armed")


def test_unknown_support_cannot_confirm_or_establish_repair():
    action, state = step(repaired(), 3, qqq_ma50=None)
    assert action.state == "no_change"
    assert state["gates"]["protect-break"]["current_damage"] is None
    for i in range(4, 8):
        _, state = step(state, i, ma50=0.02, qqq_ma50=None, selling=False)
        assert not state["break"].get("ready")
