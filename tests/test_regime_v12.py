from dataclasses import replace

import pytest
from test_regime_lifecycle import inputs

from marketlab.regime import _vvix_vs_vix_feature


@pytest.mark.parametrize(
    "vix_move,vvix_move,expected",
    [(-0.46, -0.30, 0), (-0.15, 0, 0), (-0.05, 0.12, 1), (0.05, 0.17, 1)],
)
def test_relative_volatility_deterioration_requires_actual_vvix_rise(
    vix_move, vvix_move, expected
):
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
