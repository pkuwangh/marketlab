"""Entry-only development replay; no exposure accounting or canonical writes.

Run from the repository root with a trial name. baseline.jsonl is the frozen
pre-entry-review v1.2 snapshot set under data/research/regime/v1.2/entries.
"""

import csv
import json
import sys
from dataclasses import replace
from pathlib import Path
from statistics import mean

from marketlab import regime as r
from marketlab.market_signals import load_market_signal_snapshot
from marketlab.regime_lifecycle import ACTIONS, DEFAULT_CONFIG, transition

ROOT = Path("data/research/regime/v1.2/entries")
HORIZONS = (20, 40, 65)
REFERENCES = {
    "E1-divergence-repair": "baseline",
    "E2-internals": "E1-divergence-repair",
    "B1-fresh-internal-break": "E2-internals",
    "B2-fresh-break": "E2-internals",
    "C1-base-recovery": "E2-internals",
    "C2-sequential-pullback": "C1-base-recovery",
    "B3-support-transition": "C2-sequential-pullback",
    "B3-retry-ablation": "C2-sequential-pullback",
}


def labels(rows, histories):
    dates = r._action_event_dates(snapshots=tuple(rows), prior_snapshots=())
    return tuple(
        outcome
        for row in rows
        for outcome in r._regime_action_outcomes(
            snapshot=row,
            action=r._action_state_from_snapshot(row),
            is_action_event=row.source_date in dates,
            histories=histories,
            horizons=HORIZONS,
        )
    )


def event_records(outcomes, histories):
    prices = histories["SPY"]
    indexes = {p.observed_date: i for i, p in enumerate(prices)}
    return [
        {
            "date": str(o.source_date),
            "action": o.action_state,
            "horizon": o.horizon_days,
            "label_end": str(prices[indexes[o.price_date] + o.horizon_days].observed_date)
            if indexes[o.price_date] + o.horizon_days < len(prices)
            else None,
            "spy": o.spy_return,
            "qqq": o.qqq_return,
            "spy_dd": o.spy_max_drawdown,
            "qqq_dd": o.qqq_max_drawdown,
        }
        for o in outcomes
        if o.is_action_event
    ]


def summary(outcomes):
    return r.format_regime_action_outcome_summary(r.summarize_regime_action_outcomes(outcomes))


def write_results(root, rows, baseline, histories, *, write_snapshots=True):
    root.mkdir(parents=True, exist_ok=True)
    outcomes = labels(rows, histories)
    events = event_records(outcomes, histories)
    prior = event_records(labels(baseline, histories), histories)
    before = {(e["date"], e["action"]) for e in prior}
    after = {(e["date"], e["action"]) for e in events}
    old_dates, new_dates = (
        {str(s.source_date): s for s in baseline},
        {str(s.source_date): s for s in rows},
    )
    differences = []
    for kind, keys, source in (
        ("added", after - before, events),
        ("removed", before - after, prior),
    ):
        for day, action in sorted(keys):
            differences.append(
                {
                    "change": kind,
                    "date": day,
                    "action": action,
                    "labels": [e for e in source if (e["date"], e["action"]) == (day, action)],
                    "before_gates": old_dates[day].lifecycle["gates"][action],
                    "after_gates": new_dates[day].lifecycle["gates"][action],
                    "before_action": old_dates[day].action_state,
                    "after_action": new_dates[day].action_state,
                    "before_consumed": {
                        k: old_dates[day].lifecycle[k].get("consumed")
                        for k in ("extension", "break", "pullback", "washout")
                    },
                    "after_consumed": {
                        k: new_dates[day].lifecycle[k].get("consumed")
                        for k in ("extension", "break", "pullback", "washout")
                    },
                }
            )
    text = summary(outcomes)
    (root / "table.txt").write_text(text + "\n")
    (root / "events.json").write_text(json.dumps(events, indent=2) + "\n")
    (root / "changes.json").write_text(json.dumps(differences, indent=2) + "\n")
    if write_snapshots:
        temporary = root / "snapshots.jsonl.tmp"
        with temporary.open("w") as handle:
            for row in rows:
                handle.write(json.dumps(row.to_dict(), default=str) + "\n")
        temporary.replace(root / "snapshots.jsonl")
    cohorts = {}
    for name, keep in (
        ("pre2020", lambda e: e["date"] < "2020"),
        ("post2020", lambda e: e["date"] >= "2021"),
        ("excluding2020", lambda e: not e["date"].startswith("2020")),
        ("2022", lambda e: e["date"].startswith("2022")),
        (
            "without_pandemic_window",
            lambda e: (
                e["date"] > "2020-04-30"
                or (e["label_end"] is not None and e["label_end"] < "2020-02-20")
            ),
        ),
    ):
        cohorts[name] = {}
        for action in ACTIONS:
            cohorts[name][action] = {}
            for horizon in HORIZONS:
                subset = [
                    e
                    for e in events
                    if e["action"] == action and e["horizon"] == horizon and keep(e)
                ]
                cohorts[name][action][horizon] = {
                    "n": len(subset),
                    **{
                        key: mean(e[key] for e in subset if e[key] is not None)
                        if any(e[key] is not None for e in subset)
                        else None
                        for key in ("spy", "qqq", "spy_dd", "qqq_dd")
                    },
                }
    (root / "cohorts.json").write_text(json.dumps(cohorts, indent=2) + "\n")
    print(root, flush=True)
    print(text, flush=True)
    print("CHANGES", [(d["change"], d["date"], d["action"]) for d in differences], flush=True)


