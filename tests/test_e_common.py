import math

import numpy as np
import pytest

from uc_core.validation_design import summarize_power as h1_summarize_power
from uc_ext import common as c

DEV = c.DEVELOPMENT_MASTER_SEED


def _records(ps, ss):
    return [dict(replicate=i, status="ok" if p is not None else "failed", p_value=p, S=v)
            for i, (p, v) in enumerate(zip(ps, ss))]


def _table(seed, rates):
    rng = np.random.default_rng(seed)
    ps, ss = [], []
    for rate in rates:
        rejected = rng.random(200) < rate
        ps.append([float(rng.uniform(0, .05)) if r else float(rng.uniform(.051, 1)) for r in rejected])
        ss.append(rng.normal(rate / 10, .05, 200).tolist())
    return ps, ss


@pytest.mark.parametrize("seed,rates", [(1, (.1, .4, .79, .95)), (2, (.85, .9, .95, .99)),
                                         (3, (.05, .1, .2, .3)), (4, (.5, .2, .9, .9))])
def test_power_summary_reproduces_h1_at_200_per_cell(seed, rates):
    ps, ss = _table(seed, rates)
    reference = h1_summarize_power(ps, ss)
    cells = [c.summarize_cell(_records(p, v), 200) for p, v in zip(ps, ss)]
    ours = c.summarize_power_cells(cells, (1., 1.2, 1.4, 1.6), registered=True)
    for key in ("D80", "kappa80", "crossing", "decrease_flags"):
        assert ours[key] == reference[key]
    assert ours["passed"] == reference["AT16_passed"]
    for mine, theirs in zip(ours["cells"], reference["cells"]):
        for key in ("rate", "rate_se", "rate_wilson", "rejected", "accounting_bounds"):
            assert mine[key] == pytest.approx(theirs[key], abs=1e-15)
        assert mine["mean_S"] == pytest.approx(theirs["mean_S"], rel=1e-12)
        assert mine["mean_S_se"] == pytest.approx(theirs["mean_S_se"], rel=1e-12)


def test_invalid_cell_leaves_d80_undefined_as_h1():
    ps, ss = _table(5, (.9, .9, .9, .9))
    ps[2][7] = None
    ss[2][7] = None
    reference = h1_summarize_power(ps, ss)
    cells = [c.summarize_cell(_records(p, v), 200) for p, v in zip(ps, ss)]
    ours = c.summarize_power_cells(cells, (1., 1.2, 1.4, 1.6), registered=True)
    assert ours["D80"] is reference["D80"] is None
    assert ours["passed"] is reference["AT16_passed"] is False
    assert ours["cells"][2]["accounting_bounds"] == reference["cells"][2]["accounting_bounds"]


def test_development_designs_never_pass():
    ps, ss = _table(6, (.85, .9, .95, .99))
    cells = [c.summarize_cell(_records(p, v), 200) for p, v in zip(ps, ss)]
    assert c.summarize_power_cells(cells, (1., 1.2, 1.4, 1.6), registered=False)["passed"] is False
    size = c.summarize_size(_records([.5] * 195 + [.01] * 5, [0.] * 200), requested=200,
                            bounds=(.02, .09), registered=False)
    assert size["cell"]["rate"] == .025 and size["passed"] is False


def test_holm_family_rule():
    result = c.holm_adjust({1: .01, 2: .04, 3: None, 4: .04})
    assert result[1]["adjusted_p"] == pytest.approx(.04)
    # Ties at .04 are ordered by extension number: E2 is rank 2, E4 rank 3.
    assert result[2]["adjusted_p"] == pytest.approx(.12)
    assert result[4]["adjusted_p"] == pytest.approx(.12)
    assert result[3] == dict(raw_p=None, holm_input=1.0, adjusted_p=1.0)
    with pytest.raises(ValueError):
        c.holm_adjust({1: 0.0})


def test_branch_b_is_a_labelled_diagnostic():
    assert c.branch_b_diagnostic(.3, None, (0., .1))["status"] == "unavailable"
    assert c.branch_b_diagnostic(.3, .2, (0., .1))["condition"] is True
    assert c.branch_b_diagnostic(.3, .2, (0., .2))["condition"] is False


def test_registered_seed_needs_explicit_gate_flag():
    with pytest.raises(c.RegisteredRunRefused):
        c.check_seed(1927, False)
    assert c.check_seed(1927, True) == 1927
    assert c.check_seed(DEV, False) == DEV


def test_stream_construction_is_the_registered_convention():
    ours = c.stream_rng(DEV, 5100, 2, 7)
    direct = np.random.Generator(np.random.PCG64(np.random.SeedSequence([DEV, 5100, 2, 7])))
    assert ours.bit_generator.state == direct.bit_generator.state
    assert math.isfinite(ours.standard_normal())
