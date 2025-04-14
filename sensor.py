"""Sensor platform for TIS Control."""

from datetime import timedelta
import logging

from gpiozero import CPUTemperature  # type: ignore
from TISControlProtocol.api import TISApi
from TISControlProtocol.Protocols.udp.ProtocolHandler import TISProtocolHandler

from homeassistant.components.sensor import SensorEntity, UnitOfTemperature
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import TISConfigEntry
from .coordinator import SensorUpdateCoordinator
from .entities import BaseSensorEntity


# TODO: remove this
class TempEntity:
    def __init__(self, device_id, api, gateway):
        self.device_id = device_id
        self.api = api
        self.gateway = gateway


async def async_setup_entry(
    hass: HomeAssistant, entry: TISConfigEntry, async_add_devices: AddEntitiesCallback
) -> None:
    """Set up the TIS sensors."""
    # Create an instance of your sensor
    tis_api: TISApi = entry.runtime_data.api
    # sensor = TemperatureSensor(hass, tis_api, [0x01, 0x08], "luna", "192.168.1.200")
    tis_sensors = []
    for sensor_type, sensor_handler in RELEVANT_TYPES.items():
        sensors: list[dict] = await tis_api.get_entities(platform=sensor_type)
        if sensors and len(sensors) > 0:
            # exctract the data
            sensor_entities = [
                (
                    appliance_name,
                    next(iter(appliance["channels"][0].values())),
                    appliance["device_id"],
                    appliance["is_protected"],
                    appliance["gateway"],
                    appliance["min"],
                    appliance["max"],
                )
                for sensor in sensors
                for appliance_name, appliance in sensor.items()
            ]
            # create the sensor objects
            sensor_objects = []
            for appliance_name, channel_number, device_id, is_protected, gateway, min, max in sensor_entities:
                if sensor_type == "analog_sensor":
                    sensor_objects.append(
                        sensor_handler(
                            hass=hass,
                            tis_api=tis_api,
                            gateway=gateway,
                            name=appliance_name,
                            device_id=device_id,
                            channel_number=channel_number,
                            min=min,
                            max=max,
                        )
                    )
                else:
                    sensor_objects.append(
                        sensor_handler(
                            hass=hass,
                            tis_api=tis_api,
                            gateway=gateway,
                            name=appliance_name,
                            device_id=device_id,
                            channel_number=channel_number,
                        )
                    )

            # add the sensor objects to the list
            tis_sensors.extend(sensor_objects)

    cpu_temp_sensor = CPUTemperatureSensor(hass)
    tis_sensors.append(cpu_temp_sensor)
    # Add the sensor to Home Assistant
    async_add_devices(tis_sensors)


def get_coordinator(
    hass: HomeAssistant, tis_api: TISApi, device_id: list[int], gateway: str, coordinator_type: str
) -> SensorUpdateCoordinator:
    """Get or create a SensorUpdateCoordinator for the given device_id.

    :param hass: Home Assistant instance.
    :type hass: HomeAssistant
    :param tis_api: The TIS API instance.
    :type tis_api: TISApi
    :param protocol_handler: The protocol handler instance.
    :type protocol_handler: ProtocolHandler
    :param device_id: The device ID as a list of integers.
    :type device_id: List[int]
    :return: The SensorUpdateCoordinator for the given device_id.
    :rtype: SensorUpdateCoordinator
    """
    coordinator_id = f'{tuple(device_id)}_{coordinator_type}'

    if coordinator_id not in coordinators:
        logging.info("creating new coordinator")
        entity = TempEntity(device_id, tis_api, gateway)
        if coordinator_type == "temp_sensor":
            update_packet = protocol_handler.generate_temp_sensor_update_packet(
                entity=entity
            )
        elif coordinator_type == "health_sensor":
            update_packet = protocol_handler.generate_health_sensor_update_packet(
                entity=entity
            )
        elif coordinator_type == "analog_sensor":
            update_packet = protocol_handler.generate_update_analog_packet(
                entity=entity
            )
        coordinators[coordinator_id] = SensorUpdateCoordinator(
            hass,
            tis_api,
            timedelta(seconds=30),
            device_id,
            update_packet,
        )
    return coordinators[coordinator_id]

protocol_handler = TISProtocolHandler()

_LOGGER = logging.getLogger(__name__)
coordinators = {}


class CoordinatedTemperatureSensor(BaseSensorEntity, SensorEntity):
    """Representation of a coordinated TIS sensor.

    :param coordinator: The coordinator object. :type coordinator: SensorUpdateCoordinator
    :param name: The name of the sensor. :type name: str
    :param device_id: The device id of the sensor. :type device_id: str
    """

    def __init__(
        self,
        hass: HomeAssistant,
        tis_api: TISApi,
        gateway: str,
        name: str,
        device_id: list,
        channel_number: int,
        
    ) -> None:
        """Initialize the sensor."""
        coordinator = get_coordinator(hass, tis_api, device_id, gateway, "temp_sensor")
        super().__init__(coordinator, name, device_id)
        self._attr_icon = "mdi:thermometer"
        self.name = name
        self.device_id = device_id
        self.channel_number = channel_number
        self._attr_unique_id = f"sensor_{self.name}"

    async def async_added_to_hass(self) -> None:
        """Register for the CPU temperature event."""
        await super().async_added_to_hass()

        @callback
        def handle_temperature_feedback(event: Event):
            """Handle the LUNA temperature update event."""
            try:
                if event.data["feedback_type"] == "temp_feedback":
                    self._state = event.data["temp"]
                self.async_write_ha_state()
            except Exception as e:
                logging.error(f"event data error for temperature: {event.data}")

        self.hass.bus.async_listen(str(self.device_id), handle_temperature_feedback)

    def _update_state(self, data):
        """Update the state based on the data."""
        # TODO: Implement the update logic

    @property
    def unit_of_measurement(self) -> UnitOfTemperature:
        """Return the unit of measurement."""
        # Return the unit of measurement
        return UnitOfTemperature.CELSIUS


