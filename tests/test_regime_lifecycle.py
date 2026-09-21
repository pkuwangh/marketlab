import json
from dataclasses import asdict, replace
from datetime import date, timedelta

import pytest
from test_regime import _market_signal, _snapshot

from marketlab.prices import DailyPriceObservation
from marketlab.regime import PRESSURE_FEATURE_SPECS, RegimePressureFeature, _snapshot_with_action
from marketlab.regime_exposure import replay_exposure
from marketlab.regime_lifecycle import (
    ACTIONS,
    DEFAULT_CONFIG,
    Evidence,
    action_direction,
    confirmation_gate,
    funding_veto,
    maximum_evidence,
    owned_evidence,
    price_opportunity,
    second_family,
    setup_readings,
    transition,
    update_setup,
)

DAY = date(2026, 1, 2)


@pytest.mark.parametrize(
    "breadth,credit,expected_hit",
    [
        (0.8, None, 0.8),
        (None, 0.8, 0.8),
        (0.35, None, 0.8),
        (0.2, None, None),
        (None, 0.2, None),
        (None, None, None),
        (0.2, 0.3, 0.0),
        (0.8, 0.3, 0.8),
    ],
)
def test_transmission_gate_uses_observed_alternatives(breadth, credit, expected_hit):
    snapshot, _ = inputs()
    values = {
        "rsp_spy_relative_20d": breadth,
        "iwm_spy_relative_20d": breadth,
        "hyg_tlt_relative_20d": credit,
        "credit_spread": credit,
    }
    snapshot = replace(
        snapshot,
        pressure_features=tuple(
            replace(f, washout_score=values.get(f.name, f.washout_score))
            for f in snapshot.pressure_features
            if f.name not in values or values[f.name] is not None
        ),
    )
    config = replace(DEFAULT_CONFIG, transmission=True)
    stress, hit, _ = setup_readings(snapshot, config)
    assert stress == pytest.approx(0.8)
    assert hit == expected_hit
    assert setup_readings(snapshot, DEFAULT_CONFIG)[1] == pytest.approx(0.8)


def test_partial_credit_does_not_change_its_declared_average():
    snapshot, _ = inputs()
    snapshot = replace(
        snapshot,
        pressure_features=tuple(
            replace(f, washout_score=0.1)
            if f.name in ("rsp_spy_relative_20d", "iwm_spy_relative_20d")
            else f
            for f in snapshot.pressure_features
            if f.name != "credit_spread"
        ),
    )
    config = replace(DEFAULT_CONFIG, transmission=True)
    # HYG/TLT alone is not the core profile's fixed credit-pressure mean.
    assert setup_readings(snapshot, config)[1] is None
    assert setup_readings(snapshot, replace(config, input_profile="reduced"))[1] == 0.8


@pytest.mark.parametrize("missing", ["credit_spread", "rsp_spy_relative_20d"])
def test_partial_transmission_cannot_manufacture_tvx_release(missing):
    snapshot, _ = inputs()
    config = replace(DEFAULT_CONFIG, stress_geometry="tvx", transmission=True)
    kwargs = dict(
        prices={"SPY": 80}, anchors={"SPY": 100}, kind="washout", config=config
    )
    stress, hit, _ = setup_readings(snapshot, config)
    state = update_setup(None, day="2026-01-02", index=0, hit=hit, stress=stress, **kwargs)
    peak = state["peak"]
    assert state["armed"]
    partial = replace(
        snapshot,
        pressure_features=tuple(
            replace(f, washout_score=0.5) for f in snapshot.pressure_features if f.name != missing
        ),
    )
    stress, hit, _ = setup_readings(partial, config)
    assert stress is None and hit is None
    state = update_setup(state, day="2026-01-05", index=1, hit=hit, stress=stress, **kwargs)
    assert state["release"] is None
    assert state["peak"] == peak
    assert state["last_hit"] == 0
    assert state["armed"]
    # Restoring coverage with unchanged readings cannot turn missingness into release.
    stress, hit, _ = setup_readings(snapshot, config)
    state = update_setup(state, day="2026-01-06", index=2, hit=hit, stress=stress, **kwargs)
    assert state["release"] == 0


