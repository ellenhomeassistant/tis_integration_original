"""Cover platform fot TIS Control."""

import logging
from math import ceil
from typing import Any
import json

from TISControlProtocol.api import TISApi
from TISControlProtocol.BytesHelper import int_to_8_bit_binary
from TISControlProtocol.Protocols.udp.ProtocolHandler import (
    TISPacket,
    TISProtocolHandler,
)

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.const import STATE_CLOSING, STATE_OPENING, STATE_UNKNOWN, Platform
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
    # Fetch all covers from the TIS API
    covers_w_pos: dict = await tis_api.get_entities(platform="motor")
    covers: dict = await tis_api.get_entities(platform="shutter")

    if covers_w_pos:
        # Prepare a list of tuples containing necessary cover details
        cover_entities = [
            (
                cover_name,
                next(iter(cover["channels"][0].values())),
                cover["device_id"],
                cover["gateway"],
                cover["settings"],
            )
            for cover in covers_w_pos
            for cover_name, cover in cover.items()
        ]
        # Create TISCover objects and add them to Home Assistant
        tis_covers = [
            TISCoverWPos(
                tis_api=tis_api,
                cover_name=cover_name,
                channel_number=channel_number,
                device_id=device_id,
                gateway=gateway,
                settings=settings,
            )
            for cover_name, channel_number, device_id, gateway, settings in cover_entities
        ]
        async_add_devices(tis_covers, update_before_add=True)

    if covers:
        # Prepare a list of tuples containing necessary cover details
        cover_entities = [
            (
                cover_name,
                next(iter(cover["channels"][0].values())),
                next(iter(cover["channels"][1].values())),
                cover["device_id"],
                cover["gateway"],
            )
            for cover in covers
            for cover_name, cover in cover.items()
        ]
        # Create TISCover objects and add them to Home Assistant
        tis_covers = [
            TISCoverNoPos(
                tis_api=tis_api,
                cover_name=cover_name,
                up_channel_number=up_channel_number,
                down_channel_number=down_channel_number,
                device_id=device_id,
                gateway=gateway,
            )
            for cover_name, up_channel_number, down_channel_number, device_id, gateway in cover_entities
        ]
        async_add_devices(tis_covers, update_before_add=True)


