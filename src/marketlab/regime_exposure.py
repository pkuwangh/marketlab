"""Next-open ETF exposure accounting, separate from signal-close forward labels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from marketlab.policy import POLICY_POSTURE_EXPOSURES


@dataclass(frozen=True)
class ExposureDay:
    date: date
    net_return: float
    gross_return: float
    exposure: float
    turnover: float
    cost: float
    financing: float
    entry_action: str | None
    held_action: str | None


def replay_exposure(
    *,
    snapshots,
    histories,
    start_date,
    end_date,
    constant_exposure=None,
    cost_rate=0.0005,
    financing_rate=0.05,
):
    """Replay full warm history, then return the requested valuation slice.

    Costs are charged on actual one-way turnover at the open; previous holdings own the gap.
    Cash return is zero. Borrowing accrues on the preceding close's cash debt, ACT/365.
    """
    snapshots = sorted(snapshots, key=lambda s: s.source_date)
    if not snapshots:
        return ()
    saved = {s.source_date: s for s in snapshots}
    prices = {s: {r.observed_date: r for r in histories[s]} for s in ("SPY", "QQQ")}
    dates = sorted(d for d in prices["SPY"] if snapshots[0].source_date <= d <= end_date)
    assets, cash, gross_assets, gross_cash = [0.5, 0.5], 0.0, [0.5, 0.5], 0.0
    result = []
    for prev_date, day in zip(dates, dates[1:]):
        if prev_date not in saved:
            raise ValueError(f"Missing regime session {prev_date}; backfill before exposure replay")
        signal = saved[prev_date]
        if not signal.lifecycle:
            raise ValueError("Executable exposure replay requires saved v1.1 lifecycle state")
        held = signal.lifecycle["held"]
        target = (
            POLICY_POSTURE_EXPOSURES[held["posture"]]
            if constant_exposure is None
            else constant_exposure
        )
        rows = []
        for symbol in ("SPY", "QQQ"):
            old, new = prices[symbol].get(prev_date), prices[symbol].get(day)
            if old is None or new is None or new.open <= 0 or new.close <= 0:
                raise ValueError(
                    f"Unavailable {symbol} execution price on {day}; no close substitution"
                )
            adjusted_open = new.open * new.return_close / new.close
            rows.append((adjusted_open / old.return_close, new.return_close / adjusted_open))
        old_nav, old_gross = sum(assets) + cash, sum(gross_assets) + gross_cash
        finance = max(0.0, -cash) * financing_rate * (day - prev_date).days / 365
        cash -= finance
        opened = [value * pair[0] for value, pair in zip(assets, rows)]
        pretrade = sum(opened) + cash
        if pretrade <= 0:
            raise ValueError("Nonpositive research account equity")
        # Solve cost = rate * actual turnover, including the cash consumed by that cost.
        low, high = 0.0, pretrade
        for _ in range(60):
            cost = (low + high) / 2
            turnover = sum(abs((pretrade - cost) * target / 2 - value) for value in opened)
            if cost > cost_rate * turnover:
                high = cost
            else:
                low = cost
        cost = (low + high) / 2
        nav_open = pretrade - cost
        turnover = sum(abs(nav_open * target / 2 - value) for value in opened)
        assets = [nav_open * target / 2 * pair[1] for pair in rows]
        cash = nav_open * (1 - target)
        gross_open = sum(value * pair[0] for value, pair in zip(gross_assets, rows)) + gross_cash
        gross_assets = [gross_open * target / 2 * pair[1] for pair in rows]
        gross_cash = gross_open * (1 - target)
        if start_date <= day <= end_date:
            result.append(
                ExposureDay(
                    date=day,
                    net_return=(sum(assets) + cash) / old_nav - 1,
                    gross_return=(sum(gross_assets) + gross_cash) / old_gross - 1,
                    exposure=target,
                    turnover=turnover / old_nav,
                    cost=cost / old_nav,
                    financing=finance / old_nav,
                    entry_action=signal.action_state
                    if signal.action_state != "no_change"
                    else None,
                    held_action=held.get("action"),
                )
            )
    return tuple(result)


def summarize_exposure(rows):
    nav = peak = gross = 1.0
    drawdown = 0.0
    for row in rows:
        nav *= 1 + row.net_return
        gross *= 1 + row.gross_return
        peak = max(peak, nav)
        drawdown = min(drawdown, nav / peak - 1)
    return {
        "sessions": len(rows),
        "net_return": nav - 1,
        "gross_return": gross - 1,
        "portfolio_drawdown": drawdown,
        "average_exposure": sum(r.exposure for r in rows) / len(rows) if rows else None,
        "turnover": sum(r.turnover for r in rows),
        "cost": sum(r.cost for r in rows),
        "financing": sum(r.financing for r in rows),
        "protected_sessions": sum(r.exposure < 1 for r in rows),
        "increased_sessions": sum(r.exposure > 1 for r in rows),
    }


def exposure_report(*, snapshots, histories, start_date, end_date):
    from marketlab.regime import _format_table

    kwargs = dict(
        snapshots=snapshots, histories=histories, start_date=start_date, end_date=end_date
    )
    active = replay_exposure(**kwargs)
    summary = summarize_exposure(active)
    rows = [
        [
            "account",
            "sessions",
            "net",
            "gross",
            "portfolio_dd",
            "avg_exposure",
            "turnover",
            "cost",
            "financing",
            "reduced",
            "increased",
        ]
    ]
    for label, record in (
        ("timed", summary),
        ("untimed", summarize_exposure(replay_exposure(**kwargs, constant_exposure=1.0))),
        (
            "matched_exposure",
            summarize_exposure(
                replay_exposure(**kwargs, constant_exposure=summary["average_exposure"] or 1.0)
            ),
        ),
    ):
        rows.append(
            [
                label,
                str(record["sessions"]),
                f"{record['net_return']:+.2%}",
                f"{record['gross_return']:+.2%}",
                f"{record['portfolio_drawdown']:.2%}",
                f"{record['average_exposure'] or 0:.3f}",
                f"{record['turnover']:.3f}",
                f"{record['cost']:.2%}",
                f"{record['financing']:.2%}",
                str(record["protected_sessions"]),
                str(record["increased_sessions"]),
            ]
        )
    return (
        "Executable exposure: next adjusted open; 80% core, 0/20/40% tactical; "
        "50/50 SPY/QQQ; cash 0%, borrowing 5%, one-way costs 5bp\n"
        "Cost/financing columns sum daily equity charges; reduced/increased count sessions.\n"
        + _format_table(rows)
    )


def holding_outcomes(*, snapshots, histories, start_date, end_date):
    """Actual entry/exit-open price windows; open episodes marked, never force-closed."""
    by_date = {s.source_date: s for s in snapshots}
    dates = sorted(row.observed_date for row in histories["SPY"])
    prices = {s: {row.observed_date: row for row in histories[s]} for s in ("SPY", "QQQ")}
    rows = []
    for day in sorted(by_date):
        snap = by_date[day]
        if not (start_date <= day <= end_date) or snap.action_state == "no_change":
            continue
        entry_index = dates.index(day) + 1
        if entry_index >= len(dates) or dates[entry_index] > end_date:
            continue  # EOD signal is not yet an executed entry inside this valuation window.
        episode = snap.lifecycle["held"]["episode"]
        closing = next(
            (
                s
                for d, s in sorted(by_date.items())
                if day < d <= end_date
                and s.lifecycle.get("closed_holding", {}) is not None
                and s.lifecycle.get("closed_holding", {}).get("episode") == episode
            ),
            None,
        )
        exit_index = dates.index(closing.source_date) + 1 if closing else len(dates)
        closed = exit_index < len(dates) and dates[exit_index] <= end_date
        last_index = exit_index if closed else max(i for i, d in enumerate(dates) if d <= end_date)
        record = {
            "action": snap.action_state,
            "episode": episode,
            "entry": dates[entry_index],
            "exit": dates[exit_index] if closed else None,
            "open": not closed,
            "exit_reason": closing.lifecycle["exit_reason"] if closed else None,
            "sessions": last_index - entry_index,
        }
        for symbol in ("SPY", "QQQ"):

            def observed(index):
                row = prices[symbol].get(dates[index])
                if row is None or row.open <= 0 or row.close <= 0:
                    raise ValueError(f"Unavailable {symbol} holding price on {dates[index]}")
                return row

            entry = observed(entry_index)
            opening = entry.open * entry.return_close / entry.close
            final = observed(last_index)
            ending = final.open * final.return_close / final.close if closed else final.return_close
            path = [observed(i).return_close for i in range(entry_index, last_index + (not closed))]
            path.append(ending)
            peak, drawdown = opening, 0.0
            for value in path:
                peak = max(peak, value)
                drawdown = min(drawdown, value / peak - 1)
            record[symbol] = {
                "return": ending / opening - 1,
                "entry_loss": min(0.0, min(path) / opening - 1),
                "running_drawdown": drawdown,
            }
        rows.append(record)
    return rows


def holding_report(**kwargs):
    from marketlab.regime import _format_table
    from marketlab.regime_lifecycle import ACTIONS

    episodes = holding_outcomes(**kwargs)
    rows = [
        [
            "action",
            "entries",
            "closed",
            "open",
            "avg_held_SPY",
            "avg_held_QQQ",
            "SPY_entry_loss",
            "SPY_running_dd",
        ]
    ]
    for action in ACTIONS:
        cohort = [row for row in episodes if row["action"] == action]
        closed = [row for row in cohort if not row["open"]]

        def mean(symbol, field):
            return (
                f"{sum(row[symbol][field] for row in closed) / len(closed):+.2%}" if closed else "-"
            )

        rows.append(
            [
                action,
                str(len(cohort)),
                str(len(closed)),
                str(len(cohort) - len(closed)),
                mean("SPY", "return"),
                mean("QQQ", "return"),
                mean("SPY", "entry_loss"),
                mean("SPY", "running_drawdown"),
            ]
        )
    return (
        "Executed holding windows: underlying ETF returns, not portfolio P/L; "
        "averages use closed episodes only\n" + _format_table(rows)
    )
