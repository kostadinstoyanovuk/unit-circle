"""S1.5: the two S1 figures, built only from the saved fits and bootstrap draws.

(a) figures/s1_argand: each fit's upper root with its bootstrap cloud.
(b) figures/s1_triangle: the fits' positions in the stability triangle.
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FITS = ROOT / 'data/derived/s1_fits.csv'
DRAWS = ROOT / 'data/derived/s1_bootstrap_draws.npz'
OUT = ROOT / 'figures'
COLOURS = {'V1': '#2a78d6', 'V2': '#eb6834'}
INK, MUTED, GRID, SURFACE = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
METHOD_NAMES = {'ols': 'Least squares', 'yw': 'Yule-Walker'}

plt.rcParams.update({
    'svg.hashsalt': 'unit-circle-s1', 'font.size': 9, 'axes.edgecolor': MUTED,
    'axes.labelcolor': INK, 'xtick.color': MUTED, 'ytick.color': MUTED,
    'axes.facecolor': SURFACE, 'figure.facecolor': SURFACE, 'savefig.facecolor': SURFACE,
})


def load():
    with FITS.open(encoding='utf-8') as source:
        rows = list(csv.DictReader(source))
    for row in rows:
        for key in ('phi1', 'phi2', 'modulus', 'period'):
            row[key] = float(row[key])
    return rows, np.load(DRAWS)


def upper_root(phi1, phi2):
    discriminant = phi1 * phi1 + 4 * phi2
    return phi1 / 2, np.sqrt(np.maximum(-discriminant, 0)) / 2


def save(figure, name):
    OUT.mkdir(exist_ok=True)
    figure.savefig(OUT / f'{name}.svg', metadata={'Date': None})
    figure.savefig(OUT / f'{name}.png', dpi=200, metadata={'Software': None})
    figure.savefig(OUT / f'{name}.pdf', metadata={'CreationDate': None, 'ModDate': None, 'Producer': None, 'Creator': None})
    plt.close(figure)


def style(axis):
    axis.grid(True, color=GRID, linewidth=0.6)
    axis.set_axisbelow(True)
    for side in ('top', 'right'):
        axis.spines[side].set_visible(False)


def argand(rows, draws):
    columns = ['1749-1924', 'later']
    figure, axes = plt.subplots(2, 2, figsize=(7.2, 6.4), sharex=True, sharey=True, constrained_layout=True)
    angle = np.linspace(0, np.pi / 2, 400)
    for r, method in enumerate(('ols', 'yw')):
        for c, column in enumerate(columns):
            axis = axes[r, c]
            style(axis)
            axis.plot(np.cos(angle), np.sin(angle), color=INK, linewidth=1.0)
            axis.text(0.86, 0.64, '|λ| = 1', color=INK, fontsize=8, rotation=-52)
            for k, row in enumerate(rows):
                early = row['sample'] == '1749-1924'
                if row['method'] != method or early != (column == '1749-1924'):
                    continue
                d, complex_pair = draws[f'draws_{k}'], draws[f'complex_{k}']
                x, y = upper_root(d[complex_pair, 0], d[complex_pair, 1])
                colour = COLOURS[row['version']]
                axis.scatter(x, y, s=2, color=colour, alpha=0.12, linewidths=0, rasterized=True)
                px, py = upper_root(row['phi1'], row['phi2'])
                axis.scatter([px], [py], s=70 if row['version'] == 'V2' else 26, color=colour, edgecolors=SURFACE,
                             linewidths=1.4, zorder=3 if row['version'] == 'V2' else 4,
                             label=f"{row['version']} {row['sample']}")
            axis.set_xlim(0.42, 0.92)
            axis.set_ylim(0.22, 0.72)
            axis.set_aspect('equal')
            title = '1749-1924' if column == '1749-1924' else '1925 to last complete year'
            axis.set_title(f'{METHOD_NAMES[method]}, {title}', fontsize=9, color=INK, loc='left')
            axis.legend(loc='lower left', frameon=False, fontsize=8, markerscale=0.8)
            if r == 1:
                axis.set_xlabel('Re λ')
            if c == 0:
                axis.set_ylabel('Im λ')
    figure.suptitle('Upper companion roots of the sunspot AR(2) fits, with 4,000 bootstrap roots each',
                    fontsize=10, color=INK, x=0.01, ha='left')
    save(figure, 's1_argand')


def triangle(rows):
    figure, (full, zoom) = plt.subplots(1, 2, figsize=(7.2, 3.4), constrained_layout=True,
                                        gridspec_kw={'width_ratios': [1.2, 1]})
    phi1 = np.linspace(-2, 2, 400)
    for axis in (full, zoom):
        style(axis)
        axis.plot([-2, 0, 2, -2], [-1, 1, -1, -1], color=INK, linewidth=1.0)
        axis.plot(phi1, -phi1 ** 2 / 4, color=MUTED, linewidth=0.9, linestyle='--')
        for row in rows:
            colour = COLOURS[row['version']]
            marker = 'o' if row['sample'] == '1749-1924' else 's'
            face = colour if row['method'] == 'ols' else SURFACE
            axis.scatter([row['phi1']], [row['phi2']], s=40, marker=marker, facecolors=face,
                         edgecolors=colour, linewidths=1.4, zorder=3)
        axis.set_xlabel('φ₁')
    full.set_ylabel('φ₂')
    full.set_xlim(-2.1, 2.1)
    full.set_ylim(-1.1, 1.1)
    full.text(-0.55, -0.35, 'complex roots', color=MUTED, fontsize=8)
    full.text(-0.3, 0.35, 'real roots', color=MUTED, fontsize=8)
    full.add_patch(plt.Rectangle((1.30, -0.78), 0.14, 0.16, fill=False, edgecolor=MUTED, linewidth=0.8))
    full.set_title('Stability triangle', fontsize=9, color=INK, loc='left')
    zoom.set_xlim(1.30, 1.44)
    zoom.set_ylim(-0.78, -0.62)
    zoom.set_title('Detail', fontsize=9, color=INK, loc='left')
    handles = [
        plt.Line2D([], [], color=COLOURS['V1'], marker='o', linestyle='', label='Version 1'),
        plt.Line2D([], [], color=COLOURS['V2'], marker='o', linestyle='', label='Version 2'),
        plt.Line2D([], [], color=MUTED, marker='o', linestyle='', label='1749-1924'),
        plt.Line2D([], [], color=MUTED, marker='s', linestyle='', label='1925 to series end (2014, 2025)'),
        plt.Line2D([], [], color=MUTED, marker='o', linestyle='', markerfacecolor=SURFACE, label='hollow: Yule-Walker, filled: least squares'),
    ]
    zoom.legend(handles=handles, loc='upper right', frameon=False, fontsize=7.5)
    save(figure, 's1_triangle')


def main():
    rows, draws = load()
    argand(rows, draws)
    triangle(rows)
    print('figures/s1_argand.svg, figures/s1_argand.png, figures/s1_triangle.svg, figures/s1_triangle.png')


if __name__ == '__main__':
    main()
