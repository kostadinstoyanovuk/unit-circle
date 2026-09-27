"""H1 tables and reporting semantics; no data acquisition or inference reruns."""
import csv
from datetime import datetime, timezone
import math
from pathlib import Path

import numpy as np

from .ar import _real_vector
from .recession import episodes, pre_onset_changes
from .rolling import rolling_ar2
from .validation_design import wilson_interval
from .validation_runner import serial
from .validation_store import canonical, digest


def _finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _validated_accounting(source, value):
    """Reconcile summaries with every stored attempt before displaying them."""
    requested, attempted = source.get('requested'), source.get('attempted')
    retained = source.get('retained', 0 if attempted == 0 else None)
    empty = source.get('no_episode', 0 if attempted == 0 else None)
    failed = source.get('failed', 0 if attempted == 0 else None)
    if (type(requested) is not int or requested < 1 or
            any(type(v) is not int or v < 0 for v in (attempted, retained, empty, failed))):
        raise ValueError('Every comparison needs explicit nonnegative attempt accounting')
    if attempted != retained + empty + failed or attempted > requested:
        raise ValueError('Inconsistent comparison attempt accounting')
    attempts = source.get('attempts', [])
    if not isinstance(attempts, list) or len(attempts) != attempted:
        raise ValueError('Attempt ledger length differs from comparison counts')
    counts = dict(retained=0, no_eligible_episode=0, failed=0)
    statistics = []
    for number, attempt in enumerate(attempts):
        if not isinstance(attempt, dict):
            raise ValueError('Every attempt must have a numbered status record')
        if type(attempt.get('number')) is not int or attempt['number'] != number:
            raise ValueError('Attempt numbers must be consecutive zero-based positions')
        status, statistic = attempt.get('status'), attempt.get('statistic')
        if status not in counts:
            raise ValueError('Unknown attempt status')
        counts[status] += 1
        if status == 'retained':
            if not _finite(statistic):
                raise ValueError('Retained attempt statistic must be finite')
            statistics.append(statistic)
        elif statistic is not None:
            raise ValueError('Failed or ineligible attempt cannot retain a statistic')
    if (counts['retained'], counts['no_eligible_episode'], counts['failed']) != (retained, empty, failed):
        raise ValueError('Attempt ledger statuses differ from comparison counts')
    p, count, spacing = source.get('p_value'), source.get('exceedances'), source.get('p_grid_spacing')
    if retained:
        if (not _finite(value) or type(count) is not int or
                count != sum(statistic >= value for statistic in statistics)):
            raise ValueError('Exceedance count disagrees with retained attempt statistics')
        if not _finite(spacing) or spacing != 1/(retained+1):
            raise ValueError('P-value grid spacing disagrees with retained attempt count')
    elif count is not None or spacing is not None:
        raise ValueError('Empty retained distribution cannot carry exceedances or grid spacing')
    status = source['status']
    if attempted:
        expected = 'invalid_surrogate_failure' if failed else ('ok' if retained else 'no_retained_surrogates')
        if attempted != requested or status != expected:
            raise ValueError('Comparison status or completion disagrees with attempt ledger')
    elif status not in ('observed_not_estimable', 'observed_statistic_failed', 'null_model_failed'):
        raise ValueError('Zero-attempt comparison needs an unavailable or failed observed/null status')
    if status == 'ok':
        if not _finite(p) or p != (1+count)/(1+retained):
            raise ValueError('Successful comparison p-value disagrees with attempt ledger')
    elif p is not None:
        raise ValueError('A failed or unavailable comparison cannot carry an inferential p-value')
    return attempted, retained, empty, failed, p, count


