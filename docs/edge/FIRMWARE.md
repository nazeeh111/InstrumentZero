> Optional extension: physical operation is outside the simulation-only project scope. This document preserves an unexecuted commissioning plan or software/build evidence; it is not a simulation completion gate.

# Runtime configuration update (rc3)

The current adapter requires IZC1 configuration and a matching IZA1 acknowledgement before each `G`. It supports rates of 100, 200 or 400 Hz, calibration, FIR/reduction, placement and raw-validation changes within the compiled block/queue envelope. All placement builds now contain the same runtime-capable numerical and control paths. The example total RAM planning budget is 40,960 bytes with a 6,144-byte control/RX reserve and processing state reserved in every mode. C11 atomics support the interrupt-driven RX ring; the numerical core remains C99-compatible. See [CONTROL.md](CONTROL.md). No physical operation or flashing has been performed.

Current [runtime build receipts](../../examples/edge/firmware-uart-build/report.json) bind the adapter and control source. Historical rc1 receipts remain in their original folder.

# Provisional sensor adapter and build

**No actual equipment was available or selected for deployment.** The reproducible build target is a provisional nRF52840 DK plus ADXL345 on I2C. It exercises a mature Zephyr driver and the same C numerical core. A successfully linked image is software evidence, not support established on physical equipment. Do not flash this over unrelated contents. Actual board/carrier revision inspection, voltage/pin verification, backup/recovery of existing firmware and explicit flashing authority are prerequisites for commissioning.

