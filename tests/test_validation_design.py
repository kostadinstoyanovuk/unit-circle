import math
import numpy as np
import pytest
from uc_core.constants import POWER_ONSETS
from uc_core.validation_design import h1_design_series, wilson_interval, summarize_power


def test_design_stationary_initialization_and_recursion_against_hand_equations():
    # A single engineering path, not an official size/power cell.
    rng = np.random.default_rng(99234)
    reference = np.random.default_rng(99234)
    actual = h1_design_series(rng, kappa=1.4)
    variance = 1225/88
    cov = variance/3
    assert variance == pytest.approx(.3**2*variance+.1**2*variance+2*.3*.1*cov+3.5**2)
    assert cov == pytest.approx(.3*variance+.1*cov)
    z = reference.standard_normal(2)
    noise = reference.normal(0,3.5,257)
    expected = [2.5+math.sqrt(variance)*z[0],
                2.5+cov/math.sqrt(variance)*z[0]+math.sqrt(variance-cov**2/variance)*z[1]]
    active = [t for r in POWER_ONSETS for t in range(r-8,r)]
    assert len(active) == 40 and min(active) == 41 and max(active) == 248
    for t in range(2,259):
        a,b = (.42,.196) if t in active else (.3,.1)
        c = 2.5*(1-a-b) if t in active else 1.5
        expected.append(c+a*expected[-1]+b*expected[-2]+noise[t-2])
    np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-13)
    assert rng.bit_generator.state == reference.bit_generator.state


def table(rejections, means):
    return [[.01]*r+[.5]*(200-r) for r in rejections], [[v]*200 for v in means]


def test_kappa_one_uses_exact_base_intercept_everywhere():
    rng = np.random.default_rng(7185)
    reference = np.random.default_rng(7185)
    actual = h1_design_series(rng,kappa=1.)
    reference.standard_normal(2)
    noise = reference.normal(0,3.5,257)
    expected = list(actual[:2])
    for error in noise:
        expected.append(1.5+.3*expected[-1]+.1*expected[-2]+error)
    np.testing.assert_array_equal(actual,expected)


def test_D80_hand_interpolation_and_first_crossing():
    result = summarize_power(*table([20,120,180,190],[0.,.1,.4,.6]))
    assert result["kappa80"] == pytest.approx(1.2+(2/3)*.2)
    assert result["D80"] == pytest.approx(.3)
    assert result["crossing"]["weight"] == pytest.approx(2/3)
    assert result["AT16_passed"]


def test_D80_empty_crossing_and_invalid_cells_are_explicit():
    assert summarize_power(*table([10,20,30,40],[0,1,2,3]))["D80"] is None
    ps,ss = table([10,120,180,190],[0,1,2,3])
    ps[3][0] = None
    result = summarize_power(ps,ss)
    assert result["D80"] is None and not result["AT16_passed"]
    assert result["cells"][3]["invalid_or_unfinished"] == 1
    assert result["cells"][3]["rate"] is None


def test_first_crossing_preserved_despite_later_nonmonotonicity():
    result = summarize_power(*table([160,10,180,190],[.2,1,2,3]))
    assert result["D80"] == pytest.approx(.2)
    assert result["kappa80"] == 1
    assert result["decrease_flags"][0] and not result["AT16_passed"]


def test_adjacent_precision_is_saved_without_smoothing():
    result = summarize_power(*table([20,120,180,190],[0,.1,.4,.6]))
    first = result["adjacent_comparisons"][0]
    assert first["difference"] == pytest.approx(.5)
    assert first["standard_error"] == pytest.approx(math.sqrt(.1*.9/200+.6*.4/200))
    assert (first["left_kappa"],first["right_kappa"]) == (1.,1.2)


def test_wilson_boundaries_and_invalid_inputs():
    assert wilson_interval(0,10)[0] == pytest.approx(0)
    assert wilson_interval(10,10)[1] == pytest.approx(1)
    low, high = wilson_interval(5,10)
    assert low == pytest.approx(1-high)
    for args in [(0,0),(-1,10),(11,10),(True,10),(1.5,10)]:
        with pytest.raises(ValueError):
            wilson_interval(*args)


def test_power_summary_rejects_malformed_tables():
    with pytest.raises(ValueError):
        summarize_power([],[])
    ps,ss = table([10,20,30,40],[0,1,2,3])
    ps[0][0] = np.nan
    with pytest.raises(ValueError):
        summarize_power(ps,ss)