def comparison_rows(results):
    """Keep all seven prespecified rows, including unavailable comparisons."""
    results = serial(results)
    joint = results['joint']
    sources = [('primary', joint['primary'], 40),
               ('window32', results['window32'], 32),
               ('window48', results['window48'], 48),
               ('fixed', results['fixed'], 40),
               ('wild', results['wild'], 40),
               ('trend', joint['trend'], 40),
               ('lag1', joint['lag1'], 40)]
    rows = []
    for name, source, window in sources:
        observed = source.get('observed') or {}
        value = observed.get('value', observed.get('mean_change'))
        components = observed.get('components', observed.get('changes'))
        onsets = observed.get('eligible_onsets')
        if onsets is not None and components is not None and len(onsets) != len(components):
            raise ValueError('Observed components and eligible episodes disagree')
        attempted, retained, empty, failed, p, count = _validated_accounting(source, value)
        if value is not None and not _finite(value):
            raise ValueError('Observed statistic must be finite or absent')
        error = source.get('error') or observed.get('error')
        if source['status'] == 'null_model_failed' and name in ('primary', 'trend', 'lag1'):
            error = joint.get('null_error') or error
        precision = wilson_interval(count, retained) if retained and count is not None else None
        rows.append(dict(analysis=name, window=window, status=source['status'], value=value,
                         p_value=p, eligible_episodes=len(onsets) if onsets is not None else None,
                         positive_components=sum(v > 0 for v in components) if components is not None else None,
                         requested=source['requested'], attempted=attempted, retained=retained,
                         no_eligible=empty, failed=failed, exceedances=count,
                         p_grid_spacing=source.get('p_grid_spacing'),
                         exceedance_rate=count/retained if precision else None,
                         exceedance_wilson_low=precision[0] if precision else None,
                         exceedance_wilson_high=precision[1] if precision else None,
                         error=error))
    return rows


def primary_interpretation(row, episode_interval, *, D80=None):
    """Preserve the signed statistic and the restricted Branch B diagnostic."""
    value, p = row.get('value'), row.get('p_value')
    if value is not None and not _finite(value):
        raise ValueError('Nonfinite observed statistic')
    if D80 is not None and not _finite(D80):
        raise ValueError('D80 must be finite or absent')
    interval = serial(episode_interval).get('interval')
    if interval is not None and (len(interval) != 2 or not all(_finite(x) for x in interval)
                                 or interval[0] > interval[1]):
        raise ValueError('Invalid episode interval')
    sign = 'unavailable' if value is None else ('positive' if value > 0 else 'negative' if value < 0 else 'zero')
    if row['status'] != 'ok' or p is None:
        conclusion = 'not_estimable' if row['status'] in ('observed_not_estimable', 'no_retained_surrogates') else 'failed'
        text = 'The primary comparison is unavailable; no rejection or non-rejection is assigned.'
    else:
        if not _finite(p) or not 0 <= p <= 1 or value is None:
            raise ValueError('Invalid successful primary comparison')
        conclusion = 'upper_tail_rejection' if p <= .05 else 'inconclusive'
        text = ('The observed mean pre-onset change was unusually large relative to the specified fitted constant-AR(2) surrogate procedure.'
                if p <= .05 else
                'The primary comparison did not detect an unusually large pre-onset change under the specified surrogate model; the conclusion is inconclusive.')
        if value <= 0:
            text += ' The observed mean change is nonpositive; this does not show an absolute positive rise in persistence.'
    available = row['status'] == 'ok' and p is not None and D80 is not None and interval is not None
    return dict(conclusion=conclusion, statistic_sign=sign, text=text,
                branch_B_condition=bool(p > .05 and interval[1] < D80) if available else None,
                branch_B_scope='Conditional numerical diagnostic only; it does not establish absence or equivalence.',
                episode_interval_scope='Conditional episode-resampling diagnostic; calibrated coverage is not asserted.',
                D80=D80)


def assemble_report(growth, results):
    """Assemble existing results with the input path; does not draw randomness."""
    values = _real_vector(growth, minimum=1)
    results = serial(results)
    input_sha256 = digest(values.astype('<f8').tobytes())
    if results.get('input_sha256') != input_sha256:
        raise ValueError('Analysis input hash is missing or does not match the supplied input path')
    rows = comparison_rows(results)
    primary = results['joint']['primary']['observed']
    changes = dict(zip(primary.get('eligible_onsets', []), primary.get('components', [])))
    grouped = episodes(values)
    episode_rows, run_rows = [], []
    for number, episode in enumerate(grouped):
        episode_rows.append(dict(episode=number, onset=episode.onset, end=episode.end,
                                 qualifying_runs=len(episode.runs),
                                 structurally_eligible=episode.onset >= 48,
                                 statistic_available=episode.onset in changes,
                                 change=changes.get(episode.onset)))
        run_rows.extend(dict(episode=number, onset=run.onset, end=run.end) for run in episode.runs)
    rolling_error = None
    try:
        fitted = rolling_ar2(values, 40)
        rolling_rows = [dict(position=i, growth=float(values[i]),
                             **{key: (None if isinstance(value, float) and not math.isfinite(value) else value)
                                for key, value in row.items()}) for i, row in enumerate(fitted.to_dict('records'))]
    except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
        rolling_error = f'{type(error).__name__}: {error}'
        rolling_rows = [dict(position=i, growth=float(value), intercept=None, phi1=None, phi2=None,
                             modulus=None, status='unavailable_after_failure') for i, value in enumerate(values)]
    if rolling_error is None and primary['status'] == 'ok':
        expected = pre_onset_changes(fitted['modulus'], [e.onset for e in grouped])
        if (expected.mean_change != primary['value'] or
                list(expected.changes) != primary['components'] or
                list(expected.eligible_onsets) != primary['eligible_onsets']):
            raise ValueError('Primary result does not match the supplied input path')
    elif rolling_error is not None and primary['status'] == 'ok':
        raise ValueError('Successful primary result cannot be paired with a failed rolling path')
    attempts = results['joint']['primary']['attempts']
    surrogate_rows = [dict(number=a['number'], status=a['status'], statistic=a['statistic'],
                           eligible_episodes=len(a['eligible_onsets']), error=a['error']) for a in attempts]
    return dict(comparisons=rows, episodes=episode_rows, qualifying_runs=run_rows,
                rolling=rolling_rows, rolling_error=rolling_error,
                primary_surrogates=surrogate_rows,
                episode_interval=results['episode_interval'],
                interpretation=primary_interpretation(rows[0], results['episode_interval']),
                input_sha256=input_sha256)


