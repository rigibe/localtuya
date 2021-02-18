"""Platform to locally control Tuya-based climate devices."""
import logging
import json
from functools import partial
import json

import voluptuous as vol
from homeassistant.components.climate import (
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DOMAIN,
    ClimateEntity,
)
from homeassistant.components.climate.const import (
    HVAC_MODE_AUTO,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT_COOL,
    HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY,
    SUPPORT_FAN_MODE,
    SUPPORT_PRESET_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_TARGET_TEMPERATURE_RANGE,
    CURRENT_HVAC_OFF,
    CURRENT_HVAC_HEAT,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_TEMPERATURE_UNIT,
    PRECISION_HALVES,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
)

from .common import LocalTuyaEntity, async_setup_entry
from .const import (
    CONF_CURRENT_TEMPERATURE_DP,
    CONF_FAN_MODE_DP,
    CONF_MAX_TEMP_DP,
    CONF_MIN_TEMP_DP,
    CONF_PRECISION,
    CONF_TARGET_TEMPERATURE_DP,
    CONF_TEMPERATURE_STEP,
    CONF_PRESETS,
    CONF_HVAC_MODES,
    CONF_EURISTIC_ACTION,
    CONF_HVAC_ACTION,
)

from . import pytuya

_LOGGER = logging.getLogger(__name__)

TEMPERATURE_CELSIUS = "celsius"
TEMPERATURE_FAHRENHEIT = "fahrenheit"
DEFAULT_TEMPERATURE_UNIT = TEMPERATURE_CELSIUS
DEFAULT_PRECISION = PRECISION_TENTHS
DEFAULT_TEMPERATURE_STEP = PRECISION_HALVES


def flow_schema(dps):
    """Return schema used in config flow."""
    return {
        vol.Optional(CONF_TARGET_TEMPERATURE_DP): vol.In(dps),
        vol.Optional(CONF_CURRENT_TEMPERATURE_DP): vol.In(dps),
        vol.Optional(CONF_TEMPERATURE_STEP): vol.In(
            [PRECISION_WHOLE, PRECISION_HALVES, PRECISION_TENTHS]
        ),
        vol.Optional(CONF_FAN_MODE_DP): vol.In(dps),
        vol.Optional(CONF_MAX_TEMP_DP): vol.In(dps),
        vol.Optional(CONF_MIN_TEMP_DP): vol.In(dps),
        vol.Optional(CONF_PRECISION): vol.In(
            [PRECISION_WHOLE, PRECISION_HALVES, PRECISION_TENTHS]
        ),
        vol.Optional(CONF_TEMPERATURE_UNIT): vol.In(
            [TEMPERATURE_CELSIUS, TEMPERATURE_FAHRENHEIT]
        ),
        vol.Required(CONF_HVAC_MODES, default="{}"): str,
        vol.Required(CONF_PRESETS, default="{}"): str,
        vol.Required(CONF_HVAC_ACTION, default="{}"): str,
        vol.Optional(CONF_EURISTIC_ACTION, default=False): bool,
    }