Pinned source: [Zephyr v4.2.0](https://github.com/zephyrproject-rtos/zephyr/tree/v4.2.0), commit `413b789deb391d3a37d06b463288a5fe765ee57e`. It defines ADXL345 I2C, its data-ready callback and nominal 100/200/400 Hz rates. The driver returns acceleration in SI units. This adapter exposes z only and uses a conservative ±2g software clipping threshold. Its driver scaling is not a physical calibration.

The reference pin mapping is from the pinned [DK device tree](https://github.com/zephyrproject-rtos/zephyr/blob/v4.2.0/boards/nordic/nrf52840dk/nrf52840dk_nrf52840.dts), [pin control](https://github.com/zephyrproject-rtos/zephyr/blob/v4.2.0/boards/nordic/nrf52840dk/nrf52840dk_nrf52840-pinctrl.dtsi), [driver](https://github.com/zephyrproject-rtos/zephyr/tree/v4.2.0/drivers/sensor/adi/adxl345) and [Analog Devices datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ADXL345.pdf). This is not a verified mapping for an unidentified carrier board.

| Provisional endpoint | Connect to |
|---|---|
| DK P0.26 / I2C0 SDA | ADXL345 SDA |
| DK P0.27 / I2C0 SCL | ADXL345 SCL |
| DK P0.04 / Arduino A1 | ADXL345 INT2, active high |
| Common ground | Sensor ground |
| Compatible regulated sensor rail | Sensor supply and I/O supply, after exact carrier verification |
| ADXL345 CS | Compatible I/O high for I2C mode, per carrier documentation |
| ADXL345 ALT ADDRESS | Low for address 0x53, per carrier documentation |

Verify supply and I/O voltage, pull-up voltage/resistance, connector pin labels and interrupt routing against the actual carrier before wiring. ADXL345 chip ratings do not establish a breakout board's ratings. No current/rail headroom, cable retention or physical mounting approval is claimed here. Do not attach a heavy development board to a cantilever.

## Build only

Use an isolated workspace and the official free Zephyr SDK 0.17.2 ARM toolchain. The current Mac build used pinned west 1.4.0, CMake 3.31.6 and Ninja 1.11.1.4 plus Zephyr's requirements-base.txt. Official SDK archive SHA-256 checks are mandatory before executing a downloaded compiler. No setup command below flashes hardware or exposes a network server.

```sh
python -m venv zephyr-tools
. zephyr-tools/bin/activate
python -m pip install west==1.4.0 cmake==3.31.6 ninja==1.11.1.4
west init -m https://github.com/zephyrproject-rtos/zephyr --mr v4.2.0 zephyr-work
cd zephyr-work
west update cmsis cmsis_6 hal_nordic
python -m pip install -r zephyr/scripts/requirements-base.txt
# Install verified official SDK 0.17.2 ARM toolchain in a task-owned directory.
export ZEPHYR_BASE="$PWD/zephyr"
export ZEPHYR_SDK_INSTALL_DIR=/absolute/path/to/zephyr-sdk-0.17.2
export ZEPHYR_TOOLCHAIN_VARIANT=zephyr
# From the InstrumentZero checkout with its Python package installed:
instrumentzero edge compile examples/edge/adxl345-spec.json --placement raw_host --output bindings-raw
west build -b nrf52840dk/nrf52840 /absolute/path/to/InstrumentZero/firmware/zephyr -d /absolute/path/to/new-build -- -DIZ_BINDINGS_DIR=/absolute/path/to/InstrumentZero/bindings-raw -DDTC_OVERLAY_FILE=/absolute/path/to/InstrumentZero/firmware/zephyr/boards/nrf52840dk_nrf52840.overlay
```

Use a fresh build directory for each allocation envelope. All runtime images contain the three reviewed placements; `--placement` labels the generated default binding. The acknowledged runtime request selects native calibration or FIR/decimation in the consumer thread. Retain raw validation when an exact raw recording is required; filtered-only frames cannot feed the raw recorder/recompute path. The planner includes a fixed runtime reserve in its total RAM budget. Full RTOS/driver linker RAM is checked separately; runtime high-water usage remains unmeasured.

## Acquisition lifecycle

Acquisition delivery remains disabled until the consented host configures the device, checks the matching acknowledgement and sends `G`. A `K` keepalive is sent every 0.5 seconds. `S`, a lost keepalive after two seconds, queue overflow or a fetch/clipping fault stops sampling delivery. The source callback performs acquisition only; bounded queue and consumer isolate UART/DSP work. Cancellation sends `S`, restores serial settings and closes the host handle. No flash command exists in the CLI. Every accepted configuration creates a fresh UUID and advances the epoch. Supported rate, signed calibration, FIR/reduction and placement settings may change at runtime; block and queue allocations must match the compiled envelope. An unused accepted configuration expires after two seconds. This path is software-tested and cross-compiled, with physical behavior still unverified.

The raw sensor route is explicit and **has not been executed on actual hardware**:

```sh
instrumentzero edge capture examples/edge/adxl345-spec.json --device /dev/EXACT_SERIAL_DEVICE --seconds 8 --output new-trial.izp --consent
instrumentzero edge protocol examples/edge/adxl345-spec.json new-trial.izp --firmware-sha256 EXACT_LINKED_IMAGE_SHA256 --consent --export trial.zip
```

Capture/import never overwrite existing trial files. Capture also keeps an exclusive-created sidecar with the exact specification and success/failure/cancellation outcome. Failed, partial and truncated captures remain for inspection. A new physical reference, real sample jitter/drift/rollover, masked/hidden IRQ losses, analog aliasing, serial unplug/cancel, actual memory high-water mark, utilization and total acquisition-to-result latency remain commissioning gates. A passing build or simulation must not promote these to verified status.


## Firmware licensing

The provisional linked nRF52840 firmware uses Zephyr v4.2.0 (Apache-2.0), ARM CMSIS (Apache-2.0), Nordic nrfx drivers (BSD-3-Clause), and the official Zephyr SDK 0.17.2 runtime libraries. Relevant Picolibc/Newlib notices and GCC Runtime Library Exception/GPL notices are retained under `firmware/zephyr/notices/`. No compiler executable or SDK archive is redistributed. Exact upstream commits are in the build manifest and pinned Zephyr west manifest. Neither Nordic, Analog Devices, ARM nor Zephyr endorses this project; a successful build does not establish physical sensor operation.
