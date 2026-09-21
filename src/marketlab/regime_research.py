"""Fixed v1.1 comparisons over canonical observations, outside the daily command surface."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

from marketlab import regime as r
from marketlab.regime_exposure import holding_outcomes, replay_exposure, summarize_exposure
from marketlab.regime_lifecycle import ACTIONS, DEFAULT_CONFIG, ActionConfig, transition


def comparison_configs(input_profile="reduced"):
    a = ActionConfig(
        name="R2-A",
        input_profile=input_profile,
        stress_geometry="tvx",
        transmission=True,
        opportunity=False,
        sequence=False,
        decay_gate=True,
        phase_veto=True,
        confirm_path=False,
        break_path=False,
    )
    b = replace(a, name="R2-B", stress_geometry="tv")
    c = replace(b, name="R2-C", transmission=False)
    w = replace(c, name="W-opportunity", opportunity=True)
    sequence = replace(w, name="P-sequence", sequence=True)
    decay = replace(sequence, name="P-decay", decay_gate=False)
    resolver = replace(decay, name="P-resolution", phase_veto=False)
    return (
        a,
        b,
        c,
        w,
        sequence,
        decay,
        resolver,
        replace(resolver, name="R-confirm", confirm_path=True),
        replace(resolver, name="P-break", break_path=True),
        replace(DEFAULT_CONFIG, input_profile=input_profile),
    )


def compare(
    *,
    start_date: date,
    end_date: date,
    output_root=Path("data/research/regime/v1.1"),
    input_profile="reduced",
):
    """Run predeclared comparisons; every variant owns its complete state trajectory."""
    if output_root.resolve().is_relative_to(Path("data/snapshots").resolve()):
        raise ValueError("Research variants cannot write canonical snapshots")
    histories = r._load_histories(
        symbols=r.DEFAULT_REGIME_PRICE_SYMBOLS, price_root=r.DEFAULT_PRICE_OBSERVATIONS_ROOT
    )
    series = r._load_market_series_histories(
        series_ids=r.DEFAULT_FRED_MARKET_SERIES_IDS,
        observations_root=r.DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT,
    )
    feature_history = r._pressure_feature_history_from_observations(
        source_date=end_date, histories=histories, market_series_histories=series
    )
    dates = r._regime_backfill_source_dates(
        start_date=start_date, end_date=end_date, histories=histories
    )
    configs = comparison_configs(input_profile)
    variants = {c.name: [] for c in configs}
    baseline = []
    for index, day in enumerate(dates):
        base = r._compute_regime_snapshot_from_histories(
            source_date=day,
            histories=histories,
            market_series_histories=series,
            snapshot_root=output_root,
            signal_snapshot_root=output_root,
            signal_time="eod",
            snapshot_version=None,
            write_snapshot=False,
            overwrite_snapshot=True,
            pressure_feature_history=feature_history,
            prior_snapshots=tuple(baseline[-1:]),
        )
        baseline.append(base.snapshot)
        for config in configs:
            rows = variants[config.name]
            action, wash, extension = transition(
                snapshot=base.snapshot,
                signals=base.signals,
                histories=histories,
                previous=rows[-1].lifecycle if rows else None,
                config=config,
            )
            rows.append(
                r._snapshot_with_action(
                    snapshot=replace(
                        base.snapshot, washout_setup_score=wash, extension_setup_score=extension
                    ),
                    action=action,
                )
            )
        if index % 250 == 0:
            print(f"research_sessions={index + 1}/{len(dates)} date={day}", flush=True)
    records = {}
    for config in configs:
        rows = variants[config.name]
        root = output_root / input_profile / config.name
        root.mkdir(parents=True, exist_ok=True)
        with (root / "daily.jsonl").open("w") as handle:
            for row in rows:
                handle.write(
                    json.dumps(
                        {
                            "date": row.source_date.isoformat(),
                            "action": row.action_state,
                            "state": row.lifecycle,
                        }
                    )
                    + "\n"
                )
        cohorts = {}
        for label, start, end in (
            ("full", start_date, end_date),
            ("2022", date(2022, 1, 1), date(2022, 12, 31)),
            ("post2020", date(2021, 1, 1), end_date),
        ):
            start, end = max(start, start_date), min(end, end_date)
            if start > end:
                continue
            daily = replay_exposure(
                snapshots=rows, histories=histories, start_date=start, end_date=end
            )
            active = summarize_exposure(daily)
            controls = {}
            for name, weight in (("untimed", 1.0), ("matched", active["average_exposure"] or 1.0)):
                controls[name] = summarize_exposure(
                    replay_exposure(
                        snapshots=rows,
                        histories=histories,
                        start_date=start,
                        end_date=end,
                        constant_exposure=weight,
                    )
                )
            counts = Counter(row.action_state for row in rows if start <= row.source_date <= end)
            executed = Counter(row.entry_action for row in daily if row.entry_action)
            cohorts[label] = {
                "timed": active,
                **controls,
                "signals": {a: counts[a] for a in ACTIONS},
                "entries": {a: executed[a] for a in ACTIONS},
            }
        holdings = holding_outcomes(
            snapshots=rows, histories=histories, start_date=start_date, end_date=end_date
        )
        (root / "holdings.json").write_text(json.dumps(holdings, default=str, indent=2) + "\n")
        gate_counts = {
            action: dict(
                Counter(
                    f"{gate}:{'unknown' if passed is None else 'pass' if passed else 'fail'}"
                    for row in rows
                    for gate, passed in row.lifecycle["gates"][action].items()
                )
            )
            for action in ACTIONS
        }
        records[config.name] = {
            "config": asdict(config),
            "cohorts": cohorts,
            "final_posture": rows[-1].lifecycle["held"] if rows else None,
            "gate_counts": gate_counts,
        }
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / f"comparison-{input_profile}.json"
    path.write_text(json.dumps(records, indent=2) + "\n")
    return path
