"""Causal action evidence and one persisted daily lifecycle transition."""

from __future__ import annotations

import copy
import math
from dataclasses import asdict, dataclass, field, replace

ACTIONS = ("protect-break", "protect-extension", "redeploy-washout", "redeploy-confirm")
LEGACY_ACTIONS = ("scale_down_protect", "scale_up_redeploy")
FAMILIES = ("trend", "volatility", "breadth", "credit", "liquidity")


def action_direction(action: str) -> str:
    if action == "no_change":
        return "neutral"
    if action in ACTIONS[:2] or action == LEGACY_ACTIONS[0]:
        return "protected"
    if action in ACTIONS[2:] or action == LEGACY_ACTIONS[1]:
        return "redeploying"
    raise ValueError(f"Unknown regime action identity: {action!r}")


@dataclass(frozen=True)
class ActionConfig:
    name: str = "combined"
    input_profile: str = "core"
    stress_geometry: str = "tv"
    transmission: bool = False
    opportunity: bool = True
    sequence: bool = True
    decay_gate: bool = False
    phase_veto: bool = False
    confirm_path: bool = True
    break_path: bool = True
    confirmation: float = 0.75
    family_gate: float = 0.35
    release_gate: float = 0.05
    recovery_fraction: float = 0.50
    extension_age: int = 40
    washout_age: int = 15
    pullback_age: int = 20
    break_watch_sessions: int = 5
    divergence_age: int = 10
    persistence: int = 3
    protect_cap: int = 65
    redeploy_cap: int = 20
    strong_hit: float = 0.75
    persistent_hit: float = 0.60
    setup_leg_gate: float = 0.50
    extension_window: int = 10
    extension_hits: int = 3
    washout_window: int = 5
    washout_hits: int = 2
    episode_max_entries: int = 2


DEFAULT_CONFIG = ActionConfig()


@dataclass(frozen=True)
class Evidence:
    deterioration: float | None
    stabilization: float | None
    exact: bool
    missing: tuple[str, ...] = ()
    leaves: dict[str, tuple[float, float] | None] = field(default_factory=dict)


def maximum_evidence(leaves: dict[str, tuple[float, float] | None]) -> Evidence:
    observed = [value for value in leaves.values() if value is not None]
    missing = tuple(name for name, value in leaves.items() if value is None)
    return Evidence(
        max((v[0] for v in observed), default=None),
        max((v[1] for v in observed), default=None),
        not missing,
        missing,
        leaves,
    )


def _causes_repaired(evidence, causes, threshold):
    for family, names in causes.items():
        e = evidence[family]
        if not names:
            if not e.exact or e.deterioration is None or e.deterioration >= threshold:
                return False
        elif any(e.leaves.get(n) is None or e.leaves[n][0] >= threshold for n in names):
            return False
    return bool(causes)


def second_family(evidence: dict[str, Evidence], side: str) -> float:
    scores = sorted(
        (getattr(e, side) for e in evidence.values() if getattr(e, side) is not None),
        reverse=True,
    )
    return scores[1] if len(scores) >= 2 else 0.0


def confirmation_gate(evidence, side, threshold, count=1):
    """Observed lower bounds prove support, but unresolved alternatives cannot disprove it."""
    proven = sum(
        getattr(item, side) is not None and getattr(item, side) >= threshold for item in evidence
    )
    possible = sum(
        not item.exact and (getattr(item, side) is None or getattr(item, side) < threshold)
        for item in evidence
    )
    return True if proven >= count else None if proven + possible >= count else False


def _all_gates(*values):
    return False if any(value is False for value in values) else None if None in values else True


def _any_gates(*values):
    return True if any(value is True for value in values) else None if None in values else False


def funding_veto(oas_stressed: bool | None, nfci_tight: bool | None) -> bool | None:
    if oas_stressed is False or nfci_tight is False:
        return False
    if oas_stressed is True and nfci_tight is True:
        return True
    return None


def _mean(values):
    return sum(values) / len(values) if values and all(v is not None for v in values) else None