def main(name):
    baseline = [
        r._snapshot_from_dict(json.loads(line))
        for line in (ROOT / "baseline.jsonl").read_text().splitlines()
    ]
    histories = r._load_histories(
        symbols=r.DEFAULT_REGIME_PRICE_SYMBOLS, price_root=r.DEFAULT_PRICE_OBSERVATIONS_ROOT
    )
    signals = {
        s.source_date: load_market_signal_snapshot(
            source_date=s.source_date, snapshot_version="v1.2"
        )
        for s in baseline
    }
    for profile in ("core", "reduced"):
        config = replace(DEFAULT_CONFIG, input_profile=profile)
        rows = []
        for s in baseline:
            action, wash, extension = transition(
                snapshot=s,
                signals=signals[s.source_date],
                histories=histories,
                previous=rows[-1].lifecycle if rows else None,
                config=config,
            )
            rows.append(
                r._snapshot_with_action(
                    snapshot=replace(s, washout_setup_score=wash, extension_setup_score=extension),
                    action=action,
                )
            )
        if name == "baseline" and profile == "core":
            assert all(
                a.lifecycle == b.lifecycle and a.action_state == b.action_state
                for a, b in zip(rows, baseline, strict=True)
            )
        reference = baseline
        if profile == "reduced" or name in REFERENCES:
            reference = (
                rows
                if name == "baseline"
                else [
                    r._snapshot_from_dict(json.loads(line))
                    for line in (
                        ROOT / REFERENCES.get(name, "baseline") / profile / "snapshots.jsonl"
                    )
                    .read_text()
                    .splitlines()
                ]
            )
        write_results(ROOT / name / profile, rows, reference, histories)


def audit():
    """Re-label frozen trial rows, retaining rejected experiments and exact event changes."""
    histories = r._load_histories(
        symbols=r.DEFAULT_REGIME_PRICE_SYMBOLS, price_root=r.DEFAULT_PRICE_OBSERVATIONS_ROOT
    )
    records = []
    for name, reference in {"baseline": "baseline", **REFERENCES}.items():
        for profile in ("core", "reduced"):

            def read(trial):
                return [
                    r._snapshot_from_dict(json.loads(line))
                    for line in (ROOT / trial / profile / "snapshots.jsonl")
                    .read_text()
                    .splitlines()
                ]

            root = ROOT / name / profile
            write_results(root, read(name), read(reference), histories, write_snapshots=False)
            for change in json.loads((root / "changes.json").read_text()):
                for label in change["labels"]:
                    records.append(
                        {
                            "trial": name,
                            "reference": reference,
                            "profile": profile,
                            "change": change["change"],
                            **label,
                            **{
                                key: json.dumps(change[key], sort_keys=True)
                                for key in (
                                    "before_gates",
                                    "after_gates",
                                    "before_consumed",
                                    "after_consumed",
                                )
                            },
                            "before_action": change["before_action"],
                            "after_action": change["after_action"],
                        }
                    )
    with (Path(__file__).parent / "entry-event-changes.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


if __name__ == "__main__":
    audit() if sys.argv[1] == "audit" else main(sys.argv[1])
