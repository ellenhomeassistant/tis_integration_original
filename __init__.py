"""The TISControl integration."""

from __future__ import annotations

import logging
import os
from aiohttp import web
import psutil
import uuid

from attr import dataclass
from TISControlProtocol.api import *
from TISControlProtocol.Protocols.udp.ProtocolHandler import TISProtocolHandler

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DEVICES_DICT, DOMAIN


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
    try:
        current_directory = os.getcwd()
        os.chdir("/config/custom_components/tis_integration")
        reset = os.system("git reset --hard HEAD")
        fetch = os.system("git fetch --depth 1 origin main")
        reset_to_origin = os.system("git reset --hard origin/main")

        os.chdir(current_directory)

        if fetch == 0 and reset == 0 and reset_to_origin == 0:
            logging.warning("Updated TIS Integrations")
        else:
            logging.warning(
                f"Could Not Update TIS Integration: exit error {fetch}, {reset}, {reset_to_origin}"
            )

    except Exception as e:
        logging.error(f"Could Not Update TIS Integration: {e}")

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
        hass.http.register_view(CMSEndpoint(tis_api))
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


class CMSEndpoint(HomeAssistantView):
    """Send data to CMS for monitoring."""

    url = "/api/cms"
    name = "api:cms"
    requires_auth = False

    def __init__(self, api: TISApi) -> None:
        """Initialize the endpoint."""
        self.api = api

    async def get(self, request):
        try:
            # Mac Address Stuff
            mac = uuid.getnode()
            mac_address = ":".join(("%012X" % mac)[i : i + 2] for i in range(0, 12, 2))
            logging.warning(f"MAC Address: {mac_address}")

            # CPU Stuff
            cpu_usage = await self.api.hass.async_add_executor_job(
                psutil.cpu_percent, 1
            )
            logging.warning(f"CPU Usage: {cpu_usage}")

            cpu_temp = await self.api.hass.async_add_executor_job(
                psutil.sensors_temperatures
            )
            cpu_temp = cpu_temp.get("cpu_thermal", None)
            if cpu_temp is not None:
                cpu_temp = cpu_temp[0].current
            else:
                cpu_temp = 0
            logging.warning(f"CPU Temp: {cpu_temp}")

            cpu = {
                "cpu_usage": cpu_usage,
                "cpu_temp": cpu_temp,
            }
            logging.warning(f"CPU: {cpu}")

            # Disk Stuff
            total, used, free, percent = await self.api.hass.async_add_executor_job(
                psutil.disk_usage, "/"
            )
            disk = {
                "total": total,
                "used": used,
                "free": free,
                "percent": percent,
            }
            logging.warning(f"Disk: {disk}")

            # Memory Stuff
            mem = await self.api.hass.async_add_executor_job(psutil.virtual_memory)
            memory = {
                "total": mem.total,
                "available": mem.available,
                "used": mem.used,
                "percent": mem.percent,
                "free": mem.free,
            }
            logging, Warning(f"Memory: {memory}")

            return web.json_response(
                {
                    "mac_address": mac_address,
                    "cpu": cpu,
                    "disk": disk,
                    "memory": memory,
                }
            )
        except Exception as e:
            logging.error(f"Error in CMSEndpoint: {e}")
            return web.json_response(
                {"error": "Error in CMSEndpoint", "message": str(e)}, status=500
            )
