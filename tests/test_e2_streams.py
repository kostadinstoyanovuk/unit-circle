"""E2 Annex A streams: development runs stay off the registered seed and ids; registered ids need the gate flag.

Only refusals use the registered seed 1927 or a registered stream id; no random number is drawn from them.
"""
import numpy as np
import pytest

from uc_core.constants import MASTER_SEED
from uc_e2 import analysis, constants, streams, synthetic
from uc_ext import common as c

DEV = streams.DEVELOPMENT_SEED


def test_development_ids_are_the_annex_a_ids_shifted_by_a_fixed_offset_and_avoid_every_registered_id():
    assert DEV == 20260930 and streams.DEVELOPMENT_OFFSET == 4000
    assert streams.REGISTERED_STREAM_IDS == constants.STREAM_IDS
    assert streams.DEVELOPMENT_STREAM_IDS == {name: i + 4000 for name, i in constants.STREAM_IDS.items()}
    development = set(streams.DEVELOPMENT_STREAM_IDS.values()) | {streams.DEVELOPMENT_AT12_STREAM}
    assert min(development) >= streams.DEVELOPMENT_FLOOR
    assert not development & set(streams.REGISTERED_IDS_TO_AVOID)
    assert set(constants.STREAM_IDS.values()) <= set(streams.REGISTERED_IDS_TO_AVOID)
    assert streams.stream_ids(DEV) == streams.DEVELOPMENT_STREAM_IDS
    assert streams.stream_ids(MASTER_SEED) == constants.STREAM_IDS
    assert streams.at12_stream(DEV) == 9012 and streams.at12_stream(MASTER_SEED) == constants.AT12_STREAM == 2012


def test_generators_are_seed_sequences_of_the_four_coordinates():
    expected = np.random.Generator(np.random.PCG64(np.random.SeedSequence([DEV, 9220, 3, 7])))
    assert streams.stream_rng(DEV, 9220, 3, 7).bit_generator.state == expected.bit_generator.state


@pytest.mark.parametrize("seed, stream, flag", [
    (MASTER_SEED, 5220, False),   # registered seed without the gate flag
    (DEV, 5220, False),           # registered id under a development seed
    (DEV, 5220, True),            # registered id under a development seed, even with the flag
    (MASTER_SEED, 9220, True),    # registered seed with a development id
    (DEV, 2012, False),           # AT-12's registered stream under a development seed
    (DEV, 8999, False),           # development ids start at 9000
])
def test_registered_coordinates_are_refused_outside_a_gated_registered_run(seed, stream, flag):
    with pytest.raises(streams.RegisteredRunRefused):
        streams.stream_rng(seed, stream, allow_registered=flag)


def test_the_refusal_is_also_the_shared_refusal_class():
    assert issubclass(streams.RegisteredRunRefused, c.RegisteredRunRefused)
    with pytest.raises(c.RegisteredRunRefused):
        streams.check_seed(MASTER_SEED)
    assert streams.check_seed(MASTER_SEED, allow_registered=True) == MASTER_SEED
    with pytest.raises(ValueError):
        streams.check_seed(True)


def test_registered_seed_is_refused_by_every_entry_point_without_the_gate_flag():
    x = np.zeros((constants.N_OBS, constants.K))
    for call in (lambda: synthetic.size_replicate(0, master_seed=MASTER_SEED, B=2),
                 lambda: synthetic.power_replicate(0, 0, master_seed=MASTER_SEED, B=2, onsets=(77, 148)),
                 lambda: synthetic.prerequisite_fixture(master_seed=MASTER_SEED),
                 lambda: synthetic.x3_input("size", 0, 0, master_seed=MASTER_SEED),
                 lambda: synthetic.run_size_check(master_seed=MASTER_SEED, n_series=1, B=2),
                 lambda: analysis.analyze(x, master_seed=MASTER_SEED, B=2)):
        with pytest.raises(streams.RegisteredRunRefused):
            call()


def test_development_records_use_the_development_ids():
    size = synthetic.size_replicate(0, master_seed=DEV, B=2)
    assert size["generation_rng_before"] == streams.stream_rng(DEV, 9220, 0, 0).bit_generator.state
    assert size["analysis_rng_before"] == streams.stream_rng(DEV, 9221, 0, 0).bit_generator.state
    record = synthetic.prerequisite_fixture(master_seed=DEV)
    assert record["at12"]["seed"] == [DEV, 9012]
