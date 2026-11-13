# Migrating from the legacy YAML package

This guide is for installations that used the YAML package
[homeassistant_lg_therma_v_modbus](https://github.com/basti242/homeassistant_lg_therma_v_modbus)
(Modbus hub `lg_heatpump`, entities named `hp_*`).

## 1. Switch the old package off first

A Modbus device answers one request at a time, so the YAML package and this
integration must **not** read the heat pump at the same time (see
"Troubleshooting" in the README).

1. Remove the package (the `!include` of `modbus_lg_heatpump.yaml`, or the
   whole file / submodule).
2. Reload the Modbus configuration (**Developer tools → YAML → Modbus**) or
   restart Home Assistant. This also reloads any other YAML Modbus hub you have.
3. Add the integration (**Settings → Devices & services → Add integration →
   LG Heat Pump**), same host, port and unit ID as before.

## 2. What replaces what

| Legacy YAML package | Integration |
| :------------------ | :---------- |
| `switch.hp_hauptschalter` (coil 0) | Switch **Heating circuit** (space heating and cooling only, not hot water) |
| `switch.hp_dhw` (coil 1) | `water_heater` **Hot water**: `water_heater.turn_on` / `turn_off` |
| `number.hp_dhw_target_temperatur_number` | `water_heater` **Hot water**: `water_heater.set_temperature` (30 to 80 °C), the target is the attribute `temperature` |
| `select.hp_operation_mode_select` | Select **Operation mode** (auto / heating), the same register. Or `climate` **Circuit 1/2**: HVAC mode off / heat / auto, where heat and auto also switch the heating circuit on. Cooling is not enabled yet |
| `select.hp_control_method_select` | Select **Control method** |
| `number.hp_shift_value_in_auto_mode_circuit1/2_number` | Number **Circuit 1/2 setpoint shift** (-5 to +5 K) |
| `switch.hp_silent_mode` (coil 2) | Switch **Silent mode** |
| `switch.hp_dhw_desinfection_mode` (coil 3) | Switch **Hot water disinfection** |
| `binary_sensor.hp_*_status` (discrete inputs) | Binary sensors (diagnostic, some disabled by default) |
| `sensor.hp_*` temperatures, pressures, flow rate, compressor | Sensors of the same meaning (some disabled by default) |
| `hp_power_limit`, `hp_energy_state_select`, emergency stop switches | Not provided (the energy state is a read-only sensor) |
| `*_raw` helper sensors | Not needed |

Note the changed units: compressor speed is `rpm`, flow rate `L/min`, pressure `bar`.

Entities that are disabled by default (refrigerant temperatures and
pressures, backup heater, extra pumps) can be enabled on the device page.

## 3. Keeping entity IDs and history

New entities get new IDs. If dashboards, automations or long-term statistics
use the old IDs and you want to keep them:

1. In **Settings → Devices & services → Entities**, delete the orphaned old
   entities (state "unavailable", source Modbus or Template). Home Assistant
   refuses to rename an entity to an ID that is still registered.
2. Rename the new entities to the old IDs (entity settings → entity ID).
   Statistics follow the entity ID.
3. If the statistic unit differs (for example `l/min` to `L/min`, `U/min` to
   `rpm`, `Bar` to `bar`), fix it in **Developer tools → Statistics**
   (update the unit, do not delete).

Anything that was a `number` or `select` and is now a `water_heater` or
`climate` entity needs a change in the automations and dashboard cards that
use it (service calls change from `number.set_value` to
`water_heater.set_temperature`).