def test_action_report_keeps_zero_events_and_unavailable_horizons():
    from marketlab.regime import (
        RegimeActionForwardOutcome,
        format_regime_action_outcome_summary,
        summarize_regime_action_outcomes,
    )

    outcomes = tuple(
        RegimeActionForwardOutcome(
            source_date=DAY,
            price_date=DAY,
            action_state="no_change",
            stretch_score=0,
            washout_score=0,
            action_confidence="high",
            is_action_event=False,
            horizon_days=horizon,
            spy_return=None,
            qqq_return=None,
            spy_max_drawdown=None,
            qqq_max_drawdown=None,
            has_lifecycle=True,
        )
        for horizon in (20, 40, 65)
    )
    rows = summarize_regime_action_outcomes(outcomes)
    assert len(rows) == 15
    assert all(row.action_count == 0 for row in rows if row.bucket.startswith("event:"))
    table = format_regime_action_outcome_summary(rows)
    for action in ACTIONS:
        assert table.count(f"event:{action}") == 3
    assert "baseline:all_days" in table


def price(day, value, symbol="SPY", opening=None):
    return DailyPriceObservation(
        source="test",
        source_symbol=symbol,
        symbol=symbol,
        observed_date=day,
        open=opening or value,
        high=value,
        low=value,
        close=value,
        volume=100,
    )


def inputs(day=DAY, stress=0.8, move=-0.04, vol=0.2, ma50=-0.05, ma200=0.05):
    snapshot = _snapshot(
        source_date=day,
        regime="neutral",
        score=0,
        spy_return_20d=move,
        qqq_return_20d=move,
        spy_ma50_distance=ma50,
        qqq_ma50_distance=ma50,
        spy_ma200_distance=ma200,
        qqq_ma200_distance=ma200,
    )
    pressure = tuple(
        RegimePressureFeature(
            source_date=day,
            pressure_version="fixture",
            family=spec.family,
            name=spec.name,
            raw_value=1,
            percentile=0.9,
            normalized_score=stress,
            stretch_score=1 - stress,
            washout_score=stress,
            sample_count=252,
            reason="fixture",
        )
        for spec in PRESSURE_FEATURE_SPECS
    )
    snapshot = replace(snapshot, pressure_features=pressure)

    def signal(family, name, details=None, status="mixed"):
        return _market_signal(
            source_date=day,
            family=family,
            name=name,
            status=status,
            score=0,
            value=1,
            details=details or {},
        )

    signals = (
        signal(
            "trend",
            "price_proxy",
            {"spy_return_5d": move, "qqq_return_5d": move, "qqq_return_60d": 0.1},
        ),
        signal("volatility", "price_proxy", {"vix_return_5d": vol}),
        signal("volatility", "vol_of_vol", {"vvix_return_5d": vol}),
        signal(
            "volatility",
            "term_structure",
            {"vix9d_vix_ratio_change_5d": vol, "vix_vix3m_ratio_change_5d": vol},
        ),
        signal(
            "breadth", "price_proxy", {"rsp_spy_relative_5d": move, "iwm_spy_relative_5d": move}
        ),
        signal("credit", "price_proxy", {"hyg_tlt_relative_5d": move}),
        signal("credit", "credit_spread", {"credit_spread_change_5d": -move}),
        signal(
            "liquidity",
            "financial_conditions",
            {"financial_conditions_change_4w": 0},
            status="loose",
        ),
    )
    return snapshot, signals


def test_owned_maxima_are_monotone_duplicate_invariant_and_bounded():
    first = maximum_evidence({"vix": (0.8, 0.1), "vvix": None})
    assert first == Evidence(0.8, 0.1, False, ("vvix",))
    resolved = maximum_evidence({"vix": (0.8, 0.1), "vvix": (0.2, 0.3), "duplicate": (0.8, 0.1)})
    assert resolved.deterioration == 0.8
    assert second_family({"volatility": first}, "deterioration") == 0
    assert (
        second_family({"volatility": first, "credit": Evidence(0.9, 0, False)}, "deterioration")
        == 0.8
    )
    assert confirmation_gate([first], "deterioration", 0.75) is True
    assert confirmation_gate([first], "deterioration", 0.9) is None
    assert confirmation_gate([resolved], "deterioration", 0.9) is False
    assert confirmation_gate([first, Evidence(None, None, False)], "deterioration", 0.75, 2) is None
    assert confirmation_gate([first, Evidence(0.8, 0.0, False)], "deterioration", 0.75, 2) is True


