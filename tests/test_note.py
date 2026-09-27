"""The core note is written only from evidence records, and a missing result is never a value."""
import importlib.util
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('build_note', ROOT / 'tools/build_note.py')
build_note = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_note)
LATEX = {'Delta', 'IfFileExists'}


def used_macros():
    text = (ROOT / 'paper1/core-note.tex').read_text(encoding='utf-8')
    return set(re.findall(r'\\([A-Z][A-Za-z]*)', text)) - LATEX


def with_records(monkeypatch, records):
    real = build_note.load
    monkeypatch.setattr(build_note, 'load', lambda relative: records.get(relative) if relative in build_note.GATED
                        else real(relative))


def test_the_note_uses_exactly_the_generated_numbers(monkeypatch):
    with_records(monkeypatch, {})
    assert used_macros() == set(build_note.numbers())


def test_missing_results_are_placeholders_never_values(monkeypatch):
    with_records(monkeypatch, {})
    macros = build_note.numbers()
    for name in ('ReleaseIdentity', 'GtwoStatus', 'ATfiveThirty', 'ATfiveThirtyPercent', 'Deighty',
                 'HoneS', 'HoneP', 'HoneM', 'HoneK', 'HoneRetained', 'HoneConclusion', 'HoneInterval'):
        assert macros[name].startswith(r'\pending{'), name
    assert build_note.h1_tables().startswith(r'\pending{')
    assert build_note.s2_body().startswith(r'\pending{')


def test_recorded_results_replace_every_placeholder(monkeypatch):
    comparison = dict(analysis='primary', window=40, status='ok', value=.0123, p_value=.2, eligible_episodes=7,
                      positive_components=4, retained=998)
    with_records(monkeypatch, {
        'data/raw/ABMI_acquisition.json': dict(release_title='GDP quarterly national accounts, UK: January to March 2026',
                                               release_datetime_utc='2026-06-30T06:00:00+00:00', sha256='ab' * 32),
        'audit/G2_REVIEW.json': dict(G2='passed', AT5=dict(n30_rate=.631, n1000_rate=.021), AT15=dict(rate=.045), D80=None),
        'audit/H1_RESULT.json': dict(
            primary=dict(S=.0123, p_value=.2, eligible_episodes=7, positive_changes=4, retained=998),
            episode_interval=[-.011, .034],
            interpretation=dict(conclusion='inconclusive', text='Inconclusive under the fitted AR(2) null.',
                                branch_B_condition=None),
            comparisons=[comparison, dict(comparison, analysis='trend', status='observed_not_estimable', value=None,
                                          p_value=None, retained=None)],
            episodes=[dict(onset_quarter='1973 Q3', end_quarter='1974 Q1', statistic_available=True, change=.01),
                      dict(onset_quarter='1956 Q3', end_quarter='1957 Q1', statistic_available=False, change=None)]),
        'audit/s2_verification.json': dict(sample=['1955 Q1', '2019 Q4'], rows=[
            dict(filter='linear trend', phi1=1.2, phi2=-.3, modulus=.55, period_quarters=None, c=.9, v=.33, oscillates=False),
            dict(filter='Hamilton (h=8, p=4)', phi1=1.1, phi2=-.4, modulus=.63, period_quarters=14.2, c=.7, v=.57,
                 oscillates=True)])})
    macros = build_note.numbers()
    assert not [name for name, value in macros.items() if 'pending' in value]
    assert macros['HoneS'] == '0.0123' and macros['HoneM'] == '7' and macros['GtwoStatus'] == 'passed'
    assert macros['ATfiveThirtyPercent'] == r'63\%' and macros['Deighty'].startswith('undefined')
    assert 'ab' * 8 in macros['ReleaseIdentity']
    tables = build_note.h1_tables()
    assert 'pending' not in tables and 'not eligible' in tables and 'observed not estimable' in tables
    body = build_note.s2_body()
    assert 'holds under 1 of the 2 filters' in body and 'pending' not in body


def test_text_escaping():
    assert build_note.tex('50% & a_b #1') == r'50\% \& a\_b \#1'
    assert build_note.f(-0.5, 2) == '$-$0.50' and build_note.f(None, 2) == '--'
    assert build_note.scientific(5.49e-6) == r'$5.5\times 10^{-6}$'