class LocaltuyaClimate(LocalTuyaEntity, ClimateEntity):
    """Tuya climate device."""

    def __init__(
        self,
        device,
        config_entry,
        switchid,
        **kwargs,
    ):
        """Initialize a new LocaltuyaClimate."""
        super().__init__(device, config_entry, switchid, _LOGGER, **kwargs)
        self._state = None
        self._target_temperature = None
        self._current_temperature = None
        self._hvac_mode = None
        self._preset_mode = None
        self._hvac_action = None
        self._precision = self._config.get(CONF_PRECISION, DEFAULT_PRECISION)
        self._conf_hvac_modes = eval(self._config[CONF_HVAC_MODES])
        self._conf_presets = eval(self._config[CONF_PRESETS])
        self._conf_hvac_actions = eval(self._config[CONF_HVAC_ACTION])
        print("Initialized climate [{}]".format(self.name))

    @property
    def supported_features(self):
        """Flag supported features."""
        supported_features = 0
        if self.has_config(CONF_TARGET_TEMPERATURE_DP):
            supported_features = supported_features | SUPPORT_TARGET_TEMPERATURE
        if self.has_config(CONF_MAX_TEMP_DP):
            supported_features = supported_features | SUPPORT_TARGET_TEMPERATURE_RANGE
        if self.has_config(CONF_FAN_MODE_DP):
            supported_features = supported_features | SUPPORT_FAN_MODE
        if list(self._conf_presets):
            supported_features = supported_features | SUPPORT_PRESET_MODE
        return supported_features

    @property
    def precision(self):
        """Return the precision of the system."""
        return self._precision

    @property
    def temperature_unit(self):
        """Return the unit of measurement used by the platform."""
        if (
            self._config.get(CONF_TEMPERATURE_UNIT, DEFAULT_TEMPERATURE_UNIT)
            == TEMPERATURE_FAHRENHEIT
        ):
            return TEMP_FAHRENHEIT
        return TEMP_CELSIUS

    @property
    def hvac_mode(self):
        """Return current operation ie. heat, cool, idle."""
        return self._hvac_mode

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return (list(self._conf_hvac_modes))

    @property
    def hvac_action(self):
        """Return the current running hvac operation if supported.
        Need to be one of CURRENT_HVAC_*.
        """
        if self._config[CONF_EURISTIC_ACTION]:
            if self._hvac_mode == HVAC_MODE_HEAT:
                if self._current_temperature < (self._target_temperature - self._precision):
                    self._hvac_action = CURRENT_HVAC_HEAT
                if self._current_temperature == (self._target_temperature - self._precision):
                    if self._hvac_action == CURRENT_HVAC_HEAT:
                        self._hvac_action = CURRENT_HVAC_HEAT
                    if self._hvac_action == CURRENT_HVAC_OFF:
                        self._hvac_action = CURRENT_HVAC_OFF
                if (self._current_temperature + self._precision) > self._target_temperature:
                    self._hvac_action = CURRENT_HVAC_OFF
            return self._hvac_action
        return self._hvac_action

    @property
    def preset_mode(self):
        """Return current preset"""
        return self._preset_mode

    @property
    def preset_modes(self):
        """Return the list of available presets modes."""
        return (list(self._conf_presets))
        #return (list(presets))

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temperature

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return self._config.get(CONF_TEMPERATURE_STEP, DEFAULT_TEMPERATURE_STEP)

    @property
    def fan_mode(self):
        """Return the fan setting."""
        return NotImplementedError()

    @property
    def fan_modes(self):
        """Return the list of available fan modes."""
        return NotImplementedError()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_TEMPERATURE in kwargs and self.has_config(CONF_TARGET_TEMPERATURE_DP):
            temperature = round(kwargs[ATTR_TEMPERATURE] / self._precision)
            await self._device.set_dp(temperature, self._config[CONF_TARGET_TEMPERATURE_DP])

    def set_fan_mode(self, fan_mode):
        """Set new target fan mode."""
        return NotImplementedError()

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target operation mode."""
        for k in self._conf_hvac_modes[hvac_mode].keys():
            v = self._conf_hvac_modes[hvac_mode].get(k)
            await self._device.set_dp(v, k)

    async def async_set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        for k in self._conf_presets[preset_mode].keys():
            v = self._conf_presets[preset_mode].get(k)
            await self._device.set_dp(v, k)
       
    @property
    def min_temp(self):
        """Return the minimum temperature."""
        if self.has_config(CONF_MIN_TEMP_DP):
            return self.dps_conf(CONF_MIN_TEMP_DP)
        #return DEFAULT_MIN_TEMP
        return 5

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        if self.has_config(CONF_MAX_TEMP_DP):
            return self.dps_conf(CONF_MAX_TEMP_DP)
        return DEFAULT_MAX_TEMP

    def status_updated(self):
        """Device status was updated."""
        self._state = self.dps(self._dp_id)

        if self.has_config(CONF_TARGET_TEMPERATURE_DP):
            self._target_temperature = (
                self.dps_conf(CONF_TARGET_TEMPERATURE_DP) * self._precision
            )

        if self.has_config(CONF_CURRENT_TEMPERATURE_DP):
            self._current_temperature = (
                self.dps_conf(CONF_CURRENT_TEMPERATURE_DP) * self._precision
            )

        #_LOGGER.debug("the test is %s", test)

        """Update the HVAC status"""
        for mode in self._conf_hvac_modes:
            if self.dps_all().items() & self._conf_hvac_modes[mode].items() == self._conf_hvac_modes[mode].items():
                self._hvac_mode = mode

        """Update the preset status"""
        for preset in self._conf_presets:
            if self.dps_all().items() & self._conf_presets[preset].items() == self._conf_presets[preset].items():
                self._preset_mode = preset

        """Update the current action"""
        for action in self._conf_hvac_actions:
            if self.dps_all().items() & self._conf_hvac_actions[action].items() == self._conf_hvac_actions[action].items():
                self._hvac_action = action
       
async_setup_entry = partial(async_setup_entry, DOMAIN, LocaltuyaClimate, flow_schema)