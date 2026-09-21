"""Historical action-rule fixture; not an executable production model."""

from __future__ import annotations

import math

from marketlab.regime import (
    ACTION_CONFIRMATION_THRESHOLD,
    ACTION_REDEPLOY_CURRENT_WASHOUT_THRESHOLD,
    ACTION_REDEPLOY_STABILIZATION_THRESHOLD,
    ACTION_REDEPLOY_WASHOUT_RELEASE_THRESHOLD,
    ACTION_STRENGTH_THRESHOLD,
    MarketSignal,
    RegimeActionState,
    RegimeExtensionMemory,
    RegimeSnapshot,
    RegimeWashoutMemory,
    _action_confidence,
    _action_feature_evidence,
    _action_features,
    _action_module_average,
    _action_modules,
    _action_reason,
    _action_setup_bucket,
    _action_setup_score,
    _current_only_extension_memory,
    _current_only_washout_memory,
    _event_volatility_context,
    _family_list_read,
    _protect_gate_evidence,
    _protect_gate_result,
    _protect_long_term_uptrend,
    _redeploy_confirmation_ready,
    _redeploy_stabilization_families,
    _severe_funding_stress,
    _stretch_evidence,
    _washout_evidence,
    _washout_memory_reason,
    _washout_release_from_peak,
)


def derive_regime_action_state(
    *,
    snapshot: RegimeSnapshot,
    signals: tuple[MarketSignal, ...] = (),
    extension_memory: RegimeExtensionMemory | None = None,
    washout_memory: RegimeWashoutMemory | None = None,
) -> RegimeActionState:
    """Derive rare-action state from setup pressure and turn evidence."""

    stretch_evidence = _stretch_evidence(snapshot=snapshot, signals=signals)
    washout_evidence = _washout_evidence(snapshot=snapshot, signals=signals)
    action_features = _action_features(snapshot=snapshot, signals=signals)
    action_modules = _action_modules(action_features)
    deterioration_score = _action_module_average(
        action_modules,
        field_name="deterioration_score",
    )
    stabilization_score = _action_module_average(
        action_modules,
        field_name="stabilization_score",
    )
    stretch_setup_score = _action_setup_score(
        snapshot.stretch_pressure_score,
        fallback_evidence_count=len(stretch_evidence),
    )
    extension_setup_score = (
        _action_setup_score(
            snapshot.extension_setup_score,
            fallback_evidence_count=len(stretch_evidence),
        )
        if snapshot.extension_setup_score is not None
        else stretch_setup_score
    )
    fragility_context_score = (
        _action_setup_score(
            snapshot.fragility_context_score,
            fallback_evidence_count=0,
        )
        if snapshot.fragility_context_score is not None
        else 0.0
    )
    washout_setup_score = (
        _action_setup_score(
            snapshot.washout_setup_score,
            fallback_evidence_count=len(washout_evidence),
        )
        if snapshot.washout_setup_score is not None
        else _action_setup_score(
            snapshot.washout_pressure_score,
            fallback_evidence_count=len(washout_evidence),
        )
    )
    stretch_score = _action_setup_bucket(stretch_setup_score)
    washout_score = _action_setup_bucket(washout_setup_score)
    extension_memory = extension_memory or _current_only_extension_memory(
        snapshot=snapshot,
        extension_setup_score=extension_setup_score,
    )
    washout_memory = washout_memory or _current_only_washout_memory(
        snapshot=snapshot,
        washout_setup_score=washout_setup_score,
    )
    protect_gate = _protect_gate_result(
        extension_setup_score=extension_setup_score,
        extension_memory=extension_memory,
        long_term_uptrend=_protect_long_term_uptrend(snapshot),
        fragility_context_score=fragility_context_score,
        deterioration_score=deterioration_score,
        action_features=action_features,
        action_modules=action_modules,
    )
    protect_strength = max(
        protect_gate.extension_strength,
        protect_gate.regime_break_strength,
    )
    current_washout_score = _action_setup_score(
        snapshot.washout_pressure_score,
        fallback_evidence_count=len(washout_evidence),
    )
    washout_release = _washout_release_from_peak(
        current_setup_score=washout_setup_score,
        washout_memory=washout_memory,
    )
    current_washout_ready = current_washout_score >= ACTION_REDEPLOY_CURRENT_WASHOUT_THRESHOLD
    washout_release_ready = washout_release >= ACTION_REDEPLOY_WASHOUT_RELEASE_THRESHOLD
    redeploy_strength = math.sqrt(current_washout_score * stabilization_score)
    action_score = redeploy_strength - protect_strength
    severe_funding_stress = _severe_funding_stress(signals)
    stabilization_families = _redeploy_stabilization_families(action_modules)
    redeploy_confirmation_ready = _redeploy_confirmation_ready(
        stabilization_score=stabilization_score,
        action_modules=action_modules,
    )
    redeploy_ready = (
        washout_memory.armed
        and current_washout_ready
        and washout_release_ready
        and redeploy_confirmation_ready
        and redeploy_strength >= ACTION_STRENGTH_THRESHOLD
    )
    protect_ready = protect_gate.path is not None and not washout_memory.armed

    if redeploy_ready and severe_funding_stress:
        state = "no_change"
        action_path = None
        evidence = _action_feature_evidence(
            action_features,
            field_name="stabilization_score",
        )
        reason = "Redeploy setup present, but credit and liquidity stress block aggressive re-risk"
    elif redeploy_ready:
        state = "scale_up_redeploy"
        action_path = "redeploy"
        evidence = _action_feature_evidence(
            action_features,
            field_name="stabilization_score",
        ) + (_washout_memory_reason(washout_memory),)
        reason = (
            "Armed prior washout, current opportunity, pressure release, and "
            "stabilization support staged redeploy"
        )
    elif protect_ready:
        state = "scale_down_protect"
        action_path = protect_gate.path
        evidence = _action_feature_evidence(
            action_features,
            field_name="deterioration_score",
        ) + _protect_gate_evidence(protect_gate)
        reason = f"{protect_gate.path} protect: {protect_gate.reason}"
    elif protect_gate.path is not None and washout_memory.armed:
        state = "no_change"
        action_path = "washout_blocks_protect"
        evidence = _action_feature_evidence(
            action_features,
            field_name="deterioration_score",
        ) + (_washout_memory_reason(washout_memory),)
        reason = "Protect confirmation arrived after washout armed; do not de-risk late"
    elif protect_gate.reason.startswith("regime_break_warning"):
        state = "no_change"
        action_path = "regime_break_warning"
        evidence = _action_feature_evidence(
            action_features,
            field_name="deterioration_score",
        ) + _protect_gate_evidence(protect_gate)
        reason = protect_gate.reason
    elif protect_gate.warning_only and protect_strength >= ACTION_STRENGTH_THRESHOLD:
        state = "no_change"
        action_path = "volatility_only_warning"
        evidence = _action_feature_evidence(
            action_features,
            field_name="deterioration_score",
        ) + _protect_gate_evidence(protect_gate)
        reason = protect_gate.reason
    elif washout_memory.armed and redeploy_confirmation_ready and not current_washout_ready:
        state = "no_change"
        action_path = None
        evidence = _action_feature_evidence(
            action_features,
            field_name="stabilization_score",
        ) + (_washout_memory_reason(washout_memory),)
        reason = (
            "Washout setup and stabilization are present, but current broad "
            "washout has already cleared"
        )
    elif washout_memory.armed and redeploy_confirmation_ready and not washout_release_ready:
        state = "no_change"
        action_path = None
        evidence = _action_feature_evidence(
            action_features,
            field_name="stabilization_score",
        ) + (_washout_memory_reason(washout_memory),)
        reason = "Washout remains near its remembered peak; wait for pressure to release"
    elif washout_memory.armed and redeploy_confirmation_ready:
        state = "no_change"
        action_path = None
        evidence = _action_feature_evidence(
            action_features,
            field_name="stabilization_score",
        ) + (_washout_memory_reason(washout_memory),)
        reason = "Redeploy setup and confirmation passed, but strength is below its gate"
    elif washout_memory.armed and stabilization_score >= ACTION_CONFIRMATION_THRESHOLD:
        state = "no_change"
        action_path = None
        evidence = _action_feature_evidence(
            action_features,
            field_name="stabilization_score",
        ) + (_washout_memory_reason(washout_memory),)
        reason = (
            "Washout setup is armed, but stabilization is not yet strong and broad "
            f"(families {_family_list_read(stabilization_families)})"
        )
    elif washout_memory.armed:
        state = "no_change"
        action_path = None
        evidence = washout_evidence
        reason = "Washout setup is armed, but stabilization confirmation is below its gate"
    elif (
        stabilization_score >= ACTION_REDEPLOY_STABILIZATION_THRESHOLD
        and redeploy_strength >= ACTION_STRENGTH_THRESHOLD - 0.10
    ):
        state = "no_change"
        action_path = None
        evidence = _action_feature_evidence(
            action_features,
            field_name="stabilization_score",
        )
        reason = "Stabilization is visible, but washout setup is not armed"
    elif max(stretch_setup_score, washout_setup_score) >= 0.65:
        state = "no_change"
        action_path = None
        evidence = stretch_evidence + washout_evidence
        reason = "Setup pressure present, but broad confirmation is not strong enough"
    else:
        state = "no_change"
        action_path = None
        evidence = stretch_evidence + washout_evidence
        reason = "No actionable setup; maintain current posture"
    event_volatility_context = _event_volatility_context(
        signals=signals,
        protect_gate=protect_gate,
    )

    return RegimeActionState(
        source_date=snapshot.source_date,
        action_version="regime_action_v1.0",
        state=state,
        stretch_score=stretch_score,
        washout_score=washout_score,
        confidence=_action_confidence(
            state=state,
            protect_strength=protect_strength,
            redeploy_strength=redeploy_strength,
            signals=signals,
            action_features=action_features,
        ),
        reason=_action_reason(reason=reason, evidence=evidence),
        evidence=evidence,
        deterioration_score=deterioration_score,
        stabilization_score=stabilization_score,
        protect_strength=protect_strength,
        redeploy_strength=redeploy_strength,
        action_score=action_score,
        action_path=action_path,
        event_volatility_context=event_volatility_context,
        extension_memory_status=extension_memory.status,
        extension_armed=extension_memory.armed,
        extension_armed_since=extension_memory.armed_since,
        extension_armed_age=extension_memory.armed_age,
        extension_armed_decay=extension_memory.armed_decay,
        extension_armed_source_strength=extension_memory.armed_source_strength,
        extension_arm_rule=extension_memory.arm_rule,
        extension_arm_hit_count=extension_memory.arm_hit_count,
        extension_arm_window=extension_memory.arm_window,
        extension_memory_score=extension_memory.effective_score,
        extension_memory_snapshot_count=extension_memory.snapshot_count,
        washout_memory_status=washout_memory.status,
        washout_armed=washout_memory.armed,
        washout_armed_since=washout_memory.armed_since,
        washout_armed_age=washout_memory.armed_age,
        washout_armed_decay=washout_memory.armed_decay,
        washout_armed_source_strength=washout_memory.armed_source_strength,
        washout_arm_rule=washout_memory.arm_rule,
        washout_arm_hit_count=washout_memory.arm_hit_count,
        washout_arm_window=washout_memory.arm_window,
        washout_memory_score=washout_memory.effective_score,
        washout_memory_snapshot_count=washout_memory.snapshot_count,
        action_features=action_features,
        action_modules=action_modules,
    )
