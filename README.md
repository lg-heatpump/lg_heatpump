# LG Heat Pump for Home Assistant

[![HACS Custom][hacs-shield]][hacs]
[![GitHub Release][release-shield]][releases]
[![License][license-shield]](LICENSE)

[![Lint][lint-shield]][lint]
[![Validate][validate-shield]][validate]
[![Tests][tests-shield]][tests]

Home Assistant integration for **LG heat pumps** — the Therma V family (both R32 and R290) and the
siblings that share its Modbus register map. Set up from the UI, polled locally
over Modbus TCP, with no cloud account and no YAML.

This is the HACS build. There are three different ways to control your LG heat pump via Modbus in Home Assistant:

| Integration         | YAML-based *(legacy)*                                                                                                   | HACS Integration *(this repository)*  | Core Integration *(coming soon)*                                                               |
|:--------------------|:------------------------------------------------------------------------------------------------------------------------|:--------------------------------------|:-----------------------------------------------------------------------------------------------|
| Installation method | Manually handling of YAML-files                                                                                         | Relatively easy installation via HACS | No installation required, included in HA core - just click "Add device" and select integration |
| Device library      | No library, hard-coded register map                                                                                     | `lg-heatpump-modbus` (vendored)       | `lg-heatpump-modbus` (installed via PyPI)                                                      |
| Modbus library      | `pymodbus`                                                                                                              | `modbus-connection` / `tmodbus`       | `modbus-connection` / `tmodbus`                                                                |
| Setup from UI       | No                                                                                                                      | Yes                                   | Yes                                                                                            |
| Maintainability     | Hard                                                                                                                    | Medium/Easy                           | Easy                                                                                           |
| Limitations         | No UI setup. Entities do not belong to any device. Complicated entity handling. Hard to update. Can cause conflicts with other Modbus communications | Might get breaking changes. Requires at least HA 2026.9                                         | Not available yet      |


Currently, this HACS integration is the recommended way. 

## What you get

| Platform | Entities |
| :------- | :------- |
| `climate` | One thermostat per water circuit, following the heat pump's own control method |
| `water_heater` | The domestic hot water tank |
| `sensor` | Temperatures, pressures, flow rate, compressor speed, error code, energy state; plus two debug sensors (disabled by default) with the time of the last measurement and settings poll |
| `binary_sensor` | Compressor, pumps, defrost, backup heater, disinfection, fault flags; plus two debug sensors (disabled by default) that turn on when a measurement or settings poll failed, fully or in part |
| `button` | Refresh data now: polls the measurements and the settings immediately, outside the regular schedule |
| `switch` | Power, silent mode, disinfection |
| `number` | Weather-compensation setpoint shift per circuit |
| `select` | Control method (water outlet / water inlet) |

Everything is read locally. A full poll of the whole heat pump costs five Modbus
block reads.

## Requirements

* Home Assistant 2026.9.1 or newer.
* The heat pump's Modbus interface (PI485 / third-party control module) wired to
  a **Modbus TCP gateway** — a serial-to-Ethernet bridge, or an ESPHome Modbus
  bridge — reachable from Home Assistant.
* The heat pump's Modbus unit ID, also called its slave or station address.

## Installation

### HACS (recommended)

1. In HACS, open the three-dot menu and choose **Custom repositories**.
2. Add `https://github.com/lg-heatpump/lg_heatpump` with category **Integration**.
3. Search HACS for **LG Heat Pump** and install it.
4. Restart Home Assistant.

### Manual

1. Download the latest release.
2. Copy `custom_components/lg_heatpump` into your Home Assistant `config/custom_components` directory.
3. Restart Home Assistant.

## Configuration

Go to **Settings → Devices & services → Add integration** and search for
**LG Heat Pump**. You will be asked for:

| Field | Meaning |
| :---- | :------ |
| Host | Hostname or IP of the Modbus TCP gateway |
| Port | Modbus TCP port, usually 502 |
| Modbus unit ID | The heat pump's station address, usually 1 |
| Model | The installation this heat pump is part of |

The integration reads the heat pump once before creating the entry, so a wrong
host, port or unit ID is reported immediately rather than after setup.

All four fields can be changed later with **Reconfigure** on the integration's
entry.

### Choosing the model

The **Model** field is what keeps Home Assistant from asking your heat pump for
registers it does not have. An installation without a second circuit or without
a hot water tank should not be polled for one: naming the model narrows both the
read plan and the entities that get created.

