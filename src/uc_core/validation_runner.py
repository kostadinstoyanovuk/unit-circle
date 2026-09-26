"""Bounded execution of the H1 design; development runs cannot pass acceptance."""
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime
import importlib.metadata
import math
from pathlib import Path
import platform
import subprocess
import time

import numpy as np

from .ar import fit_ols
from .constants import POWER_KAPPAS, POWER_ONSETS, STREAM_IDS
from .h1 import fixed_date_test
from . import surrogate as s
from .validation_design import h1_design_series, summarize_power, wilson_interval
from .validation_store import canonical, digest, IntegrityError

NUMERIC_ERRORS = (ValueError, FloatingPointError, np.linalg.LinAlgError)
DEVELOPMENT_MASTER_SEED = 20260926


def make_plan(mode):
    if mode not in ('development', 'registered'):
        raise ValueError('Select development or registered mode explicitly')
    official = mode == 'registered'
    cells = []
    for n, count in ((30, 100000), (1000, 60000)):
        name = f'white_noise_n{n}'
        cells.append(dict(name=name, kind='white_noise', n=n,
                          requested=count if official else 4,
                          generation_stream=STREAM_IDS[name], cell_index=0))
    cells.append(dict(name='size', kind='size', n=259, kappa=1.,
                      requested=200 if official else 2, cell_index=0,
                      generation_stream=STREAM_IDS['size_generation'],
                      surrogate_stream=STREAM_IDS['size_null']))
    for cell, kappa in enumerate(POWER_KAPPAS):
        cells.append(dict(name=f'power_{cell}', kind='power', n=259, kappa=kappa,
                          requested=200 if official else 2, cell_index=cell,
                          generation_stream=STREAM_IDS['power_generation'],
                          surrogate_stream=STREAM_IDS['power_null']))
    return dict(schema_version=1, mode=mode,
                master_seed=1927 if official else DEVELOPMENT_MASTER_SEED,
                surrogate_attempts=1000 if official else 8, cells=cells)


def _git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()


def environment_identity(root):
    root = Path(root)
    names = sorted(str(p.relative_to(root)).replace('\\', '/')
                   for p in (root / 'src/uc_core').glob('*.py'))
    names += ['tools/run_validation.py', 'tools/verify_validation_runner.py',
              'prereg/H1.md', 'requirements.lock']
    versions = {}
    for line in (root / 'requirements.lock').read_text().splitlines():
        if '==' in line and not line.startswith('#'):
            name, version = line.strip().split('==')
            versions[name] = importlib.metadata.version(name)
            if versions[name] != version:
                raise IntegrityError(f'Installed dependency differs from lock: {name}')
    return dict(commit=_git(root, 'rev-parse', 'HEAD'),
                dirty=bool(_git(root, 'status', '--porcelain')),
                python=platform.python_version(), platform=platform.platform(),
                machine=platform.machine(), numpy_runtime=str(np.__config__.CONFIG),
                packages=versions,
                source_sha256={name: digest((root / name).read_bytes()) for name in names})


def verify_registration(root, receipt):
    """Fail closed on a pending receipt; receipt evidence is independently audited."""
    root = Path(root)
    if (receipt.get('G1') != 'passed' or
            receipt.get('anonymous_api_check', {}).get('public_status_verified') is not True or
            receipt.get('anonymous_api_check', {}).get('status_code') != 200 or
            receipt.get('public_immutable_verified') is not True or
            receipt.get('archived_attachment_bytes_verified') is not True or
            receipt.get('prereg_H1_tag') != 'prereg-H1'):
        raise IntegrityError('G1 is not verified; official experiments remain disabled')
    expected = receipt.get('expected_attachment_sha256', {})
    if (set(expected) != {'H1.md', 'H1_protocol.pdf', 'H1_OSF_responses.md',
                          'H1_supporting_materials.zip', 'H1_submission_manifest.json'} or
            receipt.get('archived_attachment_sha256') != expected):
        raise IntegrityError('All five archived attachment hashes must match the submission')
    for key in ('public_registration_timestamp_utc', 'public_first_verified_at_utc'):
        try:
            timestamp = datetime.fromisoformat(receipt[key].replace('Z', '+00:00'))
            if timestamp.utcoffset() is None:
                raise ValueError('Timezone absent')
        except (KeyError, AttributeError, ValueError, TypeError) as error:
            raise IntegrityError('Verified public registration timestamps are required') from error
    protocol_hash = digest((root / 'prereg/H1.md').read_bytes())
    if receipt.get('expected_attachment_sha256', {}).get('H1.md') != protocol_hash:
        raise IntegrityError('Current protocol differs from the registration receipt')
    tagged = subprocess.check_output(['git', 'show', 'prereg-H1:prereg/H1.md'], cwd=root)
    if digest(tagged) != protocol_hash:
        raise IntegrityError('Tagged protocol differs from submitted bytes')
    if _git(root, 'cat-file', '-t', 'refs/tags/prereg-H1') != 'tag':
        raise IntegrityError('The supporting registration tag must be annotated')
    local_tag = _git(root, 'rev-parse', 'refs/tags/prereg-H1')
    remote_tag = _git(root, 'ls-remote', 'origin', 'refs/tags/prereg-H1').split()
    if not remote_tag or remote_tag[0] != local_tag:
        raise IntegrityError('Supporting registration tag is not published identically')
    return digest(canonical(receipt))