def _csv(path, rows, fields):
    with path.open('x', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=['data_kind', *fields], lineterminator='\n')
        writer.writeheader()
        writer.writerows(dict(data_kind='artificial_development_fixture', **row) for row in rows)


def _figures(report, directory):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['svg.hashsalt'] = 'h1-report-development-v1'
    title = 'Development fixture · no UK observations'
    fig, ax = plt.subplots(figsize=(10, 4.5), layout='constrained')
    position = [r['position'] for r in report['rolling']]
    modulus = [np.nan if r['modulus'] is None else r['modulus'] for r in report['rolling']]
    ax.plot(position, modulus, color='#235b83', linewidth=1.6, label='Rolling AR(2) modulus')
    for i, episode in enumerate(report['episodes']):
        ax.axvspan(episode['onset']-.5, episode['end']+.5, color='#555555', alpha=.15,
                   label='Merged negative-growth episode' if i == 0 else None)
    ax.axhline(1, color='#777777', linewidth=.8, linestyle=':', label='Unit modulus')
    ax.set(xlabel='Synthetic observation position (zero-based)', ylabel='Largest root modulus M(t)', title=title)
    if report['rolling_error']:
        ax.text(.5, .5, 'Indicator unavailable: fitting failure\nSee report.json for the retained error.',
                ha='center', va='center', transform=ax.transAxes)
    ax.legend(loc='upper left', fontsize=8)
    ax.spines[['top', 'right']].set_visible(False)
    for extension in ('png', 'svg'):
        fig.savefig(directory/f'persistence.{extension}', dpi=150,
                    metadata={'Creator': 'Unit Circle Programme', **({'Date': None} if extension == 'svg' else {})})
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.5), layout='constrained')
    retained = [r['statistic'] for r in report['primary_surrogates'] if r['status'] == 'retained']
    row = report['comparisons'][0]
    if retained:
        ax.hist(retained, bins=min(20, len(retained)), color='#a7bac8', edgecolor='#ffffff', label='Retained surrogate statistics')
    else:
        ax.text(.5, .5, 'No retained surrogate distribution', ha='center', va='center', transform=ax.transAxes)
    if row['value'] is not None:
        ax.axvline(row['value'], color='#963f35', linewidth=1.6, label=f"Observed S = {row['value']:.4g}")
    ax.set(xlabel='Mean pre-onset change S (modulus units)', ylabel='Retained surrogate count', title=title)
    if retained or row['value'] is not None:
        ax.legend(loc='upper left', fontsize=8)
    ax.text(.99, .96, f"Status: {row['status']}\nRetained {row['retained']} / attempted {row['attempted']}",
            ha='right', va='top', transform=ax.transAxes, fontsize=9)
    ax.spines[['top', 'right']].set_visible(False)
    for extension in ('png', 'svg'):
        fig.savefig(directory/f'surrogates.{extension}', dpi=150,
                    metadata={'Creator': 'Unit Circle Programme', **({'Date': None} if extension == 'svg' else {})})
    plt.close(fig)