class CoordinatedLUXSensor(BaseSensorEntity, SensorEntity):
    """Representation of a coordinated TIS sensor.

    :param coordinator: The coordinator object. :type coordinator: SensorUpdateCoordinator
    :param name: The name of the sensor. :type name: str
    :param device_id: The device id of the sensor. :type device_id: str
    """

    def __init__(
        self,
        hass: HomeAssistant,
        tis_api: TISApi,
        gateway: str,
        name: str,
        device_id: list,
        channel_number: int,
    ) -> None:
        """Initialize the sensor."""
        coordinator = get_coordinator(hass, tis_api, device_id, gateway, "health_sensor")

        super().__init__(coordinator, name, device_id)
        self._attr_icon = "mdi:brightness-6"
        self.name = name
        self.device_id = device_id
        self.channel_number = channel_number
        self._attr_unique_id = f"sensor_{self.name}"

    async def async_added_to_hass(self) -> None:
        """Register for the LUX temperature event."""
        await super().async_added_to_hass()

        @callback
        def handle_health_feedback(event: Event):
            """Handle the lux update event."""
            try:
                if event.data["feedback_type"] == "health_feedback":
                    self._state = int(event.data["lux"])
                self.async_write_ha_state()
            except Exception as e:
                logging.error(f"event data error for lux: {event.data}")

        self.hass.bus.async_listen(str(self.device_id), handle_health_feedback)

    def _update_state(self, data):
        """Update the state based on the data."""

class CoordinatedAnalogSensor(BaseSensorEntity, SensorEntity):
    """Representation of a coordinated TIS sensor.

    :param coordinator: The coordinator object. :type coordinator: SensorUpdateCoordinator
    :param name: The name of the sensor. :type name: str
    :param device_id: The device id of the sensor. :type device_id: str
    """

    def __init__(
        self,
        hass: HomeAssistant,
        tis_api: TISApi,
        gateway: str,
        name: str,
        device_id: list,
        channel_number: int,
        min: int = 0,
        max: int = 100,
    ) -> None:
        """Initialize the sensor."""
        coordinator = get_coordinator(hass, tis_api, device_id, gateway, "analog_sensor")

        super().__init__(coordinator, name, device_id)
        self._attr_icon = "mdi:current-ac"
        self.name = name
        self.device_id = device_id
        self.channel_number = channel_number
        self.min = min
        self.max = max
        self._attr_unique_id = f"sensor_{self.name}"

    async def async_added_to_hass(self) -> None:
        """Register for the analog event."""
        await super().async_added_to_hass()

        @callback
        def handle_analog_feedback(event: Event):
            """Handle the lux update event."""
            try:
                if event.data["feedback_type"] == "analog_feedback":
                    #Map the analog to be within min and max
                    value = int(event.data["analog"][self.channel_number - 1])
                    normalized = (value - self.min) / (self.max - self.min) # Normalize to 0–1
                    normalized = max(0, min(1, normalized)) # Clamp between 0 and 1
                    self._state = int(normalized * 100) # Scale to 0–100
                    
                self.async_write_ha_state()
            except Exception as e:
                logging.error(f"event data error for analog sensor: {event.data}")

             
            normalized = (value - self.min) / (self.max - self.min) # Normalize to 0–1
            normalized = max(0, min(1, normalized)) # Clamp between 0 and 1
            return int(normalized * 100) # Scale to 0–100
            
        self.hass.bus.async_listen(str(self.device_id), handle_analog_feedback)

    def _update_state(self, data):
        """Update the state based on the data."""

    

class CPUTemperatureSensor(SensorEntity):
    def __init__(self, hass: HomeAssistant) -> None:
        self._cpu = CPUTemperature()
        self._state = self._cpu.temperature
        self._hass = hass
        self._attr_name = "CPU Temperature Sensor"
        self._attr_icon = "mdi:thermometer"
        self._attr_update_interval = timedelta(seconds=10)
        self._attr_unique_id = f"sensor_{self.name}"

        # Schedule update every 10 seconds
        async_track_time_interval(
            self._hass, self.async_update, self._attr_update_interval
        )

    async def async_update(self, event_time) -> None:
        """Update the sensor state."""
        self._state = self._cpu.temperature
        self.hass.bus.async_fire("cpu_temperature", {"temperature": int(self._state)})
        self.async_write_ha_state()

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def state(self) -> float | None:
        """Return the current  temperature."""
        # Return the current CPU temperature
        return self._state

    @property
    def unit_of_measurement(self) -> UnitOfTemperature:
        """Return the unit of measurement."""
        # Return the unit of measurement
        return UnitOfTemperature.CELSIUS

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._attr_name

RELEVANT_TYPES: dict[str, type[CoordinatedLUXSensor]] = {
    "lux_sensor": CoordinatedLUXSensor,
    "temperature_sensor": CoordinatedTemperatureSensor,
    "analog_sensor": CoordinatedAnalogSensor,
}