def owned_evidence(snapshot, signals, config=DEFAULT_CONFIG):
    from marketlab import regime as r

    def detail(family, name, key):
        signal = r._signal_by_name(signals, family=family, name=name)
        if signal is None or signal.status == "missing":
            return None
        return r._signal_detail_float(signal, key)

    def signed(value, full, rising_bad=True):
        if value is None:
            return None
        value = value if rising_bad else -value
        return min(1.0, max(0.0, value / full)), min(1.0, max(0.0, -value / full))

    def average(pairs):
        if any(pair is None for pair in pairs):
            return None
        return _mean([p[0] for p in pairs]), _mean([p[1] for p in pairs])

    t5 = [detail("trend", "price_proxy", f"{s}_return_5d") for s in ("spy", "qqq")]
    t20 = [snapshot.spy_return_20d, snapshot.qqq_return_20d]
    short = average([signed(t5[0], 0.03, False), signed(t5[1], 0.04, False)])
    medium = average([signed(t20[0], 0.08, False), signed(t20[1], 0.10, False)])
    trend = maximum_evidence({"5d": short, "20d": medium})
    vix = signed(detail("volatility", "price_proxy", "vix_return_5d"), 0.15)
    vvix = signed(detail("volatility", "vol_of_vol", "vvix_return_5d"), 0.12)
    if vvix is not None and snapshot.vix_close is not None and snapshot.vix_close <= 16:
        vvix = min(1.0, vvix[0] * 1.2), vvix[1]
    term = average(
        [
            signed(detail("volatility", "term_structure", "vix9d_vix_ratio_change_5d"), 0.10),
            signed(detail("volatility", "term_structure", "vix_vix3m_ratio_change_5d"), 0.08),
        ]
    )
    pair = r._vvix_vs_vix_feature(snapshot=snapshot, signals=signals)
    paired = (
        (pair.deterioration_score, pair.stabilization_score)
        if pair is not None
        and vix is not None
        and vvix is not None
        and snapshot.vix_close is not None
        else None
    )
    breadth = average(
        [
            signed(detail("breadth", "price_proxy", "rsp_spy_relative_5d"), 0.025, False),
            signed(detail("breadth", "price_proxy", "iwm_spy_relative_5d"), 0.035, False),
        ]
    )
    credit = {
        "hyg_tlt": signed(detail("credit", "price_proxy", "hyg_tlt_relative_5d"), 0.03, False)
    }
    if config.input_profile == "core":
        credit["oas"] = signed(detail("credit", "credit_spread", "credit_spread_change_5d"), 0.30)
    elif config.input_profile != "reduced":
        raise ValueError(f"Unknown action input profile: {config.input_profile}")
    liquidity = signed(
        detail("liquidity", "financial_conditions", "financial_conditions_change_4w"), 0.15
    )
    evidence = {
        "trend": trend,
        "volatility": maximum_evidence({"vix": vix, "vvix": vvix, "term": term, "pair": paired}),
        "breadth": maximum_evidence({"proxy": breadth}),
        "credit": maximum_evidence(credit),
        "liquidity": maximum_evidence({"nfci": liquidity}),
    }
    features = list(r._action_features(snapshot=snapshot, signals=signals))
    leaf_values = {
        "short_momentum": (trend.deterioration, trend.stabilization),
        "vix_turn": vix,
        "vvix_turn": vvix,
        "term_structure_turn": term,
        "participation_turn": breadth,
        "hyg_tlt_turn": credit["hyg_tlt"],
        "credit_spread_turn": credit.get("oas"),
        "financial_conditions_turn": liquidity,
    }
    features = [
        replace(
            f,
            deterioration_score=leaf_values[f.name][0],
            stabilization_score=leaf_values[f.name][1],
        )
        if f.name in leaf_values
        else f
        for f in features
        if f.name not in leaf_values
        or (leaf_values[f.name] is not None and leaf_values[f.name][0] is not None)
    ]
    # Explanations survive, but only the declared source-owned readings vote.
    modules = tuple(
        r.RegimeActionModule(
            family=f,
            name=f + "_turn",
            deterioration_score=e.deterioration or 0.0,
            stabilization_score=e.stabilization or 0.0,
            feature_count=int(e.deterioration is not None),
            feature_names=(f,),
            reason=(
                "Exact owned evidence" if e.exact else "Lower bound; missing " + ",".join(e.missing)
            ),
        )
        for f, e in evidence.items()
    )
    return evidence, tuple(features), modules, t5


def _pressure(snapshot, names, side):
    features = {f.name: f for f in snapshot.pressure_features}
    return _mean([getattr(features[name], side) if name in features else None for name in names])


def setup_readings(snapshot, config):
    trend_names = (
        "spy_return_20d",
        "spy_return_60d",
        "qqq_return_20d",
        "spy_ma50_distance",
        "qqq_ma50_distance",
    )
    vol_names = (
        "spy_realized_vol_20d",
        "vix_close",
        "vvix_close",
        "vix9d_vix_ratio",
        "vix_vix3m_ratio",
    )
    t, v = (_pressure(snapshot, n, "washout_score") for n in (trend_names, vol_names))
    te, ve = (_pressure(snapshot, n, "stretch_score") for n in (trend_names, vol_names))
    b = _pressure(snapshot, ("rsp_spy_relative_20d", "iwm_spy_relative_20d"), "washout_score")
    cn = (
        ("hyg_tlt_relative_20d", "credit_spread")
        if config.input_profile == "core"
        else ("hyg_tlt_relative_20d",)
    )
    c = _pressure(snapshot, cn, "washout_score")
    observed_transmission = [value for value in (b, c) if value is not None]
    x = max(observed_transmission, default=None)
    x_exact = b is not None and c is not None
    # An observed alternative can prove transmission, but not exact TVX stress/release.
    transmission = True if x is not None and x >= 0.35 else False if x_exact else None
    stress = None
    if t is not None and v is not None:
        if config.stress_geometry == "tv":
            stress = math.sqrt(t * v)
        elif config.stress_geometry == "tvx" and x_exact:
            stress = (t * v * x) ** (1 / 3)
    eligible = _all_gates(
        None if t is None else t >= config.setup_leg_gate,
        None if v is None else v >= config.setup_leg_gate,
        transmission if config.transmission else True,
    )
    washout_hit = None if stress is None or eligible is None else stress if eligible else 0.0
    extension = math.sqrt(te * ve) if te is not None and ve is not None else None
    extension_hit = (
        extension
        if extension is not None and te >= config.setup_leg_gate and ve >= config.setup_leg_gate
        else 0.0
        if extension is not None
        else None
    )
    return stress, washout_hit, extension_hit


def update_setup(old, *, day, index, hit, stress, prices, anchors, kind, config):
    state = copy.deepcopy(old or {})
    window, count = (
        (config.extension_window, config.extension_hits)
        if kind == "extension"
        else (config.washout_window, config.washout_hits)
    )
    limit = config.extension_age if kind == "extension" else config.washout_age
    hits = [h for h in state.get("hits", []) if index - h["index"] < window]
    if hit is not None and hit >= config.persistent_hit:
        hits.append(
            {"index": index, "date": day, "score": hit, "prices": prices, "anchors": anchors}
        )
    state["hits"] = hits
    clock = state.get("last_hit")
    active = clock is not None and index - clock <= limit
    qualifying = hit is not None and (
        hit >= config.strong_hit or (hit >= config.persistent_hit and len(hits) >= count)
    )
    if kind == "extension" and not active and state.get("id"):
        if not state.get("renewal_ready") and hit is not None and hit < config.persistent_hit:
            state["renewal_ready"] = True
            hits = []
            state["hits"] = hits
        qualifying = qualifying and state.get("renewal_ready", False)
    if not active and qualifying:
        establishing = [hits[-1]] if hit >= config.strong_hit else hits[-count:]
        state.pop("retry_date", None)
        state.update(
            {
                "id": f"{kind}:{day}",
                "date": day,
                "index": index,
                "last_hit": index,
                "peak": max(h["score"] for h in establishing),
                "anchors": establishing[0]["anchors"],
                "lows": {s: min(h["prices"][s] for h in establishing) for s in prices},
                "rule": "strong" if hit >= config.strong_hit else "persistent",
                "consumed": False,
                "entry_count": 0,
                "retry_lows": None,
                "renewal_ready": False,
            }
        )
        active = True
    if active:
        if hit is not None and hit >= config.persistent_hit:
            state["last_hit"] = index
        if stress is not None:
            state["peak"] = max(state["peak"], stress)
        for symbol, price in prices.items():
            state["lows"][symbol] = min(state["lows"][symbol], price)
    state["armed"] = active
    state["age"] = index - state["index"] if "index" in state else None
    state["hit_count"] = len(hits)
    state["release"] = max(0.0, state["peak"] - stress) if active and stress is not None else None
    return state