@pytest.mark.parametrize(
    "left,right,expected",
    [
        (None, False, False),
        (None, True, None),
        (True, True, True),
        (False, None, False),
        (None, None, None),
    ],
)
def test_funding_three_valued(left, right, expected):
    assert funding_veto(left, right) is expected


def test_liquidity_cannot_create_a_credit_vote():
    snap, signals = inputs(move=0, vol=0)
    signals = tuple(
        replace(s, details={"financial_conditions_change_4w": 1}) if s.family == "liquidity" else s
        for s in signals
    )
    evidence, _, _, _ = owned_evidence(snap, signals)
    assert evidence["credit"].deterioration == 0
    assert evidence["liquidity"].deterioration == 1


def test_setup_identity_interrupted_hits_grace_and_no_fake_release():
    kwargs = dict(
        prices={"SPY": 80, "QQQ": 80},
        anchors={"SPY": 100, "QQQ": 100},
        kind="washout",
        config=DEFAULT_CONFIG,
    )
    state = update_setup(None, day="2026-01-02", index=0, hit=0.8, stress=0.8, **kwargs)
    identity = state["id"]
    state = update_setup(state, day="2026-01-05", index=1, hit=0, stress=0.799, **kwargs)
    assert state["release"] == pytest.approx(0.001)
    state = update_setup(state, day="2026-01-06", index=2, hit=0.7, stress=0.7, **kwargs)
    assert state["id"] == identity and state["last_hit"] == 2 and state["peak"] == 0.8
    state = update_setup(state, day="2026-02-01", index=17, hit=0, stress=0.2, **kwargs)
    assert state["armed"]
    state = update_setup(state, day="2026-02-02", index=18, hit=None, stress=None, **kwargs)
    assert not state["armed"] and state["release"] is None


def test_opportunity_uses_causal_prices_not_fear():
    episode = {"armed": True, "anchors": {"SPY": 100}, "lows": {"SPY": 80}}
    assert price_opportunity(episode, {"SPY": 90}, 0.5)
    assert not price_opportunity(episode, {"SPY": 91}, 0.5)


def test_break_action_persists_without_extension_and_does_not_reset_entry():
    state = None
    histories = {s: [] for s in ("SPY", "QQQ")}
    for i in range(5):
        day = DAY + timedelta(days=i)
        snap, signals = inputs(day, ma200=-0.1)
        for symbol in histories:
            histories[symbol].append(price(day, 100 - i, symbol))
        action, _, _ = transition(
            snapshot=snap, signals=signals, histories=histories, previous=state
        )
        state = json.loads(json.dumps(action.lifecycle))
        if i == 2:
            assert action.state == "protect-break"
            assert state["held"]["date"] == day.isoformat()
        elif i > 2:
            assert action.state == "no_change"
            assert state["held"]["age"] == i - 2
            assert "protect-break" in state["supporting"]
    assert not state["extension"]["armed"]