def write_development_report(directory, growth, results, *, fixture_metadata):
    """Export artificial-data evidence only. A gated empirical exporter is separate."""
    if fixture_metadata.get('data_kind') != 'artificial_development_fixture':
        raise ValueError('This export entry point accepts labelled development fixtures only')
    directory = Path(directory)
    report = assemble_report(growth, results)
    directory.mkdir(parents=True, exist_ok=False)
    for name in ('report', 'analysis'):
        payload = report if name == 'report' else serial(results)
        (directory/f'{name}.json').write_bytes(canonical(dict(data_kind='artificial_development_fixture', result=payload))+b'\n')
    _csv(directory/'comparisons.csv', report['comparisons'], list(report['comparisons'][0]))
    _csv(directory/'episodes.csv', report['episodes'],
         ['episode', 'onset', 'end', 'qualifying_runs', 'structurally_eligible', 'statistic_available', 'change'])
    _csv(directory/'qualifying-runs.csv', report['qualifying_runs'], ['episode', 'onset', 'end'])
    _csv(directory/'rolling.csv', report['rolling'], ['position', 'growth', 'intercept', 'phi1', 'phi2', 'modulus', 'status'])
    _csv(directory/'primary-surrogates.csv', report['primary_surrogates'], ['number', 'status', 'statistic', 'eligible_episodes', 'error'])
    _figures(report, directory)
    note = ('# H1 report development fixture\n\n'
            '**Artificial data only. This is not a UK result, registered experiment or final research note.**\n\n'
            'The tables retain all seven analysis rows and all attempted primary surrogates. '
            'Blank CSV cells mean unavailable, not zero; the status and error columns retain the reason.\n\n'
            f"Reporting-logic output: {report['interpretation']['text']}\n\n"
            f"Signed statistic: {report['interpretation']['statistic_sign']}. "
            'The episode interval is a conditional diagnostic. Official D80 and the Branch B diagnostic are unavailable here. '
            'No claim of calibrated coverage, absence, equivalence, causal tipping or real-time prediction follows.\n\n'
            'The figures use zero-based artificial observation positions. Complete inputs and rolling values are in rolling.csv; '
            'complete numerical results and random states are in analysis.json. '
            'The final empirical note remains gated by public registration, validation and verified source acquisition.\n')
    (directory/'core-note.md').write_text(note, encoding='utf-8', newline='\n')
    manifest = dict(created_at_utc=datetime.now(timezone.utc).isoformat(),
                    scope='Development report only; no UK observations or official validation results.',
                    fixture=fixture_metadata, input_sha256=report['input_sha256'],
                    file_sha256={p.name: digest(p.read_bytes()) for p in sorted(directory.iterdir())})
    (directory/'manifest.json').write_bytes(canonical(manifest)+b'\n')
    return manifest


# Registered (and rehearsal) export with quarter labels and the official D80.

REGISTERED_KINDS = ('uk_abmi_registered', 'artificial_pipeline_rehearsal')


def _labelled_csv(path, rows, fields, data_kind):
    with path.open('x', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=['data_kind', *fields], lineterminator='\n')
        writer.writeheader()
        writer.writerows(dict(data_kind=data_kind, **{key: row.get(key) for key in fields}) for row in rows)


def _figure_metadata(extension):
    """Fixed metadata so that each figure file is byte-reproducible."""
    if extension == 'svg':
        return {'Creator': 'Unit Circle Programme', 'Date': None}
    if extension == 'pdf':
        return {'Creator': 'Unit Circle Programme', 'Producer': None, 'CreationDate': None, 'ModDate': None}
    return {'Creator': 'Unit Circle Programme', 'Software': None}


