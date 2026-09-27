"""Build the core note (plan W): every number is written from the committed evidence records.

Writes paper1/generated/*.tex, then, with --pdf, compiles paper1/core-note.tex with pdflatex.
Results that do not exist yet (G2, the ABMI release, H1, S2) are typeset as visible
placeholders, never as values (plan P1). The draft is dated by its source commit, and
pdflatex receives the same time as SOURCE_DATE_EPOCH, so one commit always gives one PDF.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / 'paper1'
GENERATED = PAPER / 'generated'
GATED = ('audit/G2_REVIEW.json', 'audit/H1_RESULT.json', 'audit/s2_verification.json', 'data/raw/ABMI_acquisition.json')
ANALYSES = {'primary': 'Primary', 'window32': 'Window of 32 quarters', 'window48': 'Window of 48 quarters',
            'fixed': 'Observed onset dates', 'wild': 'Wild-bootstrap signs', 'trend': 'Kendall trend of $M$',
            'lag1': 'Lag-one autocorrelation'}


def load(relative):
    path = ROOT / relative
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def f(value, digits):
    return '--' if value is None else f'{value:.{digits}f}'.replace('-', '$-$')


def tex(text):
    for plain, escaped in (('\\', r'\textbackslash{}'), ('&', r'\&'), ('%', r'\%'), ('_', r'\_'), ('#', r'\#')):
        text = str(text).replace(plain, escaped)
    return text


def scientific(value):
    mantissa, exponent = f'{value:.1e}'.split('e')
    return rf'${mantissa}\times 10^{{{int(exponent)}}}$'


def pending(what):
    return rf'\pending{{{what}}}'


def source_time():
    """Committer time of HEAD: the note is dated by its source, not by the build."""
    try:
        out = subprocess.run(['git', 'log', '-1', '--format=%ct'], cwd=ROOT, capture_output=True, text=True, check=True)
        return datetime.fromtimestamp(int(out.stdout.strip()), timezone.utc)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return datetime.now(timezone.utc)


def branch_b(interpretation):
    condition = interpretation.get('branch_B_condition')
    if interpretation.get('conclusion') != 'inconclusive' or condition is None:
        return ''
    if condition:
        return (r'The upper end of the episode interval lies below $D_{80}$; this retained diagnostic is conditional '
                r'and numerical, and it does not establish absence.')
    return r'The upper end of the episode interval does not lie below $D_{80}$.'


def numbers():
    macros = {}
    s1, yule, reg = load('audit/s1_verification.json'), load('audit/yule1927_verification.json'), load('audit/H1_REGISTRATION.json')
    foundations = load('audit/foundations_verification.json')
    first_run = load('audit/foundations_verification_v1.json')
    with (ROOT / 'data/transcribed/yule1927.csv').open(encoding='utf-8') as source:
        printed = {row['item']: row['value'] for row in csv.DictReader(source)}
    macros.update(DOI=reg['doi'], RegistrationApproved=reg['public_registration_timestamp_utc'][:16].replace('T', ' ') + ' UTC',
                  RegistrationSubmitted='25 September 2026', YuleBone=printed['eq31_coefficient_lag1'],
                  YuleBtwo=printed['eq31_coefficient_lag2'].lstrip('-'), YuleConst=printed['eq31_constant'],
                  YulePeriod=printed['eq31_period_years'], YuleRone=printed['table4_r1'], YuleRtwo=printed['table4_r2'])
    fits = {(row['version'], row['sample'], row['method']): row for row in s1['fits']}
    boot = {(row['version'], row['sample'], row['method']): row for row in s1['bootstrap']['summaries']}
    for tag, key in (('VoneLS', ('V1', '1749-1924', 'ols')), ('VtwoLS', ('V2', '1749-1924', 'ols'))):
        macros[f'{tag}Period'] = f(fits[key]['period'], 2)
        macros[f'{tag}Modulus'] = f(fits[key]['modulus'], 3)
    band = boot[('V1', '1749-1924', 'ols')]['period_band']
    macros.update(VoneLSBandLow=f(band[0], 1), VoneLSBandHigh=f(band[1], 1),
                  PeriodShift=f(s1['version_differences'][0]['period_V2_minus_V1'], 2),
                  TableADiffVone=str(yule['table_a_vs_silso_v1']['years_differing']),
                  TableAMaxDiff=f(yule['table_a_vs_silso_v1']['max_absolute_difference'], 1),
                  TableALSPeriod=f(yule['programme_fits_on_table_a']['ols']['period'], 2),
                  TableAYWPeriod=f(yule['programme_fits_on_table_a']['yw']['period'], 2),
                  ATelevenFirst=scientific(first_run['AT11']['test']['max_abs_difference']),
                  ATelevenFixed=scientific(foundations['AT11']['test']['max_abs_difference']))
    acquisition = load('data/raw/ABMI_acquisition.json')
    if acquisition:
        macros['ReleaseIdentity'] = (rf"The file is from \emph{{{tex(acquisition['release_title'])}}}, released "
                                     rf"{acquisition['release_datetime_utc'][:16].replace('T', ' ')} UTC "
                                     rf"(SHA-256 \texttt{{{acquisition['sha256'][:16]}}}\ldots).")
    else:
        macros['ReleaseIdentity'] = pending('release identity and hash, after acquisition')
    g2 = load('audit/G2_REVIEW.json')
    if g2:
        macros.update(GtwoStatus=tex(g2['G2']), ATfiveThirty=f(g2['AT5']['n30_rate'], 3),
                      ATfiveThousand=f(g2['AT5']['n1000_rate'], 3), ATfifteen=f(g2['AT15']['rate'], 3),
                      ATfiveThirtyPercent=f"{100 * g2['AT5']['n30_rate']:.0f}\\%",
                      Deighty=(r'undefined (no planted strength reached 80\% power)' if g2['D80'] is None
                               else f(g2['D80'], 3)))
    else:
        macros.update(GtwoStatus=pending('G2 review'), ATfiveThirty=pending('AT-5'), ATfiveThousand=pending('AT-5'),
                      ATfifteen=pending('AT-15'), ATfiveThirtyPercent=pending('AT-5 rate'), Deighty=pending('D80'))
    h1 = load('audit/H1_RESULT.json')
    if h1:
        primary, interval = h1['primary'], h1.get('episode_interval')
        macros.update(HoneS=f(primary['S'], 4), HoneP=f(primary['p_value'], 4), HoneM=str(primary['eligible_episodes']),
                      HoneK=str(primary['positive_changes']), HoneRetained=str(primary['retained']),
                      HoneConclusion=tex(h1['interpretation']['text']),
                      HoneInterval=('unavailable' if not interval else rf'$[{f(interval[0], 4)},\ {f(interval[1], 4)}]$'),
                      HoneBranchB=branch_b(h1['interpretation']))
    else:
        macros.update(HoneS=pending('S'), HoneP=pending('p'), HoneM=pending('m'), HoneK=pending('k'),
                      HoneRetained=pending("B'"), HoneConclusion=pending('H1 outcome, after the registered run'),
                      HoneInterval=pending('interval'), HoneBranchB='')
    return macros


def s1_table():
    s1, yule = load('audit/s1_verification.json'), load('audit/yule1927_verification.json')
    with (ROOT / 'data/transcribed/yule1927.csv').open(encoding='utf-8') as source:
        printed = {row['item']: row['value'] for row in csv.DictReader(source)}
    lines = [r'\begin{tabular}{llrrrrl}', r'\toprule',
             r'Series & Estimator & $\hat\varphi_1$ & $\hat\varphi_2$ & $M$ & Period (y) & 95\% band \\', r'\midrule']
    rp = yule['reproduction']
    lines.append(rf"Yule (1927), printed & Yule & {printed['eq31_coefficient_lag1']} & $-${printed['eq31_coefficient_lag2'].lstrip('-')} & & {printed['eq31_period_years']} & \\")
    lines.append(rf"Yule's Table A & Yule, reproduced & {f(rp['coefficient_lag1'], 5)} & {f(rp['coefficient_lag2'], 5)} & & {f(rp['period'], 3)} & \\")
    for name, key in (('ols', 'least squares'), ('yw', 'Yule--Walker')):
        row = yule['programme_fits_on_table_a'][name]
        lines.append(rf"Yule's Table A & {key} & {f(row['phi1'], 3)} & {f(row['phi2'], 3)} & {f(row['modulus'], 3)} & {f(row['period'], 2)} & \\")
    lines.append(r'\midrule')
    for fit, boot in zip(s1['fits'], s1['bootstrap']['summaries']):
        label = f"SILSO {fit['version']}, {fit['sample'].replace('-', '--')}"
        method = 'least squares' if fit['method'] == 'ols' else 'Yule--Walker'
        band = boot['period_band']
        lines.append(rf"{label} & {method} & {f(fit['phi1'], 3)} & {f(fit['phi2'], 3)} & {f(fit['modulus'], 3)} & {f(fit['period'], 2)} & {f(band[0], 1)}--{f(band[1], 1)} \\")
    lines += [r'\bottomrule', r'\end{tabular}']
    return '\n'.join(lines) + '\n'


def h1_tables():
    h1 = load('audit/H1_RESULT.json')
    if not h1:
        return pending('the seven registered comparisons and the episode table, after the registered run') + '\n'
    lines = [r'\begin{table}[htbp]', r'\centering\small', r'\begin{tabular}{lrrrrrr}', r'\toprule',
             r"Analysis & $W$ & Statistic & $p$ & $m$ & $k$ & $B'$ \\", r'\midrule']
    for row in h1['comparisons']:
        ok = row['status'] == 'ok'
        statistic = f(row['value'], 4) if ok else tex(row['status'].replace('_', ' '))
        lines.append(rf"{ANALYSES.get(row['analysis'], tex(row['analysis']))} & {row['window']} & {statistic} & "
                     rf"{f(row['p_value'], 4) if ok else '--'} & {row['eligible_episodes'] if row['eligible_episodes'] is not None else '--'} & "
                     rf"{row['positive_components'] if row.get('positive_components') is not None else '--'} & "
                     rf"{row['retained'] if row.get('retained') is not None else '--'} \\")
    lines += [r'\bottomrule', r'\end{tabular}',
              r"\caption{The registered comparisons: the primary test and the six secondary analyses, all reported. "
              r"$m$ eligible episodes, $k$ positive changes, $B'$ retained surrogates.}", r'\label{tab:h1}', r'\end{table}',
              r'\begin{table}[htbp]', r'\centering\small', r'\begin{tabular}{llr}', r'\toprule',
              r'Onset & End & $\Delta_r$ \\', r'\midrule']
    for episode in h1['episodes']:
        change = f(episode['change'], 4) if episode['statistic_available'] else 'not eligible'
        lines.append(rf"{episode['onset_quarter']} & {episode['end_quarter']} & {change} \\")
    lines += [r'\bottomrule', r'\end{tabular}',
              r'\caption{Recession episodes (two or more negative quarters, merged within eight quarters) and the '
              r'change $\Delta_r = M(r-1) - M(r-9)$, $W=40$.}', r'\label{tab:episodes}', r'\end{table}']
    return '\n'.join(lines) + '\n'


def s2_body():
    s2 = load('audit/s2_verification.json')
    if not s2:
        return pending('three filters on the registered levels, after acquisition') + '\n'
    rows = s2['rows']
    decided = [row for row in rows if row['oscillates'] is not None]
    lines = [rf"The oscillation condition holds under {sum(row['oscillates'] for row in decided)} of the "
             rf"{len(decided)} filters that give a reading (Table~\ref{{tab:s2}}).", '',
             r'\begin{table}[htbp]', r'\centering\small', r'\begin{tabular}{lrrrrrrl}', r'\toprule',
             r'Filter & $\hat\varphi_1$ & $\hat\varphi_2$ & $M$ & Period (q) & $c$ & $v$ & Oscillates \\', r'\midrule']
    for row in rows:
        oscillates = '--' if row['oscillates'] is None else ('yes' if row['oscillates'] else 'no')
        lines.append(rf"{tex(row['filter'])} & {f(row['phi1'], 3)} & {f(row['phi2'], 3)} & {f(row['modulus'], 3)} & "
                     rf"{f(row['period_quarters'], 1)} & {f(row['c'], 3)} & {f(row['v'], 3)} & {oscillates} \\")
    lines += [r'\bottomrule', r'\end{tabular}',
              rf"\caption{{Multiplier $c$ and accelerator $v$ implied by an AR(2) fitted to each cycle of $100\ln Y_t$, "
              rf"{s2['sample'][0]}--{s2['sample'][1]} (D-021). A check, not a result.}}", r'\label{tab:s2}', r'\end{table}']
    return '\n'.join(lines) + '\n'


def write(name, text):
    (GENERATED / name).write_text(text, encoding='utf-8', newline='\n')


def compile_pdf(epoch):
    latex = shutil.which('pdflatex')
    if not latex:
        raise SystemExit('pdflatex is not available')
    env = dict(os.environ, SOURCE_DATE_EPOCH=str(epoch), FORCE_SOURCE_DATE='1')
    for _ in range(2):
        done = subprocess.run([latex, '-interaction=nonstopmode', '-halt-on-error', 'core-note.tex'], cwd=PAPER, env=env,
                              capture_output=True, text=True, errors='replace')
        if done.returncode:
            raise SystemExit('pdflatex failed:\n' + '\n'.join(done.stdout.splitlines()[-25:]))
    log = (PAPER / 'core-note.log').read_text(encoding='latin-1')
    overfull = re.findall(r'Overfull \\[hv]box \(([\d.]+)pt too (?:wide|high)\)', log)
    undefined = re.findall(r'(?:Reference|Citation) `([^\']+)\' .*undefined', log)
    print(f'paper1/core-note.pdf built; {len(overfull)} overfull boxes, {len(undefined)} undefined references')
    return not undefined


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', action='store_true', help='compile paper1/core-note.pdf with pdflatex')
    args = parser.parse_args()
    GENERATED.mkdir(parents=True, exist_ok=True)
    when = source_time()
    macros = numbers()
    body = ['% Generated by tools/build_note.py from the committed evidence records; do not edit.',
            rf'\newcommand{{\notedate}}{{{when.day} {when:%B %Y}}}']
    body += [rf'\newcommand{{\{name}}}{{{value}}}' for name, value in sorted(macros.items())]
    write('numbers.tex', '\n'.join(body) + '\n')
    write('s1_table.tex', s1_table())
    write('h1_tables.tex', h1_tables())
    write('s2_body.tex', s2_body())
    waiting = sorted(name for name, value in macros.items() if value.startswith(r'\pending'))
    print(f'{len(macros)} numbers written; {len(waiting)} still pending: {", ".join(waiting) or "none"}')
    if args.pdf and not compile_pdf(int(when.timestamp())):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
