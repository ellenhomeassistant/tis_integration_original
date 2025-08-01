"""Light platform for TIS Control."""

import logging
from math import ceil
from typing import Any

from TISControlProtocol.api import TISApi
from TISControlProtocol.BytesHelper import int_to_8_bit_binary
from TISControlProtocol.Protocols.udp.ProtocolHandler import (
    TISPacket,
    TISProtocolHandler,
)

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TISConfigEntry

handler = TISProtocolHandler()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TISConfigEntry,
    async_add_devices: AddEntitiesCallback,
) -> None:
    """Set up TIS Control lights."""
    tis_api: TISApi = entry.runtime_data.api
    lights: dict = await tis_api.get_entities(platform="dimmer")
    if lights:
        light_entities = [
            (
                light_name,
                next(iter(light["channels"][0].values())),
                light["device_id"],
                light["is_protected"],
                light["gateway"],
            )
            for light in lights
            for light_name, light in light.items()
        ]
        tis_lights = [
            TISLight(
                tis_api=tis_api,
                light_name=light_name,
                device_id=device_id,
                channel_number=channel_number,
                gateway=gateway,
            )
            for light_name, channel_number, device_id, is_protected, gateway in light_entities
        ]
        async_add_devices(tis_lights)

    rgb_lights: dict = await tis_api.get_entities(platform="rgb")
    if rgb_lights:
        rgb_light_entities = [
            (
                light_name,
                next(iter(light["channels"][0].values())),
                next(iter(light["channels"][1].values())),
                next(iter(light["channels"][2].values())),
                light["device_id"],
                light["is_protected"],
                light["gateway"],
            )
            for light in rgb_lights
            for light_name, light in light.items()
        ]
        tis_rgb_lights = [
            TISRGBLight(
                tis_api=tis_api,
                light_name=light_name,
                r_channel=r_channel,
                g_channel=g_channel,
                b_channel=b_channel,
                device_id=device_id,
                gateway=gateway,
            )
            for light_name, r_channel, g_channel, b_channel, device_id, is_protected, gateway in rgb_light_entities
        ]
        async_add_devices(tis_rgb_lights)

    rgbw_lights: dict = await tis_api.get_entities(platform="rgbw")
    if rgbw_lights:
        rgbw_light_entities = [
            (
                light_name,
                next(iter(light["channels"][0].values())),
                next(iter(light["channels"][1].values())),
                next(iter(light["channels"][2].values())),
                next(iter(light["channels"][3].values())),
                light["device_id"],
                light["is_protected"],
                light["gateway"],
            )
            for light in rgbw_lights
            for light_name, light in light.items()
        ]
        tis_rgbw_lights = [
            TISRGBWLight(
                tis_api=tis_api,
                light_name=light_name,
                r_channel=r_channel,
                g_channel=g_channel,
                b_channel=b_channel,
                w_channel=w_channel,
                device_id=device_id,
                gateway=gateway,
            )
            for light_name, r_channel, g_channel, b_channel, w_channel, device_id, is_protected, gateway in rgbw_light_entities
        ]
        async_add_devices(tis_rgbw_lights)