def _registered_figures(report, directory, labels, title):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['svg.hashsalt'] = 'h1-registered-report'
    ticks = [i for i, label in enumerate(labels) if label.endswith('Q1') and int(label[:4]) % 10 == 0]
    fig, ax = plt.subplots(figsize=(10, 4.5), layout='constrained')
    modulus = [np.nan if r['modulus'] is None else r['modulus'] for r in report['rolling']]
    ax.plot(range(len(modulus)), modulus, color='#2a78d6', linewidth=1.6, label='Rolling AR(2) modulus M(t), W = 40')
    for i, episode in enumerate(report['episodes']):
        ax.axvspan(episode['onset'] - .5, episode['end'] + .5, color='#52514e', alpha=.15,
                   label='Recession episode (two or more negative quarters, merged)' if i == 0 else None)
    ax.axhline(1, color='#52514e', linewidth=.8, linestyle=':', label='Unit modulus')
    ax.set_xticks(ticks, [labels[i][:4] for i in ticks])
    ax.set(xlabel='Quarter', ylabel='Largest root modulus M(t)', title=title)
    if report['rolling_error']:
        ax.text(.5, .5, 'Indicator unavailable: fitting failure', ha='center', va='center', transform=ax.transAxes)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.14), ncol=3, frameon=False, fontsize=8)
    ax.spines[['top', 'right']].set_visible(False)
    for extension in ('png', 'svg', 'pdf'):
        fig.savefig(directory / f'persistence.{extension}', dpi=200, metadata=_figure_metadata(extension))
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4.5), layout='constrained')
    retained = [r['statistic'] for r in report['primary_surrogates'] if r['status'] == 'retained']
    row = report['comparisons'][0]
    if retained:
        ax.hist(retained, bins=40, color='#a7bac8', edgecolor='#fcfcfb', label='Retained surrogate statistics S_b')
    else:
        ax.text(.5, .5, 'No retained surrogate distribution', ha='center', va='center', transform=ax.transAxes)
    if row['value'] is not None:
        ax.axvline(row['value'], color='#eb6834', linewidth=1.8, label=f"Observed S = {row['value']:.4f}")
    ax.set(xlabel='Mean pre-onset change S (modulus units)', ylabel='Count', title=title)
    if retained or row['value'] is not None:
        ax.legend(loc='upper left', fontsize=8)
    p = row['p_value']
    ax.text(.99, .96, f"p = {p:.4f}\nretained {row['retained']} of {row['attempted']}" if p is not None
            else f"Status: {row['status']}", ha='right', va='top', transform=ax.transAxes, fontsize=9)
    ax.spines[['top', 'right']].set_visible(False)
    for extension in ('png', 'svg', 'pdf'):
        fig.savefig(directory / f'surrogates.{extension}', dpi=200, metadata=_figure_metadata(extension))
    plt.close(fig)


def write_registered_report(directory, growth, labels, results, *, D80, metadata, data_kind='uk_abmi_registered'):
    """Export the registered analysis (or a labelled artificial rehearsal) with quarter labels and D80."""
    if data_kind not in REGISTERED_KINDS:
        raise ValueError('Unknown registered export kind')
    labels = tuple(labels)
    values = _real_vector(growth, minimum=1)
    if len(labels) != len(values):
        raise ValueError('One quarter label is required per growth observation')
    directory = Path(directory)
    report = assemble_report(values, results)
    report['interpretation'] = primary_interpretation(report['comparisons'][0], serial(results)['episode_interval'], D80=D80)
    for row in report['rolling']:
        row['quarter'] = labels[row['position']]
    for row in report['episodes'] + report['qualifying_runs']:
        row['onset_quarter'], row['end_quarter'] = labels[row['onset']], labels[row['end']]
    directory.mkdir(parents=True, exist_ok=False)
    for name in ('report', 'analysis'):
        payload = report if name == 'report' else serial(results)
        (directory / f'{name}.json').write_bytes(canonical(dict(data_kind=data_kind, result=payload)) + b'\n')
    _labelled_csv(directory / 'comparisons.csv', report['comparisons'], list(report['comparisons'][0]), data_kind)
    _labelled_csv(directory / 'episodes.csv', report['episodes'],
                  ['episode', 'onset', 'onset_quarter', 'end', 'end_quarter', 'qualifying_runs',
                   'structurally_eligible', 'statistic_available', 'change'], data_kind)
    _labelled_csv(directory / 'qualifying-runs.csv', report['qualifying_runs'],
                  ['episode', 'onset', 'onset_quarter', 'end', 'end_quarter'], data_kind)
    _labelled_csv(directory / 'rolling.csv', report['rolling'],
                  ['position', 'quarter', 'growth', 'intercept', 'phi1', 'phi2', 'modulus', 'status'], data_kind)
    _labelled_csv(directory / 'primary-surrogates.csv', report['primary_surrogates'],
                  ['number', 'status', 'statistic', 'eligible_episodes', 'error'], data_kind)
    title = ('UK real GDP growth, 1955Q2-2019Q4 (ONS ABMI)' if data_kind == 'uk_abmi_registered'
             else 'Artificial pipeline rehearsal · no UK observations')
    _registered_figures(report, directory, labels, title)
    manifest = dict(data_kind=data_kind, metadata=metadata, input_sha256=report['input_sha256'],
                    interpretation=report['interpretation'],
                    file_sha256={p.name: digest(p.read_bytes()) for p in sorted(directory.iterdir())})
    (directory / 'manifest.json').write_bytes(canonical(manifest) + b'\n')
    return manifest