def test_conflicting_unused_paths_and_consumed_opposite_resolution(monkeypatch):
    from marketlab import regime_lifecycle as lifecycle

    original = lifecycle.owned_evidence

    def contradictory(*args):
        evidence, features, modules, returns = original(*args)
        evidence["volatility"] = Evidence(0.8, 0.8, True)
        evidence["breadth"] = Evidence(0.0, 0.8, True)
        return evidence, features, modules, returns

    monkeypatch.setattr(lifecycle, "owned_evidence", contradictory)
    histories = {s: [price(DAY - timedelta(days=1), 100, s)] for s in ("SPY", "QQQ")}
    state = None
    for i in range(3):
        day = DAY + timedelta(days=i)
        snap, signals = inputs(day, stress=0.9 if i < 2 else 0.5, ma200=-0.1)
        for symbol in histories:
            histories[symbol].append(price(day, 80 if i < 2 else 84, symbol))
        prior = state
        action, _, _ = transition(
            snapshot=snap, signals=signals, histories=histories, previous=prior
        )
        state = action.lifecycle
    assert set(state["raw_candidates"]) == {"protect-break", "redeploy-washout"}
    assert state["conflict"] and action.state == "no_change"
    assert state["held"]["posture"] == "neutral"

    # A used washout cannot veto a genuine opposite protection entry or renew the old holding.
    prior["washout"]["consumed"] = True
    prior["held"] = {
        "posture": "redeploying",
        "action": "redeploy-washout",
        "episode": prior["washout"]["id"],
        "date": DAY.isoformat(),
        "index": 0,
        "families": ["volatility", "breadth"],
        "age": 1,
    }
    action, _, _ = transition(snapshot=snap, signals=signals, histories=histories, previous=prior)
    assert action.state == "protect-break"
    assert not action.lifecycle["conflict"]
    assert action.lifecycle["exit_reason"] == "opposite_action"
    assert action.lifecycle["closed_holding"]["episode"] == prior["washout"]["id"]
    assert action.lifecycle["held"]["age"] == 0


def test_washout_entry_and_failure_are_reachable_before_cap():
    histories = {s: [price(DAY - timedelta(days=1), 100, s)] for s in ("SPY", "QQQ")}
    state = None
    actions = []
    for i, (level, stress, move, vol) in enumerate(
        [
            (80, 0.9, -0.04, 0.2),
            (84, 0.5, 0.04, -0.2),
            (79, 0.8, -0.04, 0.2),
        ]
    ):
        day = DAY + timedelta(days=i)
        snap, signals = inputs(day, stress=stress, move=move, vol=vol)
        for symbol in histories:
            histories[symbol].append(price(day, level, symbol))
        action, _, _ = transition(
            snapshot=snap, signals=signals, histories=histories, previous=state
        )
        state = json.loads(json.dumps(action.lifecycle))
        actions.append(action)
    assert actions[1].state == "redeploy-washout"
    assert actions[2].lifecycle["exit_reason"] == "thesis_failed"
    assert actions[2].lifecycle["held"]["posture"] == "neutral"
    assert actions[2].lifecycle["washout"]["consumed"]
    assert actions[0].lifecycle["washout"]["id"] == state["washout"]["id"]


def test_unknown_action_and_midchain_configuration_change_fail():
    with pytest.raises(ValueError, match="Unknown"):
        action_direction("unexpected")
    snap, signals = inputs()
    with pytest.raises(ValueError, match="configuration changed"):
        transition(snapshot=snap, signals=signals, histories={}, previous={"config": {}})
    assert [action_direction(a) for a in ACTIONS] == ["protected"] * 2 + ["redeploying"] * 2


def test_protection_recovery_needs_exact_causal_evidence():
    snap, signals = inputs(stress=0.2, move=0.01, vol=0, ma50=0.01)
    state = {
        "config": asdict(DEFAULT_CONFIG),
        "index": 0,
        "held": {
            "posture": "protected",
            "action": "protect-extension",
            "date": str(DAY),
            "index": 0,
            "families": ["credit"],
            "episode": "test",
        },
    }
    for i in range(1, 5):
        day = DAY + timedelta(days=i)
        absent = tuple(s for s in signals if s.name != "credit_spread")
        action, _, _ = transition(
            snapshot=replace(snap, source_date=day),
            signals=absent,
            histories={s: [price(day, 100, s)] for s in ("SPY", "QQQ")},
            previous=state,
        )
        state = action.lifecycle
    assert state["held"]["posture"] == "protected"
    for i in range(5, 8):
        day = DAY + timedelta(days=i)
        action, _, _ = transition(
            snapshot=replace(snap, source_date=day),
            signals=signals,
            histories={s: [price(day, 100, s)] for s in ("SPY", "QQQ")},
            previous=state,
        )
        state = action.lifecycle
    assert state["held"]["posture"] == "neutral"
    assert state["exit_reason"] == "protection_recovered"


