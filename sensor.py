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

from . import TISConfigEntry
from .coordinator import SensorUpdateCoordinator
from .entities import BaseSensorEntity
from .const import ENERGY_SENSOR_TYPES
from datetime import datetime


class TISSensorEntity:
    def __init__(self, device_id, api, gateway, channel_number):
        self.device_id = device_id
        self.api = api
        self.gateway = gateway
        self.channel_number = channel_number


async def async_setup_entry(
    hass: HomeAssistant, entry: TISConfigEntry, async_add_devices: AddEntitiesCallback
) -> None:
    """Set up the TIS sensors."""
    # Create an instance of your sensor
    tis_api: TISApi = entry.runtime_data.api
    await tis_api.get_bill_configs()
    tis_sensors = []
    for sensor_type, handler in RELEVANT_TYPES.items():
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
            for (
                appliance_name,
                channel_number,
                device_id,
                is_protected,
                gateway,
                min,
                max,
            ) in sensor_entities:
                if sensor_type == "analog_sensor":
                    sensor_objects.append(
                        handler(
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
                elif sensor_type == "energy_sensor":
                    for key, val in ENERGY_SENSOR_TYPES.items():
                        sensor_objects.append(
                            handler(
                                hass=hass,
                                tis_api=tis_api,
                                gateway=gateway,
                                name=f"{val} {appliance_name}",
                                device_id=device_id,
                                channel_number=channel_number,
                                key=key,
                                sensor_type="energy_sensor",
                            )
                        )

                    sensor_objects.append(
                        handler(
                            hass=hass,
                            tis_api=tis_api,
                            gateway=gateway,
                            name=f"Monthly Energy {appliance_name}",
                            device_id=device_id,
                            channel_number=channel_number,
                            sensor_type="monthly_energy_sensor",
                        )
                    )

                    sensor_objects.append(
                        handler(
                            hass=hass,
                            tis_api=tis_api,
                            gateway=gateway,
                            name=f"Bill {appliance_name}",
                            device_id=device_id,
                            channel_number=channel_number,
                            sensor_type="bill_energy_sensor",
                        )
                    )

                else:
                    sensor_objects.append(
                        handler(
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
    hass: HomeAssistant,
    tis_api: TISApi,
    device_id: list[int],
    gateway: str,
    coordinator_type: str,
    channel_number: int,
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
    coordinator_id = (
        f"{tuple(device_id)}_{coordinator_type}"
        if "energy_sensor" not in coordinator_type
        else f"{tuple(device_id)}_{coordinator_type}_{channel_number}"
    )

    if coordinator_id not in coordinators:
        entity = TISSensorEntity(device_id, tis_api, gateway, channel_number)
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
        elif coordinator_type == "energy_sensor":
            update_packet = protocol_handler.generate_update_energy_packet(
                entity=entity
            )
        elif coordinator_type == "monthly_energy_sensor":
            update_packet = protocol_handler.generate_update_monthly_energy_packet(
                entity=entity
            )
        elif coordinator_type == "bill_energy_sensor":
            update_packet = protocol_handler.generate_update_monthly_energy_packet(
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
        coordinator = get_coordinator(
            hass, tis_api, device_id, gateway, "temp_sensor", channel_number
        )
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
        coordinator = get_coordinator(
            hass, tis_api, device_id, gateway, "health_sensor", channel_number
        )

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
        coordinator = get_coordinator(
            hass, tis_api, device_id, gateway, "analog_sensor", channel_number
        )

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
            """Handle the analog update event."""
            try:
                if event.data["feedback_type"] == "analog_feedback":
                    # Map the analog to be within min and max
                    value = int(event.data["analog"][self.channel_number - 1])
                    normalized = (value - self.min) / (
                        self.max - self.min
                    )  # Normalize to 0–1
                    normalized = max(0, min(1, normalized))  # Clamp between 0 and 1
                    self._state = int(normalized * 100)  # Scale to 0–100

                self.async_write_ha_state()
            except Exception as e:
                logging.error(
                    f"event data error for analog sensor: {event.data} \n error: {e}"
                )

            normalized = (value - self.min) / (self.max - self.min)  # Normalize to 0–1
            normalized = max(0, min(1, normalized))  # Clamp between 0 and 1
            return int(normalized * 100)  # Scale to 0–100

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


class CoordinatedEnergySensor(BaseSensorEntity, SensorEntity):
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
        key: str = None,
        sensor_type: str = None,
    ) -> None:
        """Initialize the sensor."""
        coordinator = get_coordinator(
            hass, tis_api, device_id, gateway, sensor_type, channel_number
        )

        super().__init__(coordinator, name, device_id)
        self._attr_icon = "mdi:current-ac"
        self.api = tis_api
        self.name = name
        self.device_id = device_id
        self.channel_number = channel_number
        self._attr_unique_id = f"energy_{self.name}"
        self._key = key
        self.sensor_type = sensor_type
        self._attr_state_class = "measurement"

    async def async_added_to_hass(self) -> None:
        """Register for the energy event."""
        await super().async_added_to_hass()

        @callback
        def handle_energy_feedback(event: Event):
            """Handle the energy update event."""
            try:
                if (
                    event.data["feedback_type"] == "energy_feedback"
                    and self.sensor_type == "energy_sensor"
                ):
                    if event.data["channel_num"] == self.channel_number:
                        self._state = float(event.data["energy"].get(self._key, None))
                elif (
                    event.data["feedback_type"] == "monthly_energy_feedback"
                    and self.sensor_type == "monthly_energy_sensor"
                ):
                    if event.data["channel_num"] == self.channel_number:
                        self._state = event.data["energy"]
                elif (
                    event.data["feedback_type"] == "monthly_energy_feedback"
                    and self.sensor_type == "bill_energy_sensor"
                ):
                    if event.data["channel_num"] == self.channel_number:
                        month = datetime.now().month
                        is_summer = month in [6, 7, 8, 9]

                        rates = (
                            self.api.bill_configs.get("summer_rates", {})
                            if is_summer
                            else self.api.bill_configs.get("winter_rates", {})
                        )

                        power_consumption = event.data["energy"] + 100

                        tier = None
                        for index, rate in enumerate(rates):
                            if power_consumption < rate["min_kw"]:
                                tier = rates[index - 1]["price_per_kw"]
                                break
                        if tier is None and len(rates) > 0:
                            tier = rates[-1]["price_per_kw"]

                        self._state = int(tier * power_consumption)

                self.async_write_ha_state()
            except Exception as e:
                logging.error(
                    f"error in self.name: {self.name}, self._key: {self._key}, self.sensor_type: {self.sensor_type}"
                )
                logging.error(
                    f"event data error for energy sensor: {event.data} \n error: {e}"
                )

        self.hass.bus.async_listen(str(self.device_id), handle_energy_feedback)

    def _update_state(self, data):
        """Update the state based on the data."""

    @property
    def native_value(self):
        return self.state


RELEVANT_TYPES: dict[str, type[CoordinatedLUXSensor]] = {
    "lux_sensor": CoordinatedLUXSensor,
    "temperature_sensor": CoordinatedTemperatureSensor,
    "analog_sensor": CoordinatedAnalogSensor,
    "energy_sensor": CoordinatedEnergySensor,
}
