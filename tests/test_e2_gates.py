"""The gate loader and the X.3 gates know E2: its own runner, a passed prerequisite record beside the size and
power checks (as E3's), and the E1 part of its code identity (identity option e1-superset, as E4's).
Constructed records and identities only."""
from pathlib import Path

import pytest

from uc_ext_official import gates

TREE = Path(__file__).resolve().parents[1]
E1_FROZEN = "c" * 64


def test_e2_has_its_own_runner_and_record_paths():
    assert "e2" in gates.EXTENSIONS
    assert gates.runner_path("e2") == "tools/run_e2_checks.py"
    assert gates.extension_name("e2") == "E2"
    assert gates.x3_record_path("e2") == "audit/E2_X3.json"
    assert gates.registration_record_path("e2") == "audit/E2_REGISTRATION.json"
    assert gates.PREREQUISITE_EXTENSIONS == ("e2", "e3")
    assert gates.E1_SUPERSET_EXTENSIONS == ("e2", "e4")


def test_a_missing_e2_runner_is_a_gate_refusal(tmp_path):
    with pytest.raises(gates.GateClosed, match="run_e2_checks.py is missing"):
        gates.load_runner(tmp_path, "e2")


def test_the_e2_runner_is_loaded_from_the_research_root():
    assert gates.load_runner(TREE, "e2").HERE == TREE


def _record(**changes):
    record = dict(record_type="E2 X.3 official synthetic checks (prereg/E2.md section 11; Annex B, X.3)",
                  extension="E2", X3="passed", size_passed=True, power_passed=True, prerequisite_passed=True,
                  mode="registered", master_seed=1927, n_series=200, B=1000, kappas=[1.0, 1.2, 1.4, 1.6], D80=None,
                  code_sha256="a" * 64)
    record.update(changes)
    return record


def test_an_e2_x3_record_needs_the_registered_design_and_all_three_passes():
    assert gates.validate_x3_record(_record(), "e2")["extension"] == "E2"
    for bad in (dict(size_passed=False), dict(power_passed=False), dict(prerequisite_passed=False),
                dict(prerequisite_passed=None), dict(X3="failed"), dict(extension="E4"), dict(B=999),
                dict(n_series=100), dict(master_seed=20260930), dict(kappas=[1.0, 1.2, 1.4]),
                dict(code_sha256="xyz")):
        with pytest.raises(gates.GateClosed, match="not recorded as passed"):
            gates.validate_x3_record(_record(**bad), "e2")
    record = _record()
    del record["prerequisite_passed"]
    with pytest.raises(gates.GateClosed, match="prerequisite_passed is not true"):
        gates.validate_x3_record(record, "e2")
    record = _record()
    del record["D80"]
    with pytest.raises(gates.GateClosed, match="D80"):
        gates.validate_x3_record(record, "e2")


def test_records_of_e1_and_e4_are_not_asked_for_a_prerequisite():
    for extension in ("e1", "e4"):
        name = extension.upper()
        record = _record(extension=name, record_type=f"{name} X.3 official synthetic checks")
        del record["prerequisite_passed"]
        assert gates.validate_x3_record(record, extension) is record


def _patched(monkeypatch, *, e1_now=E1_FROZEN, e1_record=E1_FROZEN):
    """Identity and E1 X.3 record as constructed values: `seen` lists the extensions asked for."""
    seen = []

    def identity(root, extension="e1"):
        seen.append(extension)
        return dict(code_sha256="a" * 64, identity={}, e1_code_sha256=e1_now)
    monkeypatch.setattr(gates, "code_identity", identity)
    monkeypatch.setattr(gates, "check_x3", lambda root, extension: dict(code_sha256=e1_record, record_path="E1_X3"))
    return seen


def test_the_e2_code_freeze_asks_for_the_e2_identity_and_the_frozen_e1_code(monkeypatch):
    seen = _patched(monkeypatch)
    x3 = dict(extension="E2", code_sha256="a" * 64, e1_code_sha256=E1_FROZEN)
    assert gates.check_code_frozen("unused", x3)["e1_code_sha256"] == E1_FROZEN
    assert gates.check_code_frozen("unused", x3, "e2")["code_sha256"] == "a" * 64
    assert seen == ["e2", "e2"]


def test_an_e2_code_freeze_needs_the_e1_part_to_be_the_frozen_e1_code(monkeypatch):
    x3 = dict(extension="E2", code_sha256="a" * 64, e1_code_sha256=E1_FROZEN)
    _patched(monkeypatch, e1_now="d" * 64)
    with pytest.raises(gates.GateClosed, match="E1 part of the E2 code identity.*the code now running"):
        gates.check_code_frozen("unused", x3, "e2")
    _patched(monkeypatch)
    for record in (dict(x3, e1_code_sha256="d" * 64), {k: v for k, v in x3.items() if k != "e1_code_sha256"}):
        with pytest.raises(gates.GateClosed, match="E1 part of the E2 code identity.*the E2 X.3 record"):
            gates.check_code_frozen("unused", record, "e2")
    _patched(monkeypatch, e1_now="d" * 64, e1_record="e" * 64)
    with pytest.raises(gates.GateClosed, match="the code now running and in the E2 X.3 record"):
        gates.check_code_frozen("unused", dict(x3, e1_code_sha256="d" * 64), "e2")


def test_the_e2_hash_check_comes_first(monkeypatch):
    _patched(monkeypatch, e1_now="d" * 64)
    with pytest.raises(gates.GateClosed, match="differs from the code that ran"):
        gates.check_code_frozen("unused", dict(extension="E2", code_sha256="b" * 64, e1_code_sha256="d" * 64), "e2")


def test_the_e1_check_still_names_e4_for_an_e4_record(monkeypatch):
    _patched(monkeypatch, e1_now="d" * 64)
    with pytest.raises(gates.GateClosed, match="E1 part of the E4 code identity"):
        gates.check_code_frozen("unused", dict(extension="E4", code_sha256="a" * 64, e1_code_sha256="d" * 64))


def test_the_e2_code_location_includes_uc_e2():
    assert set(gates.check_code_location(TREE, "e2")) == {"uc_core", "uc_ext", "uc_ext_official", "uc_e2"}
    assert "uc_e2" not in gates.check_code_location(TREE)
    with pytest.raises(gates.GateClosed, match="imported from"):
        gates.check_code_location(TREE / "elsewhere", "e2")
