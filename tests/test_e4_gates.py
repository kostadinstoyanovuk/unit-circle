"""The gate loader knows E4 as a third extension with its own runner; E1 and E3 keep theirs."""
import pytest

from uc_ext_official import gates


def test_three_extensions_each_with_its_runner():
    assert gates.EXTENSIONS == ("e1", "e3", "e4")
    assert gates.runner_path("e1") == gates.runner_path("e3") == "tools/run_e_checks.py"
    assert gates.runner_path("e4") == "tools/run_e4_checks.py"
    assert gates.extension_name("e4") == "E4"
    assert gates.x3_record_path("e4") == "audit/E4_X3.json"
    assert gates.registration_record_path("e4") == "audit/E4_REGISTRATION.json"
    with pytest.raises(ValueError):
        gates.runner_path("e2")


def test_a_missing_e4_runner_is_a_gate_refusal(tmp_path):
    with pytest.raises(gates.GateClosed, match="run_e4_checks.py is missing"):
        gates.load_runner(tmp_path, "e4")
    with pytest.raises(gates.GateClosed, match="run_e_checks.py is missing"):
        gates.load_runner(tmp_path)


def _record(**changes):
    record = dict(record_type="E4 X.3 official synthetic checks (prereg/E4.md section 11; Annex B, X.3)",
                  extension="E4", X3="passed", size_passed=True, power_passed=True, mode="registered",
                  master_seed=1927, n_series=200, B=1000, kappas=[1.0, 1.2, 1.4, 1.6], D80=None,
                  code_sha256="a" * 64)
    record.update(changes)
    return record


def test_an_e4_x3_record_needs_the_registered_design_and_both_passes():
    assert gates.validate_x3_record(_record(), "e4")["extension"] == "E4"
    for bad in (dict(power_passed=False), dict(X3="failed"), dict(extension="E1"), dict(B=999), dict(n_series=100),
                dict(master_seed=20260930), dict(kappas=[1.0, 1.2, 1.4]), dict(code_sha256="xyz")):
        with pytest.raises(gates.GateClosed, match="not recorded as passed"):
            gates.validate_x3_record(_record(**bad), "e4")
    record = _record()
    del record["D80"]
    with pytest.raises(gates.GateClosed, match="D80"):
        gates.validate_x3_record(record, "e4")


def test_the_code_freeze_names_the_extension_of_the_x3_record(monkeypatch):
    seen = []

    def identity(root, extension="e1"):
        seen.append(extension)
        return dict(code_sha256="a" * 64, identity={})
    monkeypatch.setattr(gates, "code_identity", identity)
    gates.check_code_frozen("unused", dict(extension="E4", code_sha256="a" * 64))
    gates.check_code_frozen("unused", dict(code_sha256="a" * 64))
    gates.check_code_frozen("unused", dict(extension="E1", code_sha256="a" * 64), extension="e3")
    assert seen == ["e4", "e1", "e3"]
