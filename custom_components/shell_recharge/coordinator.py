"""Data update coordinator for Shell Recharge."""

import logging
from asyncio.exceptions import CancelledError

from aiohttp.client_exceptions import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from shellrecharge.user import AssetsEmptyError, DetailedChargePointEmptyError, User
from shellrecharge.usermodels import DetailedAssets

from .api import Location, ShellEvApi, ShellEvApiError, ShellEvAuthError
from .const import DOMAIN, UPDATE_INTERVAL, SerialNumber

_LOGGER = logging.getLogger(__name__)


class ShellRechargeUserDataUpdateCoordinator(DataUpdateCoordinator[DetailedAssets]):
    """Handles data updates for private chargers."""

    def __init__(self, hass: HomeAssistant, api: User) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )

        self.api = api

    async def _async_update_data(self) -> DetailedAssets:
        """Fetch data from API endpoint."""
        data = None
        try:
            data = await self.api.get_detailed_assets()
        except AssetsEmptyError as exc:
            _LOGGER.info("User has no charger(s) or card(s)")
            raise UpdateFailed() from exc
        except DetailedChargePointEmptyError as exc:
            _LOGGER.info("User has no charger(s)")
            raise UpdateFailed() from exc
        except CancelledError as exc:
            _LOGGER.error("CancelledError while fetching user charger(s)")
            raise UpdateFailed() from exc
        except TimeoutError as exc:
            _LOGGER.error("TimeoutError while fetching user charger(s)")
            raise UpdateFailed() from exc
        except ClientError as exc:
            _LOGGER.error("ClientError while fetching user charger(s)")
            raise UpdateFailed() from exc
        except Exception as exc:
            _LOGGER.error(
                "Unexpected error fetching user charger(s): %s", exc, exc_info=True
            )
            raise UpdateFailed() from exc

        if data is None:
            _LOGGER.error("API returned None data for user charger(s)")
            raise UpdateFailed("API returned None data")

        return data

    async def toggle_session(
        self, charge_point: str, charge_token: str, toggle: str
    ) -> bool:
        """Toggle a charger session."""
        return bool(
            await self.api.toggle_charger(
                charger_id=charge_point, card_rfid=charge_token, action=toggle
            )
        )


class ShellRechargePublicDataUpdateCoordinator(DataUpdateCoordinator[Location | list[Location]]):
    """Handles data updates for public chargers via the official Shell EV API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: ShellEvApi,
        serial_number: SerialNumber | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        limit: int = 25,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.api = api
        self.serial_number = serial_number
        self.latitude = latitude
        self.longitude = longitude
        self.limit = limit

    async def _async_update_data(self) -> Location | list[Location]:
        """Fetch location data from the Shell EV API."""
        try:
            if self.serial_number:
                data = await self.api.location_by_id(self.serial_number)
            elif self.latitude is not None and self.longitude is not None:
                data = await self.api.locations_nearby(
                    self.latitude,
                    self.longitude,
                    limit=self.limit,
                )
            else:
                raise UpdateFailed("No public Shell Recharge lookup configured")
        except ShellEvAuthError as exc:
            _LOGGER.error(
                "Authentication failed for Shell EV API. Check your client_id and client_secret. Error: %s",
                exc,
            )
            raise UpdateFailed(str(exc)) from exc
        except ShellEvApiError as exc:
            _LOGGER.error("Error fetching public Shell Recharge locations: %s", exc)
            raise UpdateFailed(str(exc)) from exc
        except CancelledError as exc:
            _LOGGER.error("CancelledError while fetching public Shell Recharge locations")
            raise UpdateFailed() from exc
        except TimeoutError as exc:
            _LOGGER.error("TimeoutError while fetching public Shell Recharge locations")
            raise UpdateFailed() from exc
        except ClientError as exc:
            _LOGGER.error("ClientError while fetching public Shell Recharge locations")
            raise UpdateFailed() from exc
        except Exception as exc:
            _LOGGER.error(
                "Unexpected error fetching public Shell Recharge locations: %s",
                exc,
                exc_info=True,
            )
            raise UpdateFailed() from exc

        if not data:
            _LOGGER.error("API returned empty data for public Shell Recharge locations")
            raise UpdateFailed("API returned empty data")

        return data