def test_next_open_accounting_keeps_overnight_loss_and_slice_parity():
    snapshots = []
    histories = {s: [] for s in ("SPY", "QQQ")}
    for i in range(4):
        day = DAY + timedelta(days=i)
        snap, _ = inputs(day)
        snapshots.append(
            replace(snap, lifecycle={"held": {"posture": "protected"}}, action_state="no_change")
        )
        for symbol in histories:
            histories[symbol].append(price(day, 100 if i == 0 else 90, symbol))
    kwargs = dict(
        snapshots=snapshots,
        histories=histories,
        end_date=DAY + timedelta(days=3),
        cost_rate=0,
        financing_rate=0,
    )
    full = replay_exposure(**kwargs, start_date=DAY)
    assert full[0].net_return == pytest.approx(-0.1)  # Not -.08: old exposure owns the gap.
    sliced = replay_exposure(**kwargs, start_date=DAY + timedelta(days=2))
    assert sliced == full[1:]


def test_state_serialization_is_lossless():
    snap, signals = inputs()
    action, _, _ = transition(
        snapshot=snap, signals=signals, histories={s: [price(DAY, 100, s)] for s in ("SPY", "QQQ")}
    )
    saved = _snapshot_with_action(snapshot=snap, action=action)
    assert json.loads(json.dumps(saved.lifecycle)) == saved.lifecycle


def test_recent_report_distinguishes_no_new_action_from_held_protection():
    from marketlab.regime import format_regime_recent_report

    snap, _ = inputs()
    snap = replace(snap, action_state="no_change", lifecycle={"held": {"posture": "protected"}})
    report = format_regime_recent_report(source_date=DAY, lookback_days=1, snapshots=(snap,))
    assert "held_posture" in report and "protected" in report
    assert "no_change" in report and "maintain" not in report


def test_orderly_pullback_is_a_real_second_path_and_overlap_is_consumed():
    for panic in (False, True):
        state = None
        histories = {s: [] for s in ("SPY", "QQQ")}
        for i, (level, move, vol, ma50) in enumerate(
            [
                (100, 0.04, 0, 0.02),
                (80, -0.04, 0.2, -0.04),
                (84, 0.04, -0.2, -0.01),
            ]
        ):
            day = DAY + timedelta(days=i)
            stress = 0.9 if panic and i == 1 else 0.3
            snap, signals = inputs(day, stress=stress, move=move, vol=vol, ma50=ma50)
            for symbol in histories:
                histories[symbol].append(price(day, level, symbol))
            action, _, _ = transition(
                snapshot=snap, signals=signals, histories=histories, previous=state
            )
            state = action.lifecycle
        assert action.state == ("redeploy-washout" if panic else "redeploy-confirm")
        assert state["pullback"]["consumed"]
        if panic:
            assert state["washout"]["consumed"]
            assert "redeploy-confirm" in state["raw_candidates"]


def test_extension_divergence_precedes_damage_and_survives_context_switch():
    state = None
    histories = {s: [] for s in ("SPY", "QQQ")}
    for i in range(2):
        day = DAY + timedelta(days=i)
        snap, signals = inputs(day, stress=0.1, move=0.04 if i == 0 else -0.04, vol=0.2, ma50=0.02)
        if i == 0:
            signals = tuple(
                replace(s, details={"rsp_spy_relative_5d": -0.04, "iwm_spy_relative_5d": -0.04})
                if s.family == "breadth"
                else s
                for s in signals
            )
        for symbol in histories:
            histories[symbol].append(price(day, 100 - i, symbol))
        action, _, _ = transition(
            snapshot=snap, signals=signals, histories=histories, previous=state
        )
        state = action.lifecycle
        if i == 0:
            assert action.state == "no_change"
    assert action.state == "protect-extension"
    assert state["held"]["families"] == ["trend", "volatility", "breadth"]


