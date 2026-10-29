"""Render measured software comparisons from retained confirmation receipts."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
# Use Matplotlib's bundled DejaVu fonts for reproducible headless output. Avoid
# the machine font catalog, whose plist shape is unsupported on this macOS.
_original_check_output = subprocess.check_output

def _bundled_fonts_only(command, *args, **kwargs):
    if isinstance(command, (list, tuple)) and command and command[0] == 'system_profiler' and 'SPFontsDataType' in command:
        raise OSError('Headless plot uses bundled fonts only')
    return _original_check_output(command, *args, **kwargs)

subprocess.check_output = _bundled_fonts_only
try:
    import matplotlib.pyplot as plt
finally:
    subprocess.check_output = _original_check_output

ROOT = Path(__file__).resolve().parents[1]


def main():
    evidence = ROOT/'examples/edge/confirmation-final-v0.3'
    report = json.loads((evidence/'results.json').read_text())
    assert report['all_passed'] and len(report['trials']) == 18
    positives = [t for t in report['trials'] if t['scenario'] in ('mount_a','mount_b')]
    maximum_frequency = max(t['frequency_abs_error_hz'] for t in positives)
    maximum_damping = max(t['damping_relative_error'] for t in positives)
    groups = []
    for name in ('standard','host_favored'):
        cases = [t for t in positives if t['case']==name]
        values = np.array([[t['wire_bytes'][0],t['wire_bytes'][2],t['wire_bytes'][0 if t['selected']=='raw_host' else 2]] for t in cases])/1000
        assert np.all(values == values[0])
        groups.append(values[0])
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,
                         'figure.facecolor':'#f5f3ec','axes.facecolor':'#f5f3ec','text.color':'#222923','axes.labelcolor':'#222923'})
    fig, axes = plt.subplots(1,2,figsize=(11,4.6),sharey=True)
    for ax, values, title in zip(axes,groups,['Reduced stream permitted','Raw validation required'],strict=True):
        bars=ax.bar(['Raw host','Fixed FIR edge','Planner'],values,color=['#a3ad9a','#375cbd','#c84424'],width=.62)
        ax.set_title(title,loc='left',fontsize=14,pad=18)
        ax.set_ylim(0,48)
        ax.grid(axis='y',alpha=.15)
        ax.set_axisbelow(True)
        for bar,value in zip(bars,values,strict=True):
            ax.text(bar.get_x()+bar.get_width()/2,value+1.1,f'{value:.1f}',ha='center',fontsize=12)
    axes[0].set_ylabel('Transferred data / kB (1 kB = 1000 bytes)')
    fig.suptitle('InstrumentZero Edge · identical synthetic 8-second input',x=.06,ha='left',fontsize=18)
    fig.text(.06,.02,'Length prefixes, packet headers and timestamps included. Host cost proxies only; no MCU timing or physical measurement claim.',fontsize=9,color='#646e65')
    fig.tight_layout(rect=(.02,.07,1,.9))
    folder=ROOT/'assets/edge-v0.3'
    fig.savefig(folder/'placement-comparison.png',dpi=170)
    fig.savefig(folder/'placement-comparison.svg')
    summary={'confirmation_trials':18,'positive_trials':len(positives),'all_passed':True,
             'maximum_frequency_absolute_error_hz':maximum_frequency,'maximum_damping_relative_error':maximum_damping,
             'standard_framed_bytes':(groups[0]*1000).astype(int).tolist(),
             'raw_validation_framed_bytes':(groups[1]*1000).astype(int).tolist(),
             'physical_measurement_verified':False}
    (evidence/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
