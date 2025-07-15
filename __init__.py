"""The TISControl integration."""

from __future__ import annotations

import logging
# import os


from attr import dataclass
from TISControlProtocol.api import *
from TISControlProtocol.Protocols.udp.ProtocolHandler import TISProtocolHandler

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DEVICES_DICT, DOMAIN
from . import tis_configuration_dashboard
import aiofiles


@dataclass
class TISData:
    """TISControl data stored in the ConfigEntry."""

    api: TISApi


PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.COVER,
    Platform.CLIMATE,
    Platform.SELECT,
    Platform.LOCK,
    Platform.FAN,
]
type TISConfigEntry = ConfigEntry[TISData]
protocol_handler = TISProtocolHandler()


async def async_setup_entry(hass: HomeAssistant, entry: TISConfigEntry) -> bool:
    """Set up TISControl from a config entry."""

    tis_configuration_dashboard.create()
    http_config = """
    http:
      use_x_forwarded_for: true
      trusted_proxies:
      - 172.30.33.0/24
    """

    async with aiofiles.open("/homeassistant/configuration.yaml", "a") as f:
        if await f.read().find(http_config) == -1:
            logging.warning("adding http configuration to configuration.yaml")
            await f.write("\n" + http_config + "\n")
        else:
            logging.warning()("http configuration already exists in configuration.yaml")

    tis_api = TISApi(
        port=int(entry.data["port"]),
        hass=hass,
        domain=DOMAIN,
        devices_dict=DEVICES_DICT,
        display_logo="./custom_components/tis_integration/images/logo.png",
    )
    entry.runtime_data = TISData(api=tis_api)

    hass.data.setdefault(DOMAIN, {"supported_platforms": PLATFORMS})
    try:
        await tis_api.connect()
    except ConnectionError as e:
        logging.error("error connecting to TIS api %s", e)
        return False
    # add the tis api to the hass data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TISConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return unload_ok

    return False
