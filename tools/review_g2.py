"""G2 review of the registered validation run: the frozen summary, checked by an independent replay.

The frozen checkout's own `tools/run_validation.py verify` and `summary --summary-output`
produce the official cell summary. This tool reads that summary and the store (read-only),
then replays every record with src/uc_verify/replay.py, a second implementation written from
the protocol text that shares no code with uc_core:

  * store integrity: SQLite integrity check, manifest hash, every record's checksum and
    canonical encoding, one completion-journal entry per record, and complete coverage;
  * seeding: each record's generators start from SeedSequence([seed, stream, cell, replicate])
    and end in the stored states, so exactly the registered draws were consumed;
  * AT-5: every white-noise series is regenerated bit for bit and refitted;
  * AT-15 and AT-16: every simulated series is regenerated, its rolling fits, recessions,
    fitted null and all surrogates are recomputed, and S, K and p are compared;
  * every cell rate, mean S, adjacent power comparison and D80 is recomputed.

G2 passes only when AT-1 to AT-4 passed (audit/baseline_results.json), the frozen summary
records AT-5, AT-15 and AT-16 as passed, the run is registered and complete, and the replay
agrees. Writes G2_REVIEW.json and G2_REVIEW.md; it never modifies the store.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
import zlib

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uc_verify import replay  # noqa: E402

REGISTERED_MANIFEST = '3eb8cc1330bf721349f546869ede239d8c70b6998321d814a5de3bcd55d7cbc6'
TARGETS = {'white_noise_n30': (.625, .635), 'white_noise_n1000': (.514, .526), 'size': (.02, .09)}
STATISTIC_TOLERANCE = 1e-8
INPUT_TOLERANCE = 1e-9
NEAR_TIE = 1e-9


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path, block=1 << 24):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        while chunk := source.read(block):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False, ensure_ascii=True).encode('utf-8')


class Review:
    def __init__(self, database, summary, *, limit=None, log=print):
        self.database, self.summary, self.limit, self.log = Path(database), summary, limit, log
        self.db = sqlite3.connect(f'file:{self.database.as_posix()}?mode=ro', uri=True)
        payload, stored_hash = self.db.execute('SELECT payload, sha256 FROM manifest WHERE id=1').fetchone()
        self.manifest_bytes, self.manifest = bytes(payload), json.loads(payload)
        self.manifest_hash = stored_hash
        self.plan = self.manifest['plan']
        self.cells = {c['name']: c for c in self.plan['cells']}
        self.problems = []
        self.stats = dict(records_checked=0, white_noise_refit_max_coefficient_difference=0.,
                          white_noise_classification_mismatches=0, white_noise_near_zero_discriminants=0,
                          simulation_input_max_difference=0., observed_S_max_difference=0.,
                          surrogate_statistic_max_difference=0., surrogate_status_mismatches=0,
                          surrogate_near_ties=0, p_value_mismatches=0, rng_state_mismatches=0,
                          null_coefficient_max_difference=0.)
        self.outcomes = {name: [] for name in self.cells}

    def problem(self, text):
        if len(self.problems) < 200:
            self.problems.append(text)

    # -- store integrity -------------------------------------------------------------------
    def integrity(self):
        result = dict(sqlite_integrity=self.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok',
                      manifest_checksum=sha256(self.manifest_bytes) == self.manifest_hash,
                      manifest_matches_summary=self.manifest_hash == self.summary.get('manifest_sha256'))
        journal = self.db.execute('''
            SELECT COUNT(*) FROM records r LEFT JOIN events e
              ON e.kind='record_committed' AND e.cell=r.cell AND e.replicate=r.replicate
            GROUP BY r.cell, r.replicate HAVING COUNT(e.sequence) != 1 OR MIN(e.sha256) IS NOT r.sha256''').fetchall()
        orphans = self.db.execute('''
            SELECT COUNT(*) FROM events e LEFT JOIN records r ON e.cell=r.cell AND e.replicate=r.replicate
            WHERE e.kind='record_committed' AND r.cell IS NULL''').fetchone()[0]
        result['journal_consistent'] = not journal and orphans == 0
        coverage = {}
        for name, cell in self.cells.items():
            replicates = [r for (r,) in self.db.execute('SELECT replicate FROM records WHERE cell=? ORDER BY replicate', (name,))]
            coverage[name] = replicates == list(range(cell['requested']))
        result['complete_coverage'] = coverage
        for key, value in result.items():
            if value is False or (isinstance(value, dict) and not all(value.values())):
                self.problem(f'integrity: {key}')
        return result

    def records(self, name):
        query = 'SELECT replicate, payload, sha256 FROM records WHERE cell=? ORDER BY replicate'
        if self.limit is not None:
            query += f' LIMIT {int(self.limit)}'
        for replicate, packed, checksum in self.db.execute(query, (name,)):
            raw = zlib.decompress(packed)
            record = json.loads(raw)
            if sha256(raw) != checksum or canonical(record) != raw or record.get('replicate') != replicate:
                self.problem(f'{name} {replicate}: checksum, encoding or identity')
            self.stats['records_checked'] += 1
            yield record

    def same_state(self, stored, generator, label):
        if stored != generator.bit_generator.state:
            self.stats['rng_state_mismatches'] += 1
            self.problem(f'{label}: generator state differs')

    # -- AT-5 --------------------------------------------------------------------------------
    def white_noise(self, name, batch=4000):
        cell, seed = self.cells[name], self.plan['master_seed']
        pending = []

        def flush():
            inputs = np.array([x for _, x in pending])
            phi1, phi2, intercept = replay.ols_ar2(inputs)
            d = phi1 * phi1 + 4 * phi2
            for (record, _), p1, p2, c, disc in zip(pending, phi1, phi2, intercept, d):
                ok = record['status'] == 'ok'
                self.outcomes[name].append((ok, bool(disc < 0) if ok else False, None))
                if not ok:
                    continue
                stored = record['coefficients'] + [record['intercept']]
                self.stats['white_noise_refit_max_coefficient_difference'] = max(
                    self.stats['white_noise_refit_max_coefficient_difference'],
                    float(np.max(np.abs(np.array(stored) - [p1, p2, c]))))
                if abs(disc) < 1e-10:
                    self.stats['white_noise_near_zero_discriminants'] += 1
                if bool(disc < 0) != record['complex_pair']:
                    self.stats['white_noise_classification_mismatches'] += 1
                    self.problem(f"{name} {record['replicate']}: complex classification differs")
            pending.clear()

        for record in self.records(name):
            rng = replay.generator(cell['generation_stream'], cell['cell_index'], record['replicate'], seed)
            self.same_state(record['generation_rng_before'], rng, f"{name} {record['replicate']} before")
            x = rng.standard_normal(cell['n'])
            self.same_state(record['generation_rng_after'], rng, f"{name} {record['replicate']} after")
            if record['input'] != x.tolist() or record['input_sha256'] != sha256(x.astype('<f8').tobytes()):
                self.problem(f"{name} {record['replicate']}: regenerated series differs")
            pending.append((record, x))
            if len(pending) == batch:
                flush()
        if pending:
            flush()

    # -- AT-15 and AT-16 ------------------------------------------------------------------------
    def simulation(self, name):
        cell, seed, B = self.cells[name], self.plan['master_seed'], self.plan['surrogate_attempts']
        fixed = replay.POWER_ONSETS if cell['kind'] == 'power' else None
        started = time.perf_counter()
        for count, record in enumerate(self.records(name), 1):
            label = f"{name} {record['replicate']}"
            if record.get('input') is None:
                self.problem(f"{label}: no stored input (status {record['status']})")
                self.outcomes[name].append((False, False, None))
                continue
            generation = replay.generator(cell['generation_stream'], cell['cell_index'], record['replicate'], seed)
            self.same_state(record['generation_rng_before'], generation, label + ' generation before')
            x = replay.design_series(generation, cell['kappa'], fixed or ())
            self.same_state(record['generation_rng_after'], generation, label + ' generation after')
            stored_input = np.array(record['input'])
            difference = float(np.max(np.abs(stored_input - x)))
            self.stats['simulation_input_max_difference'] = max(self.stats['simulation_input_max_difference'], difference)
            if difference > INPUT_TOLERANCE:
                self.problem(f'{label}: regenerated series differs by {difference:.3g}')
            analysis = replay.generator(cell['surrogate_stream'], cell['cell_index'], record['replicate'], seed)
            self.same_state(record['analysis_rng_before'], analysis, label + ' analysis before')
            ours = replay.comparison(stored_input, analysis, fixed_onsets=fixed, B=B)
            stored_ok = record['status'] == 'ok'
            if stored_ok:
                self.same_state(record['analysis_rng_after'], analysis, label + ' analysis after')
            self.compare(label, record, ours)
            ours_ok = ours['p_value'] is not None
            if ours_ok != stored_ok:
                self.problem(f"{label}: validity differs (stored {record['status']})")
            self.outcomes[name].append((ours_ok, ours_ok and ours['p_value'] <= .05, ours['S']))
            if count % 25 == 0:
                self.log(f'{name}: {count} records replayed, {time.perf_counter() - started:.0f} s')

    def compare(self, label, record, ours):
        stored_S, S = record.get('S'), ours['S']
        if (stored_S is None) != (S is None):
            self.problem(f'{label}: observed S availability differs')
            return
        if S is None:
            return
        self.stats['observed_S_max_difference'] = max(self.stats['observed_S_max_difference'], abs(stored_S - S))
        if abs(stored_S - S) > STATISTIC_TOLERANCE or record['observed']['eligible_onsets'] != ours['eligible_onsets']:
            self.problem(f'{label}: observed statistic or onsets differ')
        comparison = record.get('comparison')
        if not comparison or ours['stable'] is None:
            return
        null = comparison.get('null_model') or {}
        if null.get('coefficients') and ours['null']:
            gap = max(abs(a - b) for a, b in zip(null['coefficients'] + [null['intercept']], ours['null']))
            self.stats['null_coefficient_max_difference'] = max(self.stats['null_coefficient_max_difference'], gap)
            if gap > STATISTIC_TOLERANCE:
                self.problem(f'{label}: fitted null differs by {gap:.3g}')
        stored_attempts = comparison.get('attempts') or []
        if len(stored_attempts) != len(ours['attempts']):
            self.problem(f'{label}: {len(stored_attempts)} stored attempts against {len(ours["attempts"])} replayed')
            return
        for stored, mine in zip(stored_attempts, ours['attempts']):
            if stored['status'] != mine['status'] or (mine['statistic'] is not None and
                                                      stored['eligible_onsets'] != mine['eligible_onsets']):
                self.stats['surrogate_status_mismatches'] += 1
                self.problem(f"{label} draw {mine['number']}: status or onsets differ")
                continue
            if mine['statistic'] is not None:
                gap = abs(stored['statistic'] - mine['statistic'])
                self.stats['surrogate_statistic_max_difference'] = max(self.stats['surrogate_statistic_max_difference'], gap)
                if gap > STATISTIC_TOLERANCE:
                    self.problem(f"{label} draw {mine['number']}: statistic differs by {gap:.3g}")
                if abs(mine['statistic'] - S) < NEAR_TIE:
                    self.stats['surrogate_near_ties'] += 1
        if record.get('p_value') != ours['p_value'] or comparison.get('exceedances') != ours['exceedances']:
            self.stats['p_value_mismatches'] += 1
            self.problem(f'{label}: p or K differs')

    # -- cell summaries ---------------------------------------------------------------------------
    def summaries(self):
        cells = {name: replay.cell_summary(outcomes, self.cells[name]['requested'])
                 for name, outcomes in self.outcomes.items()}
        official = self.plan['mode'] == 'registered'
        if not official:  # a development run is never an acceptance test and has no D80
            return cells, dict(D80=None, kappa80=None, AT16_passed=False), dict(
                AT5_passed=False, AT15_passed=False, AT16_passed=False)
        power = replay.power_summary([cells[f'power_{j}'] for j in range(4)], n=self.cells['power_0']['requested'])
        passes = {name: cells[name]['rate'] is not None and lo <= cells[name]['rate'] <= hi
                  for name, (lo, hi) in TARGETS.items()}
        return cells, power, dict(AT5_passed=passes['white_noise_n30'] and passes['white_noise_n1000'],
                                  AT15_passed=passes['size'], AT16_passed=power['AT16_passed'])

    def agreement(self, cells, power, decisions):
        frozen, differences = self.summary, []

        def close(a, b, tolerance=1e-9):
            return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= tolerance)

        for name, mine in cells.items():
            theirs = frozen['cells'][name]
            for key in ('attempted', 'valid', 'positive'):
                if mine[key] != theirs[key]:
                    differences.append(f'{name} {key}: {theirs[key]} frozen, {mine[key]} replayed')
            for key in ('rate', 'rate_se', 'mean_S', 'mean_S_se'):
                if not close(mine[key], theirs.get(key)):
                    differences.append(f'{name} {key}: {theirs.get(key)} frozen, {mine[key]} replayed')
        theirs = frozen.get('power') or {}
        if not close(power['D80'], theirs.get('D80')) or not close(power['kappa80'], theirs.get('kappa80')):
            differences.append(f"D80: {theirs.get('D80')} frozen, {power['D80']} replayed")
        for key, value in decisions.items():
            if frozen.get(key) is not value:
                differences.append(f'{key}: {frozen.get(key)} frozen, {value} replayed')
        return differences


def baseline():
    tests = json.loads((ROOT / 'audit/baseline_results.json').read_text(encoding='utf-8'))['acceptance_tests']
    return {name: tests[name]['status'] == 'passed' for name in ('AT-1', 'AT-2', 'AT-3', 'AT-4')}


def review(database, summary_path, *, limit=None, log=print):
    summary_bytes = Path(summary_path).read_bytes()
    summary = json.loads(summary_bytes)
    work = Review(database, summary, limit=limit, log=log)
    integrity = work.integrity()
    for name, cell in work.cells.items():
        log(f'replaying {name}')
        (work.white_noise if cell['kind'] == 'white_noise' else work.simulation)(name)
    cells, power, decisions = work.summaries()
    differences = work.agreement(cells, power, decisions)
    base = baseline()
    registered = work.plan['mode'] == 'registered' and work.manifest_hash == REGISTERED_MANIFEST
    replay_agrees = not work.problems and not differences
    integrity_ok = all(v if not isinstance(v, dict) else all(v.values()) for v in integrity.values())
    frozen = {key: summary.get(key) is True for key in ('AT5_passed', 'AT15_passed', 'AT16_passed')}
    passed = (registered and limit is None and integrity_ok and replay_agrees and all(base.values())
              and all(frozen.values()))
    frozen_power = summary.get('power') or {}
    result = dict(
        record_type='G2 review', G2='passed' if passed else 'not passed',
        AT1_AT4_passed=all(base.values()), **frozen,
        D80=frozen_power.get('D80'),
        AT5=dict(n30_rate=summary['cells']['white_noise_n30']['rate'],
                 n30_wilson=summary['cells']['white_noise_n30']['rate_wilson'],
                 n1000_rate=summary['cells']['white_noise_n1000']['rate'],
                 n1000_wilson=summary['cells']['white_noise_n1000']['rate_wilson'],
                 targets=dict(n30=TARGETS['white_noise_n30'], n1000=TARGETS['white_noise_n1000'])),
        AT15=dict(rate=summary['cells']['size']['rate'], rejected=summary['cells']['size'].get('rejected'),
                  wilson=summary['cells']['size']['rate_wilson'], target=TARGETS['size']),
        AT16=dict(cells=frozen_power.get('cells'), adjacent_comparisons=frozen_power.get('adjacent_comparisons'),
                  decrease_flags=frozen_power.get('decrease_flags'), crossing=frozen_power.get('crossing'),
                  kappa80=frozen_power.get('kappa80')),
        baseline=base,
        provenance=dict(database=str(Path(database).name), database_sha256=file_sha256(database),
                        summary_sha256=sha256(summary_bytes), manifest_sha256=work.manifest_hash,
                        manifest_is_registered=registered, identity=work.manifest.get('identity'),
                        registration_receipt_sha256=work.manifest.get('registration_receipt_sha256')),
        independent_replay=dict(module='src/uc_verify/replay.py', complete=limit is None, agrees=replay_agrees,
                                integrity=integrity, statistics=work.stats, problems=work.problems,
                                summary_differences=differences, replayed_decisions=decisions,
                                replayed_D80=power['D80'], replayed_kappa80=power['kappa80']),
        scope=('AT-5, AT-15 and AT-16 assess this registered synthetic design only; passing does not establish '
               'universal calibration. D80 is a Monte Carlo point diagnostic, not a confidence bound.'))
    return result


def markdown(result):
    at5, at15, at16 = result['AT5'], result['AT15'], result['AT16']
    fmt = lambda v, d=4: '-' if v is None else f'{v:.{d}f}'
    lines = ['# G2 review', '',
             f"**G2 {result['G2']}.** Generated by `tools/review_g2.py` from the frozen validation summary "
             f"(SHA-256 `{result['provenance']['summary_sha256'][:16]}`) and an independent replay of every record.", '',
             '| Check | Result | Target | Outcome |', '|---|---|---|---|',
             f"| AT-1 to AT-4 (estimators) | audit/baseline_results.json | original tolerances | {'passed' if result['AT1_AT4_passed'] else 'not passed'} |",
             f"| AT-5, n = 30 | {fmt(at5['n30_rate'], 5)} | 0.625-0.635 | {'passed' if result['AT5_passed'] else 'not passed'} |",
             f"| AT-5, n = 1,000 | {fmt(at5['n1000_rate'], 5)} | 0.514-0.526 | |",
             f"| AT-15 size | {fmt(at15['rate'], 3)} | 0.02-0.09 | {'passed' if result['AT15_passed'] else 'not passed'} |",
             f"| AT-16 power | see below | no flagged decrease; all cells valid | {'passed' if result['AT16_passed'] else 'not passed'} |",
             '', '| kappa | Rejection rate | Mean S |', '|---|---|---|']
    for cell in at16['cells'] or []:
        lines.append(f"| {cell['kappa']} | {fmt(cell.get('rate'), 3)} | {fmt(cell.get('mean_S'))} |")
    replay_record = result['independent_replay']
    stats = replay_record['statistics']
    lines += ['', f"D80 = {fmt(result['D80'])} (first raw crossing; kappa80 = {fmt(at16['kappa80'], 3)}).", '',
              '## Independent replay', '',
              f"`src/uc_verify/replay.py` shares no code with `uc_core`. It regenerated all {stats['records_checked']:,} records "
              f"from their stream coordinates, refitted every series, redrew every surrogate and recomputed every summary. "
              f"Agreement: **{'yes' if replay_record['agrees'] else 'no'}**.", '',
              f"- Largest white-noise coefficient difference: {stats['white_noise_refit_max_coefficient_difference']:.2e}; "
              f"classification mismatches: {stats['white_noise_classification_mismatches']}.",
              f"- Largest simulated-input difference: {stats['simulation_input_max_difference']:.2e}; observed S: "
              f"{stats['observed_S_max_difference']:.2e}; surrogate S: {stats['surrogate_statistic_max_difference']:.2e}.",
              f"- p-value mismatches: {stats['p_value_mismatches']}; surrogate status mismatches: "
              f"{stats['surrogate_status_mismatches']}; generator-state mismatches: {stats['rng_state_mismatches']}; "
              f"near ties within 1e-9: {stats['surrogate_near_ties']}.",
              f"- Summary differences: {len(replay_record['summary_differences'])}; problems: {len(replay_record['problems'])}.",
              '', result['scope'], '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--summary', type=Path, required=True, help='final summary written by the frozen CLI')
    parser.add_argument('--output-directory', type=Path, default=ROOT / 'audit')
    parser.add_argument('--limit', type=int, help='replay only the first N records per cell; such a review cannot pass G2')
    args = parser.parse_args()
    result = review(args.database, args.summary, limit=args.limit, log=lambda text: print(text, flush=True))
    args.output_directory.mkdir(parents=True, exist_ok=True)
    (args.output_directory / 'G2_REVIEW.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    (args.output_directory / 'G2_REVIEW.md').write_text(markdown(result), encoding='utf-8', newline='\n')
    print(json.dumps({k: result[k] for k in ('G2', 'AT1_AT4_passed', 'AT5_passed', 'AT15_passed', 'AT16_passed', 'D80')}))
    print(f"independent replay agrees: {result['independent_replay']['agrees']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
