# Contributing

Thanks for helping out.

## Where does a change belong?

This repository holds the **Home Assistant integration**. The Modbus register
map — addresses, scaling, units, ranges, enumerations and device models — lives
in the [`lg-heatpump-modbus`][library] device library and is vendored in here.

| Change | Where |
| :----- | :---- |
| A wrong address, scaling or unit | Device library |
| A missing datapoint | Device library |
| A new heat pump variant | Device library (`configurations/models.py`) |
| A new entity for an existing datapoint | Here |
| Entity naming, icons, translations | Here |
| Config flow, coordinators, diagnostics | Here |

Fixing the library first and vendoring the result keeps the register map usable
by non-Home-Assistant projects, which is the whole point of splitting it out.

## Development environment

The repository ships a dev container: open it in VS Code and everything is
installed. Otherwise:

```bash
scripts/setup      # install dependencies
scripts/develop    # run Home Assistant with this integration loaded
scripts/lint       # format and lint
scripts/test       # run the test suite
```

Home Assistant is then at <http://localhost:8123>. Add the integration from
**Settings → Devices & services**.

## Working on the vendored library

```bash
# Check out the library next to this repository, then:
scripts/vendor                  # refresh the copy
python3 scripts/check_vendored.py   # prove the copy is faithful
```

If the library lives elsewhere, either run
`scripts/vendor /path/to/lg-heatpump-modbus` or point `LIBRARY_SOURCE` at
`.../src/lg_heatpump_modbus` before running either script.

Never edit `custom_components/lg_heatpump/lg_heatpump_modbus` directly. It is a
verbatim copy, ruff skips it, and CI fails if it has drifted.

## Tests

```bash
scripts/test
```

Every test runs against `modbus-connection`'s in-memory mock backend, so no heat
pump, gateway or network is involved. A test seeds registers, sets the
integration up, and asserts on entity states or on the register a write landed
in — see `tests/__init__.py` for the seeded heat pump image.

New entities need a test. New register behaviour needs a test in the device
library, not here.

## Before opening a pull request

```bash
scripts/lint
scripts/test
python3 scripts/check_vendored.py
```

CI additionally runs [hassfest][hassfest] and the [HACS action][hacs-action],
which validate the manifest, translations, icons and repository layout.

## Reporting a register problem

Please attach the integration's **Diagnostics** download. It contains the raw,
undecoded register map read from your heat pump, and that is what makes a
scaling or address bug fixable without owning your hardware.

[library]: https://github.com/lg-heatpump/lg-heatpump-modbus
[hassfest]: https://developers.home-assistant.io/blog/2020/04/16/hassfest
[hacs-action]: https://github.com/hacs/action