def test_cap_does_not_allow_consumed_setup_to_reenter():
    histories = {s: [price(DAY - timedelta(days=1), 100, s)] for s in ("SPY", "QQQ")}
    state = None
    config = replace(DEFAULT_CONFIG, redeploy_cap=2)
    for i in range(5):
        day = DAY + timedelta(days=i)
        snap, signals = inputs(
            day,
            stress=0.9 if i == 0 else 0.5,
            move=-0.04 if i == 0 else 0.04,
            vol=0.2 if i == 0 else -0.2,
        )
        for symbol in histories:
            histories[symbol].append(price(day, 80 if i == 0 else 84, symbol))
        action, _, _ = transition(
            snapshot=snap, signals=signals, histories=histories, previous=state, config=config
        )
        state = action.lifecycle
        if i == 1:
            assert action.state == "redeploy-washout"
        if i == 3:
            assert state["exit_reason"] == "holding_expired"
        if i >= 3:
            assert state["held"]["posture"] == "neutral"
            assert action.state == "no_change"


def test_extension_does_not_rearm_a_continuous_run_after_fixed_expiry():
    state = None
    for i in range(44):
        state = update_setup(
            state,
            day=str(DAY + timedelta(days=i)),
            index=i,
            hit=0.8,
            stress=0.8,
            prices={"SPY": 100},
            anchors={"SPY": 100},
            kind="extension",
            config=DEFAULT_CONFIG,
        )
    assert not state["armed"]
    assert state["index"] == 0


def test_costs_financing_and_missing_execution_are_not_hidden():
    snapshots = []
    histories = {s: [] for s in ("SPY", "QQQ")}
    for i in range(3):
        day = DAY + timedelta(days=i)
        snap, _ = inputs(day)
        snapshots.append(
            replace(snap, lifecycle={"held": {"posture": "redeploying"}}, action_state="no_change")
        )
        for symbol in histories:
            histories[symbol].append(price(day, 100, symbol))
    kwargs = dict(
        snapshots=snapshots, histories=histories, start_date=DAY, end_date=DAY + timedelta(days=2)
    )
    rows = replay_exposure(**kwargs)
    assert rows[0].cost == pytest.approx(0.0005 * rows[0].turnover)
    assert rows[0].net_return < 0 and rows[0].gross_return == 0
    assert rows[1].financing > 0
    histories["QQQ"][-1] = replace(histories["QQQ"][-1], open=0)
    with pytest.raises(ValueError, match="no close substitution"):
        replay_exposure(**kwargs)