def price_opportunity(episode, prices, fraction):
    if not episode.get("armed"):
        return False
    for symbol, price in prices.items():
        high, low = episode["anchors"][symbol], episode["lows"][symbol]
        if high <= low or price > low + fraction * (high - low):
            return False
    return True


def _reopen_after_new_low(episode, prices, *, allowed, day, config):
    reference = episode.get("retry_lows")
    if (
        allowed
        and episode.get("armed")
        and episode.get("consumed")
        and reference
        and episode.get("entry_count", 0) < config.episode_max_entries
        and all(prices[s] < reference[s] for s in prices)
    ):
        episode["consumed"] = False
        episode["retry_lows"] = None
        episode["retry_date"] = day


def _above(values, threshold=0.0):
    return all(v is not None and v >= threshold for v in values)


def _below(values, threshold=0.0):
    return all(v is not None and v < threshold for v in values)


def transition(*, snapshot, signals, histories, previous=None, config=DEFAULT_CONFIG):
    """Return today's action and JSON-safe resumable state without I/O or future prices."""
    from marketlab import regime as r

    previous = previous or {}
    if previous and previous.get("config") != asdict(config):
        raise ValueError("Action configuration changed inside a snapshot chain; backfill it again")
    index = previous.get("index", -1) + 1
    day = snapshot.source_date.isoformat()
    prices, anchors, recovery_breakouts = {}, {}, {}
    for symbol in ("SPY", "QQQ"):
        rows = [
            p
            for p in histories[symbol]
            if p.observed_date <= snapshot.source_date
            and p.availability_date <= snapshot.source_date
        ]
        if not rows or rows[-1].observed_date != snapshot.source_date:
            raise ValueError(f"Missing {symbol} EOD observation for {day}; refresh sources")
        prices[symbol] = rows[-1].return_close
        anchors[symbol] = max(p.return_close for p in rows[-20:])
        recovery_breakouts[symbol] = (
            prices[symbol] > max(p.return_close for p in rows[-6:-1]) if len(rows) >= 6 else None
        )
    evidence, features, modules, returns5 = owned_evidence(snapshot, signals, config)
    d, s = second_family(evidence, "deterioration"), second_family(evidence, "stabilization")
    stress, wash_hit, extension_hit = setup_readings(snapshot, config)
    wash = update_setup(
        previous.get("washout"),
        day=day,
        index=index,
        hit=wash_hit,
        stress=stress,
        prices=prices,
        anchors=anchors,
        kind="washout",
        config=config,
    )
    extension = update_setup(
        previous.get("extension"),
        day=day,
        index=index,
        hit=extension_hit,
        stress=extension_hit,
        prices=prices,
        anchors=anchors,
        kind="extension",
        config=config,
    )

    def score(family, side="deterioration"):
        return getattr(evidence[family], side)

    def supports(family, side="deterioration", gate=None):
        value = score(family, side)
        return value is not None and value >= (config.family_gate if gate is None else gate)

    def threshold_gate(families, side="deterioration", gate=None, count=1):
        return confirmation_gate(
            [evidence[f] for f in families],
            side,
            config.family_gate if gate is None else gate,
            count,
        )

    def corroborator(side, exclude=("trend",), gate=None):
        families = [f for f in FAMILIES if f not in exclude and supports(f, side, gate)]
        return sorted(families, key=lambda f: (-score(f, side), f))[:1]

    ma50 = [snapshot.spy_ma50_distance, snapshot.qqq_ma50_distance]
    ma200 = [snapshot.spy_ma200_distance, snapshot.qqq_ma200_distance]
    return20 = [snapshot.spy_return_20d, snapshot.qqq_return_20d]
    trend_signal = r._signal_by_name(signals, family="trend", name="price_proxy")
    return60 = [snapshot.spy_return_60d, r._signal_detail_float(trend_signal, "qqq_return_60d")]
    established = _above(ma50) and _above(ma200) and _above(return60)
    pullback = copy.deepcopy(previous.get("pullback", {}))
    onset = (
        previous.get("established", False)
        and any(v is not None and v < 0 for v in ma50)
        and _above(ma200)
    )
    if onset and not pullback.get("armed"):
        pullback = {
            "id": f"pullback:{day}",
            "index": index,
            "date": day,
            "armed": True,
            "anchors": anchors,
            "lows": prices.copy(),
            "last_low": {k: index for k in prices},
            "consumed": False,
            "joint_damage": False,
        }
    if pullback.get("armed"):
        pullback["joint_damage"] = pullback.get("joint_damage", False) or _below(ma50)
        for symbol, value in prices.items():
            if value <= pullback["lows"][symbol]:
                pullback.setdefault("last_low", {})[symbol] = index
        pullback["lows"] = {k: min(v, prices[k]) for k, v in pullback["lows"].items()}
        if (
            index - pullback["index"] > config.pullback_age
            or not _above(ma200)
            or all(prices[k] >= pullback["anchors"][k] for k in prices)
        ):
            pullback["armed"] = False
    repair_streak = previous.get("break_repair", 0) + 1 if _above(ma50) else 0
    br = copy.deepcopy(previous.get("break", {}))
    if repair_streak >= config.persistence:
        br["armed"] = False
        br["ready"] = True
    if br.get("ready") and any(v is not None and v < 0 for v in ma50):
        br = {
            "id": f"break:{day}",
            "date": day,
            "index": index,
            "armed": True,
            "consumed": False,
            "ready": False,
        }
    if "index" in br:
        br["age"] = index - br["index"]
        if br["age"] >= config.break_watch_sessions:
            br["armed"] = False

    divergence = copy.deepcopy(previous.get("divergence", {}))
    if extension.get("id") != previous.get("extension", {}).get("id"):
        divergence = {}
    prior_divergence = []
    prior_divergence_leaves = {}
    for family in ("breadth", "credit"):
        record = divergence.get(family, {})
        original_repaired = _causes_repaired(
            evidence, {family: record.get("leaves", [])}, config.family_gate
        )
        record["repair"] = record.get("repair", 0) + 1 if original_repaired else 0
        if record.get("repair", 0) >= config.persistence:
            record.pop("index", None)
        if (
            extension.get("armed")
            and "index" in record
            and 0 < index - record["index"] <= config.divergence_age
        ):
            prior_divergence.append(family)
            prior_divergence_leaves[family] = list(record.get("leaves", []))
        if extension.get("armed") and _mean(return20) is not None and _mean(return20) >= 0:
            if supports(family):
                record["index"] = index
                record["leaves"] = [
                    name
                    for name, value in evidence[family].leaves.items()
                    if value is not None and value[0] >= config.family_gate
                ]
        divergence[family] = record
    current_divergence = [
        f
        for f in ("breadth", "credit")
        if supports(f) and _mean(return20) is not None and _mean(return20) >= 0
    ]
    div = prior_divergence if config.sequence else current_divergence
    oas = r._signal_status(signals, family="credit", name="credit_spread")
    nfci = r._signal_status(signals, family="liquidity", name="financial_conditions")
    veto = funding_veto(
        None if oas in (None, "missing") else oas == "stressed",
        None if nfci in (None, "missing") else nfci == "tight",
    )
    strong = sorted(
        [f for f in FAMILIES if supports(f, "stabilization", config.confirmation)],
        key=lambda f: (-score(f, "stabilization"), f),
    )
    wash_opportunity = price_opportunity(wash, prices, config.recovery_fraction)
    current_w = snapshot.washout_pressure_score
    old_opportunity = (
        current_w is not None and current_w >= 0.35 and math.sqrt(current_w * s) >= 0.55
    )
    extension_strength = math.sqrt(
        max(0.0, 1 - (index - extension.get("last_hit", index)) / config.extension_age)
        * extension.get("peak", 0.0)
        * d
    )
    gates = {
        "redeploy-washout": {
            "setup": wash["armed"],
            "release": None if wash["release"] is None else wash["release"] >= config.release_gate,
            "confirmation": threshold_gate(FAMILIES, "stabilization", config.confirmation, 2),
            "opportunity": wash_opportunity if config.opportunity else old_opportunity,
            "funding_clear": None if veto is None else not veto,
        },
        "redeploy-confirm": {
            "enabled": config.confirm_path,
            "setup": pullback.get("armed", False) and pullback.get("joint_damage", False),
            "price_recovery": _all_gates(
                None if any(value is None for value in returns5) else _above(returns5),
                *recovery_breakouts.values(),
            ),
            "base": all(
                index - pullback.get("last_low", {}).get(k, index) >= config.persistence
                for k in prices
            ),
            "confirmation": threshold_gate(FAMILIES[1:], "stabilization"),
            "opportunity": bool(pullback.get("armed"))
            and all(prices[k] < pullback["anchors"][k] for k in prices),
            "funding_clear": None if veto is None else not veto,
        },
        "protect-extension": {
            "setup": extension["armed"],
            "divergence": bool(div),
            "uptrend": None if any(value is None for value in ma200) else _above(ma200),
            "volatility": threshold_gate(("volatility",)),
            "damage": _any_gates(
                threshold_gate(("trend",)),
                _all_gates(
                    len(div) >= 2,
                    threshold_gate(("breadth", "credit"), count=2),
                ),
            )
            if config.sequence
            else (supports("trend") or len(div) >= 2),
            "strength": not config.decay_gate or extension_strength >= 0.55,
            "phase": not config.phase_veto or not wash["armed"],
        },
        "protect-break": {
            "enabled": config.break_path,
            "setup": br.get("armed", False),
            "current_damage": None if any(v is None for v in ma50) else _below(ma50),
            "fresh_damage": confirmation_gate(
                [maximum_evidence({"5d": evidence["trend"].leaves.get("5d")})],
                "deterioration",
                config.family_gate,
            ),
            "corroboration": threshold_gate(FAMILIES[1:]),
            "phase": not config.phase_veto or not wash["armed"],
        },
    }
    episodes = {
        "redeploy-washout": wash,
        "redeploy-confirm": pullback,
        "protect-extension": extension,
        "protect-break": br,
    }
    prior_direction = previous.get("held", {}).get("posture", "neutral")
    _reopen_after_new_low(
        wash,
        prices,
        day=day,
        config=config,
        allowed=prior_direction != "redeploying"
        and wash_hit is not None
        and wash_hit >= config.persistent_hit,
    )
    causes = {
        "redeploy-washout": strong[:2],
        "redeploy-confirm": ["trend", *corroborator("stabilization")],
        "protect-extension": list(
            dict.fromkeys(
                ["trend", "volatility", *div[:1]] if supports("trend") else ["volatility", *div]
            )
        ),
        "protect-break": ["trend", *corroborator("deterioration")],
    }
    raw = [name for name in ACTIONS if all(v is True for v in gates[name].values())]
    held = copy.deepcopy(previous.get("held", {"posture": "neutral"}))
    direction = held["posture"]
    supporting = [name for name in raw if action_direction(name) == direction]
    for name in supporting:
        episodes[name]["consumed"] = True
    eligible = [name for name in raw if not episodes[name].get("consumed")]
    directions = {action_direction(name) for name in eligible}
    conflict = len(directions) > 1
    selected = eligible[0] if eligible and not conflict else None
    exit_reason = None
    if direction != "neutral":
        held["age"] = index - held["index"]
        held["observed_lows"] = {
            k: min(held.get("observed_lows", held["lows"])[k], prices[k]) for k in prices
        }
        recovered = (
            direction == "protected"
            and _above(returns5)
            and _causes_repaired(evidence, held["causal_leaves"], config.family_gate)
            and not (supports("trend") and bool(corroborator("deterioration")))
            and (held["action"] != "protect-break" or _above(ma50))
        )
        held["recovery_streak"] = held.get("recovery_streak", 0) + 1 if recovered else 0
        if selected and action_direction(selected) != direction:
            exit_reason = "opposite_action"
        elif held["age"] >= (
            config.protect_cap if direction == "protected" else config.redeploy_cap
        ):
            exit_reason = "holding_expired"
        elif direction == "protected" and held["recovery_streak"] >= config.persistence:
            exit_reason = "protection_recovered"
        elif direction == "redeploying":
            if held["action"] == "redeploy-washout":
                failed = (
                    supports("trend")
                    and supports("volatility")
                    and stress is not None
                    and previous.get("stress") is not None
                    and stress > previous["stress"]
                )
            else:
                structure_failed = any(v is not None and v < 0 for v in ma200) or all(
                    prices[k] < held["lows"][k] for k in prices
                )
                failed = (
                    structure_failed and supports("trend") and bool(corroborator("deterioration"))
                )
            if failed:
                exit_reason = "thesis_failed"
    previous_holding = copy.deepcopy(held) if exit_reason else None
    if exit_reason:
        ended = episodes[held["action"]]
        if ended.get("id") == held["episode"]:
            ended["retry_lows"] = held["observed_lows"].copy()
        held = {"posture": "neutral"}
    action = "no_change"
    if selected and (direction == "neutral" or exit_reason == "opposite_action"):
        action = selected
        episode = episodes[action]
        episode["entry_count"] = episode.get("entry_count", 0) + 1
        held = {
            "posture": action_direction(action),
            "action": action,
            "episode": episode["id"],
            "index": index,
            "date": day,
            "age": 0,
            "families": causes[action],
            "causal_leaves": {
                family: list(
                    dict.fromkeys(
                        [
                            *[
                                name
                                for name, value in evidence[family].leaves.items()
                                if value is not None and value[0] >= config.family_gate
                            ],
                            *(
                                prior_divergence_leaves.get(family, [])
                                if action == "protect-extension"
                                else []
                            ),
                        ]
                    )
                )
                for family in causes[action]
            },
            "prices": prices.copy(),
            "lows": episode.get("lows", prices.copy()),
            "recovery_streak": 0,
        }
        for name in raw:
            if action_direction(name) == held["posture"]:
                episodes[name]["consumed"] = True
    reason = (
        "Conflicting unused opportunities; no new entry"
        if conflict
        else f"{action}: confirmed unused setup"
        if action != "no_change"
        else f"Restore normal: {exit_reason}"
        if exit_reason
        else "Supporting evidence; retain held posture"
        if supporting
        else "No new eligible opportunity"
    )
    state = {
        "config": asdict(config),
        "date": day,
        "index": index,
        "stress": stress,
        "extension": extension,
        "washout": wash,
        "pullback": pullback,
        "break": br,
        "established": established,
        "break_repair": repair_streak,
        "divergence": divergence,
        "evidence": {
            f: {
                **asdict(e),
                "missing": list(e.missing),
                "leaves": {n: list(v) if v is not None else None for n, v in e.leaves.items()},
            }
            for f, e in evidence.items()
        },
        "gates": gates,
        "raw_candidates": raw,
        "eligible_candidates": eligible,
        "supporting": supporting,
        "conflict": conflict,
        "held": held,
        "exit_reason": exit_reason,
        "closed_holding": previous_holding,
        "funding_veto": veto,
        "washout_opportunity": wash_opportunity,
    }
    action_kwargs = {}
    for kind, setup, limit in (
        ("extension", extension, config.extension_age),
        ("washout", wash, config.washout_age),
    ):
        age = setup.get("age")
        freshness_age = index - setup["last_hit"] if "last_hit" in setup else 0
        decay = max(0.0, 1 - freshness_age / limit) if age is not None else None
        action_kwargs.update(
            {
                f"{kind}_memory_status": "armed"
                if setup.get("armed")
                else "expired"
                if setup.get("id")
                else "unarmed",
                f"{kind}_armed": setup.get("armed", False),
                f"{kind}_armed_since": r.date.fromisoformat(setup["date"])
                if setup.get("date")
                else None,
                f"{kind}_armed_age": age,
                f"{kind}_armed_decay": decay,
                f"{kind}_armed_source_strength": setup.get("peak"),
                f"{kind}_arm_rule": setup.get("rule"),
                f"{kind}_arm_hit_count": setup.get("hit_count"),
                f"{kind}_arm_window": config.extension_window
                if kind == "extension"
                else config.washout_window,
                f"{kind}_memory_score": (setup.get("peak", 0) * (decay or 0))
                if setup.get("armed")
                else 0,
                f"{kind}_memory_snapshot_count": index + 1,
            }
        )
    result = r.RegimeActionState(
        source_date=snapshot.source_date,
        action_version=r.REGIME_ACTION_VERSION,
        state=action,
        stretch_score=r._action_setup_bucket(snapshot.stretch_pressure_score or 0),
        washout_score=r._action_setup_bucket(snapshot.washout_pressure_score or 0),
        confidence="high" if all(e.exact for e in evidence.values()) else "low",
        reason=reason,
        evidence=tuple(raw),
        deterioration_score=d,
        stabilization_score=s,
        protect_strength=d,
        redeploy_strength=s,
        action_score=s - d,
        action_path=action if action != "no_change" else None,
        action_features=features,
        action_modules=modules,
        lifecycle=state,
        **action_kwargs,
    )
    return result, wash_hit, extension_hit
