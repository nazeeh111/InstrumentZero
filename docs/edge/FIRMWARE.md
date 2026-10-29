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

Use a fresh build directory for each placement. `--placement calibrated_edge` or `filtered_edge` binds native calibration or FIR/decimation in the consumer thread. Retain raw validation when an exact raw recording is required; filtered-only frames cannot feed the raw recorder/recompute path. The planner includes a fixed runtime reserve in its total RAM budget. Full RTOS/driver linker RAM is checked separately; runtime high-water usage remains unmeasured.

## Acquisition lifecycle

Firmware remains idle until the explicitly consented host sends `G`. A `K` keepalive is sent every 0.5 seconds. `S`, a lost keepalive after two seconds, queue overflow or a fetch/clipping fault stops sampling delivery. The source callback performs acquisition only; bounded queue and consumer isolate UART/DSP work. Cancellation sends `S`, restores serial settings and closes the host handle. No flash command exists in the CLI. A new start creates a new UUID. Compiled hardware configuration is fixed for that image; runtime graph reconfiguration on physical hardware is not implemented/verified in this preview.

The raw sensor route is explicit and **has not been executed on actual hardware**:

```sh
instrumentzero edge capture examples/edge/adxl345-spec.json --device /dev/EXACT_SERIAL_DEVICE --seconds 8 --output new-trial.izp --consent
instrumentzero edge protocol examples/edge/adxl345-spec.json new-trial.izp --firmware-sha256 EXACT_LINKED_IMAGE_SHA256 --consent --export trial.zip
```

Capture/import never overwrite existing trial files. Capture also keeps an exclusive-created sidecar with the exact specification and success/failure/cancellation outcome. Failed, partial and truncated captures remain for inspection. A new physical reference, real sample jitter/drift/rollover, masked/hidden IRQ losses, analog aliasing, serial unplug/cancel, actual memory high-water mark, utilization and total acquisition-to-result latency remain commissioning gates. A passing build or simulation must not promote these to verified status.