def test_observations_recompute_setup_entry_and_failure_before_cap(tmp_path):
    import math

    from marketlab import regime as r
    from marketlab.market_series import MarketSeriesObservation, write_market_series_observations
    from marketlab.prices import write_price_observations

    start = date(2024, 1, 1)
    base = [100 * (1.0005**i) * (1 + 0.015 * math.sin(i / 7)) for i in range(320)]
    levels = base.copy()
    for step in [-0.025] * 10 + [0.015] * 6 + [-0.035] * 5:
        levels.append(levels[-1] * (1 + step))
    volatility = [16 + 2 * math.sin(i / 9) for i in range(320)]
    volatility += (
        [20 + i * 2 for i in range(10)]
        + [35 - i * 2 for i in range(6)]
        + [32 + i * 3 for i in range(5)]
    )
    price_root, series_root = tmp_path / "prices", tmp_path / "series"
    for symbol in r.DEFAULT_REGIME_PRICE_SYMBOLS:
        values = levels
        if symbol.startswith("^"):
            scale = {"^VIX": 1, "^VVIX": 5, "^VIX9D": 1, "^VIX3M": 1.1}[symbol]
            values = [v * scale for v in volatility]
        if symbol.startswith("$"):
            values = [50.0] * len(levels)
        write_price_observations(
            tuple(price(start + timedelta(days=i), v, symbol) for i, v in enumerate(values)),
            output_root=price_root,
        )
    write_market_series_observations(
        tuple(
            MarketSeriesObservation(
                source="fixture",
                source_series_id="NFCI",
                series_id="NFCI",
                observed_date=start + timedelta(days=i),
                availability_date=start + timedelta(days=i),
                value=-0.5,
                unit="index",
            )
            for i in range(len(levels))
        ),
        output_root=series_root,
    )
    result = r.compute_regime_backfill(
        start_date=start + timedelta(days=319),
        end_date=start + timedelta(days=len(levels) - 1),
        price_root=price_root,
        market_series_root=series_root,
        snapshot_root=tmp_path / "snapshots",
        signal_snapshot_root=tmp_path / "signals",
    )
    rows = [
        r.load_regime_snapshot(source_date=d, snapshot_root=tmp_path / "snapshots")
        for d in result.source_dates
    ]
    entries = [row for row in rows if row.action_state == "redeploy-washout"]
    failures = [row for row in rows if row.lifecycle["exit_reason"] == "thesis_failed"]
    assert entries and failures
    assert failures[0].lifecycle["closed_holding"]["age"] < DEFAULT_CONFIG.redeploy_cap
    resumed = r.compute_regime_snapshot(
        source_date=rows[-1].source_date,
        price_root=price_root,
        market_series_root=series_root,
        snapshot_root=tmp_path / "snapshots",
        signal_snapshot_root=tmp_path / "signals",
        write_snapshot=False,
        require_action_history=True,
    )
    assert resumed.snapshot == rows[-1]
    from marketlab.regime_export import _rows_for_snapshots

    columns = (
        "date",
        "extension_armed_since",
        "washout_armed_since",
        "washout_peak_stress",
        "washout_last_hit_session",
        "held_episode",
        "posture_state",
        "posture_age",
    )
    exported = _rows_for_snapshots(tuple(rows), price_root=price_root, headers=columns)
    sliced = _rows_for_snapshots(tuple(rows[-5:]), price_root=price_root, headers=columns)
    assert exported[-5:] == sliced
    with pytest.raises(r.RegimeError, match="Missing intermediate"):
        r._compute_regime_snapshot_from_histories(
            source_date=rows[-1].source_date,
            histories=r._load_histories(
                symbols=r.DEFAULT_REGIME_PRICE_SYMBOLS, price_root=price_root
            ),
            market_series_histories={},
            snapshot_root=tmp_path / "snapshots",
            signal_snapshot_root=tmp_path / "signals",
            signal_time="eod",
            snapshot_version=None,
            write_snapshot=False,
            overwrite_snapshot=True,
            prior_snapshots=(rows[-3],),
        )


def test_policy_uses_independent_pillar_versions_and_held_posture(tmp_path):
    from test_policy import _candidate, _regime_snapshot

    from marketlab.bulltard.validation import write_candidate_validation_snapshots
    from marketlab.policy import PortfolioPolicyError, compute_portfolio_policy_snapshot
    from marketlab.regime import write_regime_snapshot

    for version, posture in (("v1.0", "neutral"), ("v1.1", "protected")):
        write_regime_snapshot(
            replace(
                _regime_snapshot(source_date=DAY, snapshot_version=version),
                lifecycle={"held": {"posture": posture}},
            ),
            snapshot_root=tmp_path / "regime",
        )
    write_candidate_validation_snapshots(
        (_candidate(source_date=DAY, symbol="SPY", validation_status="watch"),),
        snapshot_root=tmp_path / "candidates",
        source_date=DAY,
    )
    kwargs = dict(
        source_date=DAY,
        regime_snapshot_root=tmp_path / "regime",
        candidate_snapshot_root=tmp_path / "candidates",
        write_snapshot=False,
    )
    default = compute_portfolio_policy_snapshot(**kwargs).snapshot
    explicit = compute_portfolio_policy_snapshot(
        **kwargs,
        regime_snapshot_version="v1.0",
        candidate_snapshot_version="v0.0",
        snapshot_version="v0.1",
    ).snapshot
    assert default.policy_state == "protect"  # no_change does not mean reset to neutral.
    assert default.marginal_beta_target == 0.8
    assert explicit.policy_state == "maintain"
    assert default.regime_snapshot_version == "v1.1"
    assert explicit.regime_snapshot_version == "v1.0"
    assert explicit.candidate_snapshot_version == "v0.0"
    assert explicit.snapshot_version == "v0.1"
    with pytest.raises(PortfolioPolicyError, match="current policy version"):
        compute_portfolio_policy_snapshot(**kwargs, snapshot_version="v0.0")
