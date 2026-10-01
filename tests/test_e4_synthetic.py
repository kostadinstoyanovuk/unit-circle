"""prereg/E4.md section 11 (truncation-only synthetic vintages) and Annex A's synthetic streams.
Development runs on constructed data only (seed 20260930, stream ids from 9000, small B); not the registered X.3."""
import math

import numpy as np
import pytest

from e4_artificial import DEV_SEED
from uc_core.validation_design import h1_design_series
from uc_e4 import synthetic as Y
from uc_e4.procedure import EpisodeInput, compare
from uc_e4.streams import DEVELOPMENT_STREAMS as DS, REGISTERED_STREAMS, RegisteredRunRefused, stream_rng
from uc_ext import common as c

B = 6


def test_truncations_are_positions_zero_to_r_minus_one_of_the_same_series():
    x = h1_design_series(stream_rng(DEV_SEED, DS.size_generation, 0, 0), kappa=1.0)
    assert len(x) == 259 and Y.ONSETS == (49, 99, 149, 199, 249)
    v = Y.truncation_vintages(x)
    assert [len(a) for a in v] == [49, 99, 149, 199, 249]
    assert all(np.array_equal(a, x[:len(a)]) for a in v)
    a = v[0]
    a[0] = 999.0
    assert x[0] != 999.0                                     # the vintages are copies
    with pytest.raises(ValueError):
        Y.truncation_vintages(x[:100])


@pytest.mark.parametrize("kappa", (1.0, 1.2, 1.6))
def test_generator_is_h1s_with_the_planted_signal_in_the_eight_positions_before_each_onset(kappa):
    rng = stream_rng(DEV_SEED, DS.power_generation, 1, 3)
    x = h1_design_series(rng, kappa=kappa)
    ref = stream_rng(DEV_SEED, DS.power_generation, 1, 3)
    ref.standard_normal(2)
    noise = ref.normal(0, 3.5, size=257)
    active = np.zeros(259, dtype=bool)
    for r in Y.ONSETS:
        active[r - 8:r] = True
    for t in range(2, 259):
        a, b = (kappa * 0.3, kappa ** 2 * 0.1) if active[t] else (0.3, 0.1)
        intercept = 2.5 * (1 - a - b) if active[t] and kappa != 1.0 else 1.5
        assert x[t] == pytest.approx(intercept + a * x[t - 1] + b * x[t - 2] + noise[t - 2], rel=0, abs=1e-12)
    assert active.sum() == 40                                 # five signals of eight positions, none overlapping


def test_size_replicate_follows_the_registered_stream_coordinates():
    rec = Y.size_replicate(2, master_seed=DEV_SEED, streams=DS, B=B)
    x = h1_design_series(stream_rng(DEV_SEED, DS.size_generation, 0, 2), kappa=1.0)
    eps = [EpisodeInput(j, v) for j, v in enumerate(Y.truncation_vintages(x))]
    direct = compare(eps, {j: stream_rng(DEV_SEED, DS.size_null, j, 2) for j in range(5)}, B=B)
    assert rec["input"] == x.tolist() and rec["S"] == direct.primary.observed.value
    assert rec["p_value"] == direct.primary.p_value and rec["status"] == "ok"
    assert rec["cell"] == "size" and rec["replicate"] == 2 and rec["surrogate_attempted"] == B
    assert Y.size_replicate(2, master_seed=DEV_SEED, streams=DS, B=B) == rec        # determinism


def test_power_replicate_follows_the_registered_stream_coordinates():
    rec = Y.power_replicate(2, 1, master_seed=DEV_SEED, streams=DS, B=B)
    x = h1_design_series(stream_rng(DEV_SEED, DS.power_generation, 2, 1), kappa=1.4)
    eps = [EpisodeInput(j, v) for j, v in enumerate(Y.truncation_vintages(x))]
    direct = compare(eps, {j: stream_rng(DEV_SEED, DS.power_null, 20 + j, 1) for j in range(5)}, B=B)   # 10 * kappa index + j
    assert rec["input"] == x.tolist() and rec["kappa"] == 1.4
    assert rec["S"] == direct.primary.observed.value and rec["p_value"] == direct.primary.p_value


def test_five_episodes_are_all_structurally_eligible_and_use_the_whole_fixed_window():
    rec = Y.size_replicate(0, master_seed=DEV_SEED, streams=DS, B=B)
    obs = rec["observed"]
    assert obs["eligible_onsets"] == [0, 1, 2, 3, 4] and len(obs["components"]) == 5
    assert rec["surrogate_retained"] == B and rec["surrogate_no_episode"] == 0 and rec["surrogate_failed"] == 0


def test_records_feed_the_shared_summaries_and_development_runs_cannot_pass():
    size = Y.run_size_check(master_seed=DEV_SEED, streams=DS, n_series=3, B=B)
    cell = size["summary"]["cell"]
    assert cell["requested"] == 3 and cell["valid"] == 3 and cell["rate"] == cell["rejected"] / 3
    assert size["summary"]["passed"] is False and size["summary"]["registered_design"] is False
    power = Y.run_power_check(master_seed=DEV_SEED, streams=DS, n_series=2, B=B)
    rows = power["summary"]["cells"]
    assert [r["kappa"] for r in rows] == [1.0, 1.2, 1.4, 1.6] and all(r["valid"] == 2 for r in rows)
    assert power["summary"]["passed"] is False
    assert len(power["records"]) == 8


def test_a_failed_series_is_kept_as_a_record_not_dropped(monkeypatch):
    def boom(*args, **kwargs):
        raise FloatingPointError("forced")
    monkeypatch.setattr(Y, "compare", boom)
    rec = Y.size_replicate(0, master_seed=DEV_SEED, streams=DS, B=B)
    assert rec["status"] == "comparison_failed" and "forced" in rec["error"] and rec["p_value"] is None
    assert c.summarize_cell([rec], 1)["valid"] == 0


def test_registered_coordinates_need_the_gate_flag():
    with pytest.raises(RegisteredRunRefused):
        Y.size_replicate(0, master_seed=1927, streams=REGISTERED_STREAMS, B=B)
    with pytest.raises(RegisteredRunRefused):
        Y.run_power_check(master_seed=DEV_SEED, streams=REGISTERED_STREAMS, n_series=1, B=B)
    assert Y._registered(1927, REGISTERED_STREAMS, 200, 1000) and not Y._registered(DEV_SEED, DS, 200, 1000)