def make_manifest(root, mode, receipt=None):
    plan = make_plan(mode)
    gate = verify_registration(root, receipt or {}) if mode == 'registered' else None
    identity = environment_identity(root)
    if mode == 'registered' and (identity['dirty'] or identity['python'] != '3.12.14'):
        raise IntegrityError('Official execution requires a clean commit and Python 3.12.14')
    return dict(plan=plan, identity=identity, registration_receipt_sha256=gate)


def serial(value):
    if is_dataclass(value):
        return serial(asdict(value))
    if isinstance(value, dict):
        return {key: serial(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [serial(item) for item in value]
    if isinstance(value, np.ndarray):
        return serial(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    return value


def _rng(plan, stream, cell, replicate):
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(
        [plan['master_seed'], stream, cell, replicate])))


def compute_replicate(plan, cell, replicate):
    """One deterministic record. Caller enforces registration and storage gates."""
    generation = _rng(plan, cell['generation_stream'], cell['cell_index'], replicate)
    analysis = (_rng(plan, cell['surrogate_stream'], cell['cell_index'], replicate)
                if cell['kind'] != 'white_noise' else None)
    result = dict(cell=cell['name'], replicate=replicate, status='generation_failed',
                  input=None, input_sha256=None, generation_rng_before=deepcopy(generation.bit_generator.state),
                  analysis_rng_before=deepcopy(analysis.bit_generator.state) if analysis else None,
                  S=None, p_value=None, comparison=None, error=None,
                  surrogate_requested=plan['surrogate_attempts'] if analysis else 0,
                  surrogate_attempted=0, surrogate_retained=0,
                  surrogate_no_episode=0, surrogate_failed=0,
                  surrogate_exceedance_rate=None, surrogate_exceedance_wilson=None)
    try:
        values = (generation.standard_normal(cell['n']) if cell['kind'] == 'white_noise'
                  else h1_design_series(generation, kappa=cell['kappa']))
        result.update(input=values.tolist(), input_sha256=digest(values.astype('<f8').tobytes()))
        if cell['kind'] == 'white_noise':
            result['status'] = 'fit_failed'
            fit = fit_ols(values)
            result.update(status='ok', coefficients=fit.coefficients, intercept=fit.intercept,
                          discriminant=fit.diagnostics.discriminant,
                          complex_pair=fit.diagnostics.complex_pair)
        else:
            result['status'] = 'observed_statistic_failed'
            fixed = POWER_ONSETS if cell['kind'] == 'power' else None
            # Preserve an observed value even if the subsequent null is unusable.
            observed = s._statistic(values, window=40, lookback=8, merge=8, fixed_onsets=fixed)
            result.update(S=observed.mean_change, observed=serial(observed))
            result['status'] = 'comparison_failed'
            if fixed is None:
                comparison = s.csd_test(values, B=plan['surrogate_attempts'], rng=analysis)
            else:
                comparison = fixed_date_test(values, fixed, B=plan['surrogate_attempts'], rng=analysis)
            result.update(status=comparison.status, p_value=comparison.p_value,
                          comparison=serial(comparison),
                          surrogate_attempted=comparison.attempted,
                          surrogate_retained=comparison.retained,
                          surrogate_no_episode=comparison.no_episode,
                          surrogate_failed=comparison.failed)
            if comparison.retained:
                result.update(surrogate_exceedance_rate=comparison.exceedances/comparison.retained,
                              surrogate_exceedance_wilson=wilson_interval(
                                  comparison.exceedances, comparison.retained))
    except s.NullModelError as error:
        result.update(status='null_model_failed', error=f'{type(error).__name__}: {error}')
    except NUMERIC_ERRORS as error:
        result['error'] = f'{type(error).__name__}: {error}'
    result['generation_rng_after'] = deepcopy(generation.bit_generator.state)
    result['analysis_rng_after'] = deepcopy(analysis.bit_generator.state) if analysis else None
    return serial(result)


def run_batch(store, *, max_new, compute=compute_replicate):
    """Run at most max_new records. Committed failures are never rerun."""
    if type(max_new) is not int or max_new < 1:
        raise ValueError('max_new must be a positive integer')
    plan = store.manifest['plan']
    if plan != make_plan(plan['mode']):
        raise IntegrityError('Plan differs from frozen mode definition')
    if plan['mode'] == 'registered' and not store.manifest.get('registration_receipt_sha256'):
        raise IntegrityError('Registration verification receipt required')
    store.verify()
    started = time.perf_counter()
    completed = 0
    with store.transaction():
        store.event('batch_started')
    try:
        for cell in plan['cells']:
            for replicate in range(cell['requested']):
                # Lock before the existence check and computation. Concurrent
                # writers fail promptly instead of computing duplicate records.
                with store.transaction():
                    if store.contains(cell['name'], replicate):
                        continue
                    result = compute(plan, cell, replicate)
                    store.put(cell['name'], replicate, result)
                completed += 1
                if completed == max_new:
                    break
            if completed == max_new:
                break
    except BaseException:
        with store.transaction():
            store.event('batch_interrupted')
        raise
    with store.transaction():
        store.event('batch_finished')
    return dict(new_records=completed, seconds=time.perf_counter()-started)


def summarize(store):
    """All nominal denominators are retained. Development cannot pass any AT."""
    store.verify()
    plan = store.manifest['plan']
    if plan != make_plan(plan['mode']):
        raise IntegrityError('Plan differs from frozen mode definition')
    cells = {c['name']: dict(requested=c['requested'], attempted=0, valid=0,
                            positive=0, failures={}, statistics=[], p_values=[]) for c in plan['cells']}
    specifications = {c['name']: c for c in plan['cells']}
    with store.transaction(write=False):
        for record in store.iter_records():
            cell = cells[record['cell']]
            spec = specifications[record['cell']]
            cell['attempted'] += 1
            if record['status'] == 'ok':
                if spec['kind'] == 'white_noise':
                    valid = type(record.get('complex_pair')) is bool
                    positive = record.get('complex_pair') is True
                else:
                    p, value = record.get('p_value'), record.get('S')
                    valid = (isinstance(p, (int, float)) and isinstance(value, (int, float)) and
                             math.isfinite(p) and math.isfinite(value) and 0 <= p <= 1)
                    positive = valid and p <= .05
                if not valid:
                    raise IntegrityError('Successful record lacks a valid scientific outcome')
                cell['valid'] += 1
                cell['positive'] += int(positive)
                if spec['kind'] != 'white_noise':
                    cell['statistics'].append(value)
                    cell['p_values'].append(p)
            else:
                status = record['status']
                cell['failures'][status] = cell['failures'].get(status, 0) + 1
    for name, cell in cells.items():
        n, v, count = cell['requested'], cell['valid'], cell['positive']
        cell.update(unfinished=n-cell['attempted'], failed=cell['attempted']-v,
                    accounting_bounds=[count/n, (count+n-v)/n],
                    valid_only_rate=count/v if v else None,
                    rate=count/n if v == n else None,
                    rate_se=math.sqrt((count/n)*(1-count/n)/n) if v == n else None,
                    rate_wilson=wilson_interval(count, n) if v == n else None)
        ss = cell['statistics']
        cell['mean_S'] = float(np.mean(ss)) if ss and v == n else None
        cell['mean_S_se'] = float(np.std(ss, ddof=1)/math.sqrt(n)) if ss and v == n and n > 1 else None
        if specifications[name]['kind'] == 'white_noise':
            cell.update(complex=count, real=v-count)
        else:
            cell['rejected'] = count
    official = plan['mode'] == 'registered'
    rates = [cells[name]['rate'] for name in ('white_noise_n30', 'white_noise_n1000', 'size')]
    bounds = ((.625, .635), (.514, .526), (.02, .09))
    passes = [official and r is not None and lo <= r <= hi for r, (lo, hi) in zip(rates, bounds)]
    power = None
    if official:
        power_cells = [cells[f'power_{i}'] for i in range(4)]
        ps = [c['p_values'] + [None]*(200-c['valid']) for c in power_cells]
        ss = [c['statistics'] + [None]*(200-c['valid']) for c in power_cells]
        power = summarize_power(ps, ss)
    # Individual values stay in immutable records; keep summaries small.
    for cell in cells.values():
        del cell['statistics'], cell['p_values']
    return dict(mode=plan['mode'], manifest_sha256=store.manifest_hash, cells=cells,
                AT5_passed=passes[0] and passes[1], AT15_passed=passes[2],
                AT16_passed=bool(power and power['AT16_passed']), power=power,
                G2_passed=False, scope='Cell summary only; G2 requires separate complete evidence review.')
