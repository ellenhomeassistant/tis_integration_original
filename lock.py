from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant
from .const import DOMAIN
from TISControlProtocol.api import TISApi
import asyncio
import logging


async def async_setup_entry(hass: HomeAssistant, entry, async_add_devices):
    tis_api: TISApi = entry.runtime_data.api
    lock_module = await tis_api.get_entities(platform="lock_module")

    if lock_module is None:
        logging.error("No lock module found in the configuration")
        return
    else:
        async_add_devices([TISControlLock("Admin Lock", lock_module["password"])])


class TISControlLock(LockEntity):
    def __init__(self, name, password):
        self._attr_name = name
        self.unique_id = f"lock_{self.name}"
        self._attr_is_locked = True
        self._attr_password = password
        self._attr_changed_by = None
        self._attr_code_format = r".*"
        self._attr_is_locking = False
        self._attr_is_unlocking = False
        self._attr_is_opening = False
        self._attr_is_open = False
        self._attr_timeout = 60

    @property
    def name(self):
        return self._attr_name

    @property
    def is_locked(self):
        return self._attr_is_locked

    async def async_lock(self, **kwargs):
        if "code" in kwargs and kwargs["code"] == self._attr_password:
            self._attr_is_locked = True
            self._attr_changed_by = "user"
            # make protected entities read only
            self.hass.bus.async_fire(str("admin_lock"), {"locked": True})
        else:
            raise ValueError("Invalid password")

    async def async_unlock(self, **kwargs):
        if "code" in kwargs and kwargs["code"] == self._attr_password:
            self._attr_is_locked = False
            self._attr_changed_by = "user"
            # make protected entities read and write
            self.hass.bus.async_fire(str("admin_lock"), {"locked": False})
            # Cancel the previous task if it exists
            if hasattr(self, "_auto_lock_task") and self._auto_lock_task:
                self._auto_lock_task.cancel()

            # Schedule the automatic locking of the lock after 30 seconds
            self._auto_lock_task = asyncio.create_task(self.auto_lock())
        else:
            raise ValueError("Invalid password")

    async def auto_lock(self):
        await asyncio.sleep(self._attr_timeout)
        await self.async_lock(code=self._attr_password)

    async def async_open(self, **kwargs):
        if "code" in kwargs and kwargs["code"] == self._attr_password:
            self._attr_is_open = True
            self._attr_changed_by = "user"
        else:
            raise ValueError("Invalid password")
