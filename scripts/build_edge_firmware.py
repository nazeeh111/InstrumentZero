"""Build all three provisional board placements. Requires an existing pinned SDK/workspace.
Never installs a tool, accesses a device, or invokes west flash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from instrumentzero.edge.artifacts import generated_header
from instrumentzero.edge.native import core_identity
from instrumentzero.edge.spec import canonical, compile_graph

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--tools', type=Path, required=True, help='bin folder containing west, cmake and ninja')
    parser.add_argument('--output', type=Path, required=True, help='New, empty output directory')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    spec = json.loads((ROOT/'examples/edge/adxl345-spec.json').read_text())
    compiled = compile_graph(spec)
    env = os.environ.copy()
    env.update(PATH=str(args.tools)+os.pathsep+env['PATH'], ZEPHYR_BASE=str(args.workspace/'zephyr'),
               ZEPHYR_SDK_INSTALL_DIR=str(args.sdk), ZEPHYR_TOOLCHAIN_VARIANT='zephyr')
    source_paths = sorted((ROOT/'firmware/zephyr').rglob('*.c')) + sorted((ROOT/'firmware/zephyr').rglob('*.conf')) + sorted((ROOT/'firmware/zephyr').rglob('*.overlay')) + [ROOT/'firmware/zephyr/CMakeLists.txt',ROOT/'src/instrumentzero/edge/core/iz_core.c',ROOT/'src/instrumentzero/edge/core/iz_core.h']
    source_hashes = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    modes = []
    for mode in ('raw_host','calibrated_edge','filtered_edge'):
        bindings = args.output/('bindings-'+mode)
        bindings.mkdir()
        (bindings/'generated.h').write_text(generated_header(compiled, mode))
        (bindings/'compiled.json').write_bytes(canonical(compiled))
        command = [str(args.tools/'west'), 'build', '-b', 'nrf52840dk/nrf52840', str(ROOT/'firmware/zephyr'),
                   '-d', str(args.output/('build-'+mode)), '--', '-DIZ_BINDINGS_DIR='+str(bindings),
                   '-DDTC_OVERLAY_FILE='+str(ROOT/'firmware/zephyr/boards/nrf52840dk_nrf52840.overlay')]
        run = subprocess.run(command, cwd=args.workspace, env=env, capture_output=True, text=True)
        (args.output/(mode+'.log')).write_text(run.stdout+run.stderr)
        if run.returncode:
            raise SystemExit(f'Firmware build failed ({mode}); retained log: {args.output/(mode+".log")}\n{run.stderr[-3000:]}')
        if any(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest for name,digest in source_hashes.items()):
            raise SystemExit('Firmware source changed during build; retain this attempt and rebuild from a frozen source.')
        zephyr = args.output/('build-'+mode)/'zephyr'
        image = zephyr/'zephyr.elf'
        size_tool = args.sdk/'arm-zephyr-eabi/bin/arm-zephyr-eabi-size'
        size = subprocess.check_output([str(size_tool), '-A', str(image)], text=True)
        (args.output/(mode+'-sections.txt')).write_text(size)
        modes.append({'mode':mode, 'elf_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
                      'hex_sha256':hashlib.sha256((zephyr/'zephyr.hex').read_bytes()).hexdigest(),
                      'elf_bytes':image.stat().st_size, 'section_report':size,
                      'spec_sha256':compiled['spec_sha256'], 'command':command})
    report = {'schema':'instrumentzero.edge.firmware-build/1', 'zephyr_commit':subprocess.check_output(
        ['git','-C',str(args.workspace/'zephyr'),'rev-parse','HEAD'],text=True).strip(),
        'sdk_version':(args.sdk/'sdk_version').read_text().strip(), 'board':'nrf52840dk/nrf52840',
        'core_sha256':core_identity(), 'adapter_source_sha256':source_hashes, 'placements':modes,
        'hardware_operation_verified':False, 'flashed':False,
        'memory_scope':'Linker sections include fixed RTOS/driver/static stacks; stack high-water and device utilization remain unmeasured.'}
    (args.output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
