"""Compile and execute sanitizer harness, then actually cross-compile the same core."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'outputs/edge-core')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    compiler = shutil.which('clang')
    if not compiler:
        raise SystemExit('Clang is required for both sanitizer and Cortex-M cross-compilation.')
    core = ROOT/'src/instrumentzero/edge/core'
    binary = args.output/'core-sanitized'
    target = args.output/'core-cortex-m4.o'
    host_object = args.output/'core-host.o'
    cpp_binary = args.output/'cpp-integration'
    cpp_compiler = shutil.which('clang++')
    if not cpp_compiler:
        raise SystemExit('clang++ is required for the C++17 integration check.')
    commands = [
        [compiler, '-std=c99', '-g', '-O1', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
         '-fno-omit-frame-pointer', '-I'+str(core), str(core/'iz_core.c'), str(ROOT/'tests/edge/core_harness.c'), '-o', str(binary)],
        [str(binary)],
        [compiler, '-std=c99', '-O2', '-c', str(core/'iz_core.c'), '-o', str(host_object)],
        [cpp_compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I'+str(core), str(ROOT/'examples/edge/cpp-integration.cpp'), str(host_object), '-o', str(cpp_binary)],
        [str(cpp_binary)],
        [compiler, '--target=arm-none-eabi', '-mcpu=cortex-m4', '-mthumb', '-ffreestanding', '-fno-builtin',
         '-std=c99', '-Oz', '-Wall', '-Wextra', '-Werror', '-c', str(core/'iz_core.c'), '-o', str(target)]]
    receipts = []
    for command in commands:
        run = subprocess.run(command, capture_output=True, text=True)
        receipt = {'command': command, 'returncode': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr}
        receipts.append(receipt)
        (args.output/'commands.json').write_text(json.dumps(receipts, indent=2))
        if run.returncode:
            raise SystemExit(f'Failed acceptance command: {command}\n{run.stderr}')
    report = {'schema': 'instrumentzero.edge.core-verification/1', 'platform': platform.platform(),
              'compiler': subprocess.check_output([compiler,'--version'], text=True),
              'sanitizers': 'AddressSanitizer + UndefinedBehaviorSanitizer harness executed successfully',
              'cpp_integration': 'C++17 consumer linked to the separately compiled C99 core and executed',
              'cross_compilation': 'Cortex-M4 freestanding core object; not a linked board firmware image',
              'object_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
              'core_sha256': hashlib.sha256((core/'iz_core.h').read_bytes()+(core/'iz_core.c').read_bytes()).hexdigest(),
              'physical_verification': False, 'commands': receipts}
    (args.output/'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='commands'}, indent=2))


if __name__ == '__main__':
    main()