class TISLight(LightEntity):
    """Representation of a single channel TIS light."""

    def __init__(
        self,
        tis_api: TISApi,
        gateway: str,
        light_name,
        channel_number,
        device_id: list[int],
    ) -> None:
        """Initialize the light."""
        self.api = tis_api
        self.gateway = gateway
        self.device_id = device_id
        self.channel_number = int(channel_number)
        self._attr_name = light_name
        self._attr_state = False
        self._attr_brightness = None
        self.listener = None
        self.broadcast_channel = 255
        self._attr_unique_id = f"{self.name}_{self.channel_number}"

        self.setup_light()

    def setup_light(self):
        """TODO: remove this function and only use constructor."""
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        self._attr_color_mode = ColorMode.BRIGHTNESS
        self._attr_supported_features = LightEntityFeature.TRANSITION
        self.generate_light_packet = handler.generate_light_control_packet
        self.update_packet: TISPacket = handler.generate_control_update_packet(self)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""

        @callback
        async def handle_event(event: Event):
            """Handle the event."""
            # check if event is for this switch
            if event.event_type == str(self.device_id):
                if event.data["feedback_type"] == "control_response":
                    logging.info(f"channel number for light: {self.channel_number}")
                    channel_value = event.data["additional_bytes"][2]
                    channel_number = event.data["channel_number"]
                    if int(channel_number) == self.channel_number:
                        self._attr_state = int(channel_value) != 0
                        self._attr_brightness = int((channel_value / 100) * 255)
                    self.async_write_ha_state()

                elif self.channel_number != self.broadcast_channel:
                    if event.data["feedback_type"] == "binary_feedback":
                        n_bytes = ceil(event.data["additional_bytes"][0] / 8)
                        channels_status = "".join(
                            int_to_8_bit_binary(event.data["additional_bytes"][i])
                            for i in range(1, n_bytes + 1)
                        )
                        if channels_status[self.channel_number - 1] == "0":
                            self._attr_state = False
                        self.async_write_ha_state()
                    elif event.data["feedback_type"] == "update_response":
                        additional_bytes = event.data["additional_bytes"]
                        self._attr_brightness = int(
                            additional_bytes[self.channel_number] / 100 * 255
                        )
                        self._attr_state = (
                            STATE_ON if self._attr_brightness > 0 else STATE_OFF
                        )
                elif event.data["feedback_type"] == "offline_device":
                    self._attr_state = STATE_UNKNOWN

        self.listener = self.hass.bus.async_listen(str(self.device_id), handle_event)
        _ = await self.api.protocol.sender.send_packet(self.update_packet)

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        return self._attr_brightness

    @property
    def color_mode(self) -> ColorMode | str | None:
        """Return the color mode of the light."""
        return self._attr_color_mode

    @property
    def supported_color_modes(self) -> set[str] | None:
        """Flag supported color modes."""
        return self._attr_supported_color_modes

    @property
    def supported_features(self) -> LightEntityFeature:
        """Flag supported features."""
        return self._attr_supported_features

    @property
    def is_on(self) -> bool | None:
        """Return the state of the light."""
        return self._attr_brightness > 0 if self._attr_brightness is not None else None

    @property
    def name(self) -> str | None:
        """Return the name of the light."""
        return self._attr_name

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        try:
            brightness_level = kwargs[ATTR_BRIGHTNESS]
        except KeyError:
            brightness_level = 255
        packet = self.generate_light_packet(self, int((brightness_level / 255) * 100))
        ack_status = await self.api.protocol.sender.send_packet_with_ack(packet)
        if ack_status:
            self._attr_state = True
            self._attr_brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        else:
            # set light to unknown
            self._attr_state = None
            self._attr_brightness = None
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        packet = self.generate_light_packet(self, 0)
        ack_status = await self.api.protocol.sender.send_packet_with_ack(packet)
        if ack_status:
            self._attr_brightness = 0
            self._attr_state = False
        else:
            # set light to unknown
            self._attr_state = None
            self._attr_brightness = None
        self.async_write_ha_state()


