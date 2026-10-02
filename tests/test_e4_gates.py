"""The gate loader knows E4 as an extension with its own runner (E2 has its own as well, see test_e2_gates.py);
E1 and E3 keep theirs."""
import pytest

from uc_ext_official import gates


def test_four_extensions_each_with_its_runner():
    assert gates.EXTENSIONS == ("e1", "e2", "e3", "e4")
    assert gates.runner_path("e1") == gates.runner_path("e3") == "tools/run_e_checks.py"
    assert gates.runner_path("e4") == "tools/run_e4_checks.py"
    assert gates.extension_name("e4") == "E4"
    assert gates.x3_record_path("e4") == "audit/E4_X3.json"
    assert gates.registration_record_path("e4") == "audit/E4_REGISTRATION.json"
    with pytest.raises(ValueError):
        gates.runner_path("e5")


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


E1_FROZEN = "c" * 64


def _patched(monkeypatch, *, e1_now=E1_FROZEN, e1_record=E1_FROZEN):
    """Identity and E1 X.3 record as constructed values: `seen` lists the extensions asked for."""
    seen = []

    def identity(root, extension="e1"):
        seen.append(extension)
        return dict(code_sha256="a" * 64, identity={}, e1_code_sha256=e1_now)
    monkeypatch.setattr(gates, "code_identity", identity)
    monkeypatch.setattr(gates, "check_x3", lambda root, extension: dict(code_sha256=e1_record, record_path="E1_X3"))
    return seen


def test_the_code_freeze_names_the_extension_of_the_x3_record(monkeypatch):
    seen = _patched(monkeypatch)
    gates.check_code_frozen("unused", dict(extension="E4", code_sha256="a" * 64, e1_code_sha256=E1_FROZEN))
    gates.check_code_frozen("unused", dict(code_sha256="a" * 64))
    gates.check_code_frozen("unused", dict(extension="E1", code_sha256="a" * 64), extension="e3")
    assert seen == ["e4", "e1", "e3"]


def test_an_e4_code_freeze_needs_the_e1_part_to_be_the_frozen_e1_code(monkeypatch):
    x3 = dict(extension="E4", code_sha256="a" * 64, e1_code_sha256=E1_FROZEN)
    _patched(monkeypatch)
    assert gates.check_code_frozen("unused", x3, "e4")["e1_code_sha256"] == E1_FROZEN
    _patched(monkeypatch, e1_now="d" * 64)
    with pytest.raises(gates.GateClosed, match="E1 part of the E4 code identity.*the code now running"):
        gates.check_code_frozen("unused", x3, "e4")
    _patched(monkeypatch)
    for record in (dict(x3, e1_code_sha256="d" * 64), {k: v for k, v in x3.items() if k != "e1_code_sha256"}):
        with pytest.raises(gates.GateClosed, match="E1 part of the E4 code identity.*the E4 X.3 record"):
            gates.check_code_frozen("unused", record, "e4")
    _patched(monkeypatch, e1_now="d" * 64, e1_record="e" * 64)
    with pytest.raises(gates.GateClosed, match="the code now running and in the E4 X.3 record"):
        gates.check_code_frozen("unused", dict(x3, e1_code_sha256="d" * 64), "e4")


def test_the_e4_hash_check_comes_first_and_e1_and_e3_do_not_read_the_e1_record(monkeypatch):
    _patched(monkeypatch, e1_now="d" * 64)
    with pytest.raises(gates.GateClosed, match="differs from the code that ran"):
        gates.check_code_frozen("unused", dict(extension="E4", code_sha256="b" * 64, e1_code_sha256="d" * 64), "e4")
    calls = []
    monkeypatch.setattr(gates, "check_x3", lambda root, extension: calls.append(extension) or dict(code_sha256="0"))
    for extension in ("e1", "e3"):
        gates.check_code_frozen("unused", dict(extension=extension.upper(), code_sha256="a" * 64), extension)
    assert calls == []


def test_the_frozen_e1_code_is_read_from_the_committed_e1_x3_record(monkeypatch, tmp_path):
    asked = []
    _patched(monkeypatch)
    monkeypatch.setattr(gates, "check_x3", lambda root, extension: asked.append((root, extension))
                        or dict(code_sha256=E1_FROZEN))
    gates.check_code_frozen(tmp_path, dict(extension="E4", code_sha256="a" * 64, e1_code_sha256=E1_FROZEN), "e4")
    assert asked == [(tmp_path, "e1")]
