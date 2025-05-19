"""The TISControl integration."""

from __future__ import annotations

import logging
import os

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


    #------ Security Settings Setup
    current_dir = os.path.dirname(__file__)
    base_dir = os.path.abspath(os.path.join(current_dir, "../../"))
    config_path = os.path.join(base_dir, "configuration.yaml")
    dashboard_filename = "security_lock_settings.yaml"
    dashboard_path = os.path.join(base_dir, dashboard_filename)
    try:
        # YAML setup
        yaml = YAML()
        yaml.preserve_quotes = True

        # 1. Load configuration.yaml
        with open(config_path, 'r') as f:
            config = yaml.load(f)

        # 2. Add dashboard if missing
        if 'lovelace' not in config:
            config['lovelace'] = {}
        if 'dashboards' not in config['lovelace']:
            config['lovelace']['dashboards'] = {}

        if 'security-lock-settings' not in config['lovelace']['dashboards']:
            config['lovelace']['dashboards']['security-lock-settings'] = {
                'mode': 'yaml',
                'title': 'Security Lock Settings',
                'icon': 'mdi:lock',
                'show_in_sidebar': True,
                'filename': dashboard_filename
            }


        # 3. Save configuration.yaml
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        # 4. Create dashboard file if not exists
        if not os.path.exists(dashboard_path):
            dashboard_content = {
                'title': 'YAML Dashboard',
                'views': [
                    {
                        'title': 'Settings',
                        'path': 'main',
                        'cards': [
                            {
                                'type': 'button',
                                'name': 'Change Password',
                                'icon': 'mdi:lock',
                                'tap_action': {
                                    'action': 'url',
                                    'url_path': 'http://homeassistant.local:8000/api/change-password'
                                }
                            }
                        ]
                    }
                ]
            }
            with open(dashboard_path, 'w') as f:
                yaml.dump(dashboard_content, f)
    except Exception as e:
        logging.error(f"Could Not Setup Security Settings Dashboard: {e}")


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
