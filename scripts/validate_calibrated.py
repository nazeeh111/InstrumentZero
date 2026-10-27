#!/usr/bin/env python3
"""Reproduce a calibrated recorded acoustic reference comparison and its figures."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from instrumentzero.calibrated import calibrated_acoustic_validation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('data'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a fresh output directory; earlier outputs are preserved')
    result = calibrated_acoustic_validation(args.data)
    source_root = Path(__file__).resolve().parents[1]
    result['analysis_source_sha256'] = {name: hashlib.sha256((source_root/name).read_bytes()).hexdigest()
                                      for name in ('src/instrumentzero/calibrated.py', 'scripts/validate_calibrated.py')}
    args.output.mkdir(parents=True)
    (args.output/'results.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    c = result['comparison']
    with (args.output/'paired-levels.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['source_row_index', 'source_column_index', 'measured_spl_db', 'reference_spl_db', 'difference_db'])
        for row in range(33):
            for col in range(33):
                writer.writerow([row, col, c['measured_level_db'][row][col], c['reference_level_db'][row][col], c['difference_db'][row][col]])
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    values = np.asarray(c['difference_db'])
    limit = float(np.max(np.abs(values)))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.4), layout='constrained')
    fig.patch.set_facecolor('#f5f3ec')
    cmap = LinearSegmentedColormap.from_list('instrumentzero', ['#375cbd', '#faf9f5', '#d65d37'])
    image = axes[0].imshow(values, cmap=cmap, vmin=-limit, vmax=limit, origin='lower')
    axes[0].set(xlabel='Source column index (Z direction)', ylabel='Source row index (Y direction)',
                title='HiFUSPEx minus reference USPM / recorded grid')
    fig.colorbar(image, ax=axes[0], label='Sound-level difference / dB', shrink=.8)
    axes[1].hist(values.ravel(), bins=30, color='#375cbd', edgecolor='#f5f3ec', linewidth=.5)
    axes[1].axvline(c['mean_difference_db'], color='#d65d37', linewidth=2,
                    label=f"Mean difference {c['mean_difference_db']:.3f} dB")
    axes[1].set(xlabel='Recorded paired difference / dB', ylabel='Number of grid positions',
                title=f"1,089 positions; twice spatial SD {c['twice_spatial_sd_db']:.3f} dB")
    axes[1].legend(loc='upper right', fontsize=9)
    for axis in axes:
        axis.set_facecolor('#f5f3ec')
        axis.spines[['top', 'right']].set_visible(False)
    fig.suptitle('PTB calibrated acoustic field comparison • 20 kHz scene', fontsize=14)
    fig.supxlabel('Sequential physical recordings. Spatial spread is not a mean confidence interval. Source: 10.7795/720.20211214', fontsize=9)
    fig.savefig(args.output/'calibrated-reference.png', dpi=170)
    fig.savefig(args.output/'calibrated-reference.svg')
    plt.close(fig)
    print(json.dumps({'positions': c['positions'], 'mean_difference_db': c['mean_difference_db'],
                      'twice_spatial_sd_db': c['twice_spatial_sd_db'], 'output': str(args.output)}, indent=2))


if __name__ == '__main__':
    main()