class TISRGBLight(LightEntity):
    """Representation of a TIS RGB light."""

    def __init__(
        self,
        tis_api: TISApi,
        gateway: str,
        device_id: list[int],
        r_channel: str | int,
        g_channel: str | int,
        b_channel: str | int,
        light_name: str,
    ) -> None:
        """.Initialize the light."""
        self.api = tis_api
        self.gateway = gateway
        self.device_id = device_id
        self.r_channel = int(r_channel)
        self.g_channel = int(g_channel)
        self.b_channel = int(b_channel)
        self.rgb_value_flags = [0, 0, 0]
        # hass attrs
        self._attr_name = light_name
        self._attr_state = None
        self._attr_rgb_color = None
        self._attr_brightness = None
        self.listener = None
        self._attr_unique_id = (
            f"{self.name}_{self.r_channel}_{self.g_channel}_{self.b_channel}"
        )
        self.default_color = (0, 0, 0)

        self.setup_light()

    def setup_light(self):
        """."""
        self._attr_supported_color_modes = {ColorMode.RGB}
        self._attr_color_mode = ColorMode.RGB
        self.generate_rgb_packets = handler.generate_rgb_light_control_packet
        self.update_packet = handler.generate_control_update_packet(self)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""

        @callback
        async def handle_event(event: Event):
            """Handle the event."""
            if event.event_type == str(self.device_id):
                if event.data["feedback_type"] == "update_response":
                    additional_bytes = event.data["additional_bytes"]
                    channel_number = event.data["channel_number"]

                    if self._attr_rgb_color is None:
                        self._attr_rgb_color = [0, 0, 0]
                    if channel_number == self.r_channel:
                        self._attr_rgb_color[0] = int(
                            (additional_bytes[channel_number] / 100) * 255
                        )
                    elif channel_number == self.g_channel:
                        self._attr_rgb_color[1] = int(
                            (additional_bytes[channel_number] / 100) * 255
                        )
                    elif channel_number == self.b_channel:
                        self._attr_rgb_color[2] = int(
                            (additional_bytes[channel_number] / 100) * 255
                        )
                    self._attr_state = bool(
                        self.r_channel or self.g_channel or self.b_channel
                    )
                elif event.data["feedback_type"] == "offline_device":
                    self._attr_state = STATE_UNKNOWN

        self.listener = self.hass.bus.async_listen(str(self.device_id), handle_event)
        # send update 5 times or until receiving a state
        for _i in range(5):
            if self._attr_rgb_color is None:
                _ = await self.api.protocol.sender.send_packet(self.update_packet)

        if self._attr_rgb_color is None:
            self._attr_state = STATE_UNKNOWN
            self._attr_rgb_color = (0, 0, 0)

    @property
    def color_mode(self) -> ColorMode | str | None:
        """Return the color mode of the light."""
        return self._attr_color_mode

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        return self._attr_brightness

    # Unique property for RGB light
    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the RGB color value."""
        return self._attr_rgb_color

    @property
    def supported_color_modes(self) -> set[str] | None:
        """Flag supported color modes."""
        return self._attr_supported_color_modes

    @property
    def is_on(self) -> bool:
        """Return the state of the light."""
        return self._attr_state

    @property
    def name(self) -> str | None:
        """Return the name of the light."""
        return self._attr_name

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        try:
            color = kwargs.get(ATTR_RGB_COLOR, None)
            brightness = kwargs.get(ATTR_BRIGHTNESS, None)
            logging.info(f"color: {color}")
            logging.info(f"brightness: {brightness}")

            if color is not None:
                # map color from 255 to 100
                color = tuple([int((c / 255) * 100) for c in color])
                r_packet, g_packet, b_packet = self.generate_rgb_packets(self, color)
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    r_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.r_channel}",
                    )
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    g_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.g_channel}",
                    )
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    b_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.b_channel}",
                    )
                self._attr_state = True
                # map color from 100 to 255
                color = tuple([int((c / 100) * 255) for c in color])
                self._attr_rgb_color = color
                self.default_color = color
                logging.info(f"new default color: {color}")
            elif brightness is not None:
                brightness = max(1, min(255, brightness))
                brightness /= 255

                color = self.default_color or (0, 0, 0)
                logging.info(f"default color: {color}")
                color = tuple([int(brightness * c * 100 / 255) for c in color])

                r_packet, g_packet, b_packet = self.generate_rgb_packets(self, color)
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    r_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.r_channel}",
                    )
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    g_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.g_channel}",
                    )
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    b_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.b_channel}",
                    )
                logging.info(f"brightened color: {color}")
            else:
                logging.info(
                    "Neither color nor brightness provided, using default color."
                )
                color = self.default_color or (0, 0, 0)
                self._attr_state = (
                    True
                    if self.default_color and self.default_color != (0, 0, 0)
                    else False
                )
                self._attr_rgb_color = color
                color = tuple([int(c * 100 / 255) for c in color])
                r_packet, g_packet, b_packet = self.generate_rgb_packets(self, color)
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    r_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.r_channel}",
                    )
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    g_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.g_channel}",
                    )
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    b_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.b_channel}",
                    )

        except KeyError as e:
            logging.error(f"error turning on light: {e}")
        self.async_write_ha_state()
        # self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        logging.info("turning off")
        logging.info(f"kwargs: {kwargs}")
        r_packet, g_packet, b_packet = self.generate_rgb_packets(self, (0, 0, 0))
        _ = await self.api.protocol.sender.send_packet_with_ack(g_packet)
        _ = await self.api.protocol.sender.send_packet_with_ack(r_packet)
        _ = await self.api.protocol.sender.send_packet_with_ack(b_packet)
        self._attr_state = False
        self._attr_rgb_color = (0, 0, 0)
        self.async_write_ha_state()


class TISRGBWLight(LightEntity):
    """Representation of a TIS RGBW light."""

    def __init__(
        self,
        tis_api: TISApi,
        gateway: str,
        device_id: list[int],
        r_channel: str | int,
        g_channel: str | int,
        b_channel: str | int,
        w_channel: str | int,
        light_name: str,
    ) -> None:
        """.Initialize the light."""
        self.api = tis_api
        self.gateway = gateway
        self.device_id = device_id
        self.r_channel = int(r_channel)
        self.g_channel = int(g_channel)
        self.b_channel = int(b_channel)
        self.w_channel = int(w_channel)
        # hass attrs
        self._attr_name = light_name
        self._attr_state = None
        self._attr_brightness = None
        self._attr_rgbw_color = None
        self.rgbw_value_flags = [0, 0, 0, 0]
        self.listener = None
        self._attr_unique_id = f"{self.name}_{self.r_channel}_{self.g_channel}_{self.b_channel}_{self.w_channel}"
        self.default_color = (0, 0, 0, 0)
        self.setup_light()

    def setup_light(self):
        """."""
        self._attr_supported_color_modes = {ColorMode.RGBW}
        self._attr_color_mode = ColorMode.RGBW
        self._attr_supported_features = LightEntityFeature.TRANSITION
        self.generate_rgbw_packets = handler.generate_rgbw_light_control_packet
        self.update_packet = handler.generate_control_update_packet(self)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""

        @callback
        async def handle_event(event: Event):
            """Handle the event."""
            # check if event is for this switch
            if event.event_type == str(self.device_id):
                if event.data["feedback_type"] == "update_response":
                    logging.info(f"RGBW event data: {event.data}")
                    additional_bytes = event.data["additional_bytes"]

                    r_value = (additional_bytes[self.r_channel] / 100) * 255
                    g_value = (additional_bytes[self.g_channel] / 100) * 255
                    b_value = (additional_bytes[self.b_channel] / 100) * 255
                    w_value = (additional_bytes[self.w_channel] / 100) * 255

                    self._attr_rgbw_color = (r_value, g_value, b_value, w_value)
                    self._attr_state = bool(r_value or g_value or b_value or w_value)
                elif event.data["feedback_type"] == "offline_device":
                    self._attr_state = STATE_UNKNOWN

        self.listener = self.hass.bus.async_listen(str(self.device_id), handle_event)
        # send update 5 times or until receiving a state
        for _i in range(5):
            if self._attr_rgbw_color is None:
                _ = await self.api.protocol.sender.send_packet(self.update_packet)

        if self._attr_rgbw_color is None:
            self._attr_state = STATE_UNKNOWN
            self._attr_rgbw_color = (0, 0, 0, 0)

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        return self._attr_brightness

    @property
    def color_mode(self) -> ColorMode | str | None:
        """Return the color mode of the light."""
        return self._attr_color_mode

    # Unique property for RGBW light
    @property
    def rgbw_color(self) -> tuple[int, int, int, int] | None:
        """Return the RGBW color value."""
        return self._attr_rgbw_color

    @property
    def supported_color_modes(self) -> set[str] | None:
        """Flag supported color modes."""
        return self._attr_supported_color_modes

    @property
    def supported_features(self) -> LightEntityFeature:
        """Flag supported features."""
        return self._attr_supported_features

    @property
    def is_on(self) -> bool:
        """Return the state of the light."""
        return self._attr_state

    @property
    def name(self) -> str | None:
        """Return the name of the light."""
        return self._attr_name

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        try:
            color = kwargs.get(ATTR_RGBW_COLOR, None)
            brightness = kwargs.get(ATTR_BRIGHTNESS, None)
            logging.warning(f"kwargs: {kwargs}")
            if color is not None:
                # map color from 255 to 100
                color = tuple([int((c / 255) * 100) for c in color])
                r_packet, g_packet, b_packet, w_packet = self.generate_rgbw_packets(
                    self, color
                )
                logging.info(f"color (percent): {color}")
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    r_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.r_channel}",
                    )
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    g_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.g_channel}",
                    )
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    b_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.b_channel}",
                    )
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    w_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.w_channel}",
                    )

                self._attr_state = True
                # map color from 100 to 255
                color = tuple([int((c / 100) * 255) for c in color])
                self._attr_rgbw_color = color
                self.default_color = color
            elif brightness is not None:
                brightness = max(1, min(255, brightness))
                logging.warning(
                    f"brightness: {brightness}, self._attr_brightness: {self._attr_brightness}"
                )
                self._attr_brightness = brightness
                brightness /= 255

                color = self.default_color or (0, 0, 0, 0)
                logging.info(f"default color: {color}")
                color = tuple([int(brightness * c * 100 / 255) for c in color])

                r_packet, g_packet, b_packet, w_packet = self.generate_rgbw_packets(
                    self, color
                )
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    r_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.r_channel}",
                    )
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    g_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.g_channel}",
                    )
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    b_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.b_channel}",
                    )
                ack_status = await self.api.protocol.sender.send_packet_with_ack(
                    w_packet
                )
                if not ack_status:
                    logging.error(
                        f"error turning on light: {ack_status}, channel: {self.w_channel}",
                    )
                self._attr_state = True
                # map color from 100 to 255
                color = tuple([int((c / 100) * 255) for c in color])
                self._attr_rgbw_color = color

        except KeyError as e:
            logging.error(f"error turning on light: {e}")
        self.async_write_ha_state()
        # self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        r_packet, g_packet, b_packet, w_packet = self.generate_rgbw_packets(
            self, (0, 0, 0, 0)
        )
        _ = await self.api.protocol.sender.send_packet_with_ack(r_packet)
        _ = await self.api.protocol.sender.send_packet_with_ack(g_packet)
        _ = await self.api.protocol.sender.send_packet_with_ack(b_packet)
        _ = await self.api.protocol.sender.send_packet_with_ack(w_packet)
        self._attr_state = False
        self._attr_rgbw_color = (0, 0, 0, 0)
        self.async_write_ha_state()
