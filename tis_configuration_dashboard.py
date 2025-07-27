import os
from ruamel.yaml import YAML
import logging


# ------ Security Settings Setup
def create():
    current_dir = os.path.dirname(__file__)
    base_dir = os.path.abspath(os.path.join(current_dir, "../../"))
    config_path = os.path.join(base_dir, "configuration.yaml")
    dashboard_filename = "tis_configuration.yaml"
    dashboard_path = os.path.join(base_dir, dashboard_filename)
    try:
        # YAML setup
        yaml = YAML()
        yaml.preserve_quotes = True

        # 1. Load configuration.yaml
        with open(config_path, "r") as f:
            config = yaml.load(f)

        # 2. Add dashboard if missing
        if "lovelace" not in config:
            config["lovelace"] = {}
        if "dashboards" not in config["lovelace"]:
            config["lovelace"]["dashboards"] = {}

        if "tis-configuration" not in config["lovelace"]["dashboards"]:
            config["lovelace"]["dashboards"]["tis-configuration"] = {
                "mode": "yaml",
                "title": "TIS Configuration",
                "icon": "mdi:tune",
                "show_in_sidebar": True,
                "filename": dashboard_filename,
                "require_admin": True,
            }

        # 3. Save configuration.yaml
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        # 4. Create dashboard file if not exists
        if not os.path.exists(dashboard_path):
            dashboard_content = {
                "title": "YAML Dashboard",
                "views": [
                    {
                        "title": "TIS Configuration",
                        "path": "main",
                        "cards": [
                            {
                                "type": "button",
                                "name": "Change Lock Password",
                                "icon": "mdi:lock",
                                "tap_action": {
                                    "action": "url",
                                    "url_path": "http://homeassistant.local:8000/api/change-password",
                                },
                            },
                            {
                                "type": "button",
                                "name": "Tier Price",
                                "icon": "mdi:flash",
                                "tap_action": {
                                    "action": "url",
                                    "url_path": "http://homeassistant.local:8000/api/electricity-bill",
                                },
                            },
                        ],
                    }
                ],
            }
            with open(dashboard_path, "w") as f:
                yaml.dump(dashboard_content, f)
    except Exception as e:
        logging.error(f"Could Not Setup Security Settings Dashboard: {e}")