| Model | Circuits | Hot water | Solar | Mixing valve |
| :---- | :------: | :-------: | :---: | :----------: |
| LG Therma V | 2 | ✔ | ✔ | ✔ |
| LG Therma V (single circuit) | 1 | ✔ | | |
| LG Therma V (heating only) | 2 | | ✔ | ✔ |

If your installation is not covered, pick the closest match and open an issue —
a variant is added to the device library as data, not as code.

## How it polls

Two independent polls run against the heat pump:

| Poll         | Interval   | Reads |
|:-------------|:-----------| :---- |
| Measurements | 30 seconds | Input registers and discrete inputs |
| Settings     | 60 seconds | Holding registers and coils |

Setpoints do not change on their own, so re-reading them every 30 seconds only
loads the bus. A write refreshes both polls immediately, so a change you make in
Home Assistant is reflected as soon as the heat pump has taken it.

Each sub-system reads only its own registers. One block the heat pump refuses
makes only that sub-system's entities unavailable; the rest keep updating.

## Troubleshooting

**The entry never finishes setting up.** The heat pump is not answering. Check
the gateway is reachable, the unit ID matches, and no client outside Home Assistant is polling
the bus — a Modbus device answers one request at a time.

**Some entities are unavailable, the rest are fine.** That sub-system's block
read was refused. It usually means one of two things: 
- The model is wrong for your installation: Reconfigure the entry and pick one that matches, or open an issue with the
diagnostics attached.
- Another application is communicating with the heat pump via Modbus at the same time (e.g., legacy YAML integration, different HA installation, HEMS, or manually ran device library)

**A value is obviously wrong.** Download **Diagnostics** from the integration's
device page and open an issue. The dump contains the raw, undecoded register map,
which is what makes a scaling or address bug fixable.

To collect logs, add this to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.lg_heatpump: debug
    modbus_connection: debug
```
## Manual Additions

An extra switch to turn on/off warm water can easily be added as a helper -> template -> switch:

```yaml
template:
  - switch:
      - name: Warmwasser
        unique_id: hot_water_toggle
        state: "{{ is_state('water_heater.lg_therma_v_hot_water', 'on') }}"
        turn_on:
          service: water_heater.set_operation_mode
          target:
            entity_id: water_heater.lg_therma_v_hot_water
          data:
            operation_mode: on
        turn_off:
          service: water_heater.set_operation_mode
          target:
            entity_id: water_heater.lg_therma_v_hot_water
          data:
            operation_mode: off
```


## Development

The repository ships a dev container. Open it in VS Code and everything is
installed for you. Otherwise:

```bash
scripts/setup     # install dependencies
scripts/develop   # run Home Assistant with this integration loaded
scripts/lint      # format and lint
scripts/test      # run the test suite
scripts/vendor    # refresh the vendored device library
```

If `lg-heatpump-modbus` is not checked out next to this repository, either run
`scripts/vendor /path/to/lg-heatpump-modbus` or set `LIBRARY_SOURCE` to its
`src/lg_heatpump_modbus` directory before running the vendoring scripts.

The test suite runs against `modbus-connection`'s in-memory mock backend, so it
needs no heat pump, no gateway and no network.

The register map itself lives in the device library, not here. A wrong address,
a wrong scaling or a missing datapoint is fixed in [`lg-heatpump-modbus`][library]
and pulled in with `scripts/vendor`.

## Licence

Apache-2.0. See [LICENSE](LICENSE).

[library]: https://github.com/lg-heatpump/lg-heatpump-modbus
[hacs]: https://hacs.xyz
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[releases]: https://github.com/lg-heatpump/lg_heatpump/releases
[release-shield]: https://img.shields.io/github/release/lg-heatpump/lg_heatpump.svg
[license-shield]: https://img.shields.io/badge/license-Apache--2.0-blue.svg
[lint]: https://github.com/lg-heatpump/lg_heatpump/actions/workflows/lint.yml
[lint-shield]: https://github.com/lg-heatpump/lg_heatpump/actions/workflows/lint.yml/badge.svg
[validate]: https://github.com/lg-heatpump/lg_heatpump/actions/workflows/validate.yml
[validate-shield]: https://github.com/lg-heatpump/lg_heatpump/actions/workflows/validate.yml/badge.svg
[tests]: https://github.com/lg-heatpump/lg_heatpump/actions/workflows/test.yml
[tests-shield]: https://github.com/lg-heatpump/lg_heatpump/actions/workflows/test.yml/badge.svg