class TISCoverWPos(CoverEntity):
    """Representation of a TIS cover with position feedback."""

    def __init__(
        self,
        tis_api: TISApi,
        gateway: str,
        cover_name: str,
        channel_number: int,
        device_id: list[int],
        settings,
    ) -> None:
        """Initialize the cover."""
        if settings:
            settings = json.loads(settings)
            self.exchange_command = settings["exchange_command"]
        else:
            self.exchange_command = "0"
        self.api = tis_api
        self.gateway = gateway
        self.device_id = device_id
        self.channel_number = int(channel_number)
        self._attr_name = cover_name
        self._attr_is_closed = None
        self._attr_current_cover_position = None
        self._attr_device_class = CoverDeviceClass.SHUTTER
        self._attr_unique_id = f"{self._attr_name}_{self.channel_number}"
        self.listener = None
        ##############################################
        self.update_packet: TISPacket = handler.generate_control_update_packet(self)
        self.generate_cover_packet = handler.generate_light_control_packet

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""

        @callback
        async def handle_event(event: Event):
            """Handle the event."""
            # check if event is for this switch
            if event.event_type == str(self.device_id):
                if event.data["feedback_type"] == "control_response":
                    logging.info(f"channel number for cover: {self.channel_number}")
                    channel_value = event.data["additional_bytes"][2]
                    channel_number = event.data["channel_number"]
                    if int(channel_number) == self.channel_number:
                        # Convert the received position if needed
                        position = channel_value
                        if self.exchange_command == "1":
                            position = 100 - position
                        self._attr_is_closed = position == 0
                        self._attr_current_cover_position = position
                    self.async_write_ha_state()
                elif event.data["feedback_type"] == "update_response":
                    additional_bytes = event.data["additional_bytes"]
                    position = additional_bytes[self.channel_number]
                    if self.exchange_command == "1":
                        position = 100 - position
                    self._attr_current_cover_position = position
                    self._attr_is_closed = self._attr_current_cover_position == 0
                    self._attr_state = (
                        STATE_CLOSING if self._attr_is_closed else STATE_OPENING
                    )
                elif event.data["feedback_type"] == "offline_device":
                    self._attr_state = STATE_UNKNOWN
                    self._attr_is_closed = None
                    self._attr_current_cover_position = None

            await self.async_update_ha_state(True)

        self.listener = self.hass.bus.async_listen(str(self.device_id), handle_event)
        _ = await self.api.protocol.sender.send_packet(self.update_packet)

    def _convert_position(self, position: int) -> int:
        """Convert position based on exchange_command flag."""
        if self.exchange_command == "1":
            return 100 - position
        return position

    @property
    def name(self) -> str:
        """Return the name of the cover."""
        return self._attr_name

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        return self._attr_is_closed

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Flag supported features."""
        return CoverEntityFeature.SET_POSITION

    @property
    def current_cover_position(self) -> int | None:
        """Return the current position of the cover."""
        return self._attr_current_cover_position

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._attr_unique_id

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        # For open, we want position 100, but if exchanged, we send 0
        send_position = self._convert_position(100)
        packet = self.generate_cover_packet(self, send_position)
        ack_status = await self.api.protocol.sender.send_packet_with_ack(packet)
        if ack_status:
            self._attr_is_closed = False
            self._attr_current_cover_position = 100
        else:
            self._attr_is_closed = None
            self._attr_current_cover_position = None
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        # For close, we want position 0, but if exchanged, we send 100
        send_position = self._convert_position(0)
        packet = self.generate_cover_packet(self, send_position)
        ack_status = await self.api.protocol.sender.send_packet_with_ack(packet)
        if ack_status:
            self._attr_is_closed = True
            self._attr_current_cover_position = 0
        else:
            self._attr_is_closed = None
            self._attr_current_cover_position = None
        self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        position = kwargs[ATTR_POSITION]
        # Convert the position before sending to the device
        send_position = self._convert_position(position)
        packet = self.generate_cover_packet(self, send_position)
        ack_status = await self.api.protocol.sender.send_packet_with_ack(packet)
        if ack_status:
            self._attr_is_closed = (
                send_position <= 20
                if self.exchange_command == "0"
                else send_position >= 80
            )
            self._attr_current_cover_position = position
        else:
            self._attr_is_closed = None
            self._attr_current_cover_position = None
        self.async_write_ha_state()


class TISCoverNoPos(CoverEntity):
    """Representation of a TIS cover without position feedback."""

    def __init__(
        self,
        tis_api: TISApi,
        gateway: str,
        cover_name: str,
        up_channel_number: int,
        down_channel_number: int,
        device_id: list[int],
    ) -> None:
        """Initialize the cover."""
        self.api = tis_api
        self.gateway = gateway
        self.device_id = device_id
        self.up_channel_number = int(up_channel_number)
        self.down_channel_number = int(down_channel_number)
        self._attr_name = cover_name
        self._attr_unique_id = (
            f"{self._attr_name}_{self.up_channel_number}_{self.down_channel_number}"
        )
        # for feedback
        self.channel_number = self.up_channel_number
        self._attr_is_closed = None
        self._attr_device_class = CoverDeviceClass.WINDOW
        self.last_state = STATE_OPENING
        self.listener = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to events."""

        @callback
        async def handle_event(event: Event):
            """Handle the event."""
            # check if event is for this switch
            if event.event_type == str(self.device_id):
                if event.data["feedback_type"] == "control_response":
                    channel_value = event.data["additional_bytes"][2]
                    channel_number = event.data["channel_number"]
                    if int(channel_number) == self.up_channel_number:
                        if channel_value != 0:
                            self._attr_is_closed = False
                            self.last_state = STATE_OPENING
                            self._attr_state = STATE_OPENING
                            logging.info(f"up channel value: {channel_value} 'opening'")
                    elif int(channel_number) == self.down_channel_number:
                        if channel_value != 0:
                            self._attr_is_closed = True
                            self._attr_state = STATE_CLOSING
                            self.last_state = STATE_CLOSING
                            logging.info(
                                f"down channel value: {channel_value} 'closing'"
                            )
                    else:
                        logging.info(f"channel number: {channel_number} 'stopping'")
                        self._attr_state = self.last_state
                        self._attr_is_closed = (
                            False if self.last_state == STATE_OPENING else True
                        )
            await self.async_update_ha_state(True)
            self.schedule_update_ha_state()

        self.listener = self.hass.bus.async_listen(str(self.device_id), handle_event)

    @property
    def name(self) -> str:
        """Return the name of the cover."""
        return self._attr_name

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        # return self._attr_is_closed
        if self._attr_is_closed == True:
            return True
        elif self._attr_is_closed == False:
            return False
        else:
            return None

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Flag supported features."""
        return (
            CoverEntityFeature.OPEN | CoverEntityFeature.STOP | CoverEntityFeature.CLOSE
        )

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._attr_unique_id

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        up_packet, down_packet = handler.generate_no_pos_cover_packet(self, "open")
        # we only need to send the up packet here
        ack_status = await self.api.protocol.sender.send_packet_with_ack(up_packet)
        if ack_status:
            logging.info("up packet sent 'opening'")
            self._attr_is_closed = False
            self._attr_state = STATE_OPENING
            self.last_state = STATE_OPENING
        else:
            logging.info("up packet not sent 'None'")
            self._attr_is_closed = None
            self._attr_state = None
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        up_packet, down_packet = handler.generate_no_pos_cover_packet(self, "close")
        # we only need to send the down packet here
        ack_status = await self.api.protocol.sender.send_packet_with_ack(down_packet)
        if ack_status:
            logging.info("down packet sent 'closing'")
            self._attr_is_closed = True
            self._attr_state = STATE_CLOSING
            self.last_state = STATE_CLOSING
        else:
            logging.info("down packet not sent 'None'")
            self._attr_is_closed = None
            self._attr_state = None
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        up_packet, down_packet = handler.generate_no_pos_cover_packet(self, "stop")
        # we need to send both packets here
        if self._attr_is_closed:
            ack_status = await self.api.protocol.sender.send_packet_with_ack(
                down_packet
            )
            if ack_status:
                logging.info("down packet sent 'stopping'")
                self._attr_state = self.last_state
                self._attr_is_closed = (
                    False if self.last_state == STATE_OPENING else True
                )
            else:
                logging.info("down packet not sent 'stopping'")
                self._attr_state = None
                self._attr_is_closed = None

        elif not self._attr_is_closed:
            ack_status = await self.api.protocol.sender.send_packet_with_ack(up_packet)
            if ack_status:
                logging.info("up packet sent 'stopping'")
                self._attr_state = self.last_state
                self._attr_is_closed = (
                    False if self.last_state == STATE_OPENING else True
                )
            else:
                logging.info("up packet not sent 'stopping'")
                self._attr_state = None
                self._attr_is_closed = None
        self.async_write_ha_state()
