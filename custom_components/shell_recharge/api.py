"""Async client for the official Shell EV API (sandbox/test)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientError

_LOGGER = logging.getLogger(__name__)

# Sandbox/test endpoints. Switch these to api.shell.com for production later.
OAUTH_URL = "https://api-test.shell.com/v2/oauth/token"
API_BASE = "https://api-test.shell.com/ev/v1"


class ShellEvApiError(Exception):
    """Base exception for Shell EV API errors."""


class ShellEvAuthError(ShellEvApiError):
    """Raised when OAuth2 authentication fails."""


class ShellEvLocationNotFoundError(ShellEvApiError):
    """Raised when a location cannot be found."""


@dataclass
class ElectricalProperties:
    powerType: str = ""
    voltage: float = 0.0
    amperage: float = 0.0
    maxElectricPower: float = 0.0


@dataclass
class Tariff:
    startFee: float = 0.0
    perMinute: float = 0.0
    perKWh: float = 0.0
    currency: str = ""
    updated: str = ""
    updatedBy: str = ""
    structure: str = ""


@dataclass
class Connector:
    uid: int = 0
    externalId: str = ""
    connectorType: str = "Unspecified"
    electricalProperties: ElectricalProperties = field(default_factory=ElectricalProperties)
    fixedCable: bool = False
    tariff: Tariff = field(default_factory=Tariff)


@dataclass
class Evse:
    uid: int = 0
    externalId: str = ""
    evseId: str = ""
    status: str = "Unknown"
    connectors: list[Connector] = field(default_factory=list)


@dataclass
class Coordinates:
    latitude: float = 0.0
    longitude: float = 0.0


@dataclass
class Address:
    streetAndNumber: str = ""
    postalCode: str = ""
    city: str = ""
    country: str = ""


@dataclass
class AccessibilityV2:
    status: str = ""


@dataclass
class Location:
    uid: int = 0
    externalId: str = ""
    coordinates: Coordinates = field(default_factory=Coordinates)
    operatorName: str = ""
    address: Address = field(default_factory=Address)
    evses: list[Evse] = field(default_factory=list)
    accessibilityV2: AccessibilityV2 = field(default_factory=AccessibilityV2)
    suboperatorName: str = ""
    supportPhoneNumber: str = ""
    openTwentyFourSeven: bool = True


EVSE_STATUS_OPTIONS = ["Available", "Occupied", "Unavailable", "Unknown"]


class ShellEvApi:
    """Async client for the Shell EV public locations API."""

    def __init__(self, websession: ClientSession, client_id: str, client_secret: str) -> None:
        self._session = websession
        self._client_id = client_id.strip()
        self._client_secret = client_secret.strip()
        self._access_token: str | None = None
        self._token_expires_at: datetime = datetime.min

    async def _get_token(self) -> str:
        """Return a valid Bearer token, fetching a new one when expired."""
        if self._access_token and datetime.now() < self._token_expires_at:
            return self._access_token

        _LOGGER.debug("Fetching new Shell EV API OAuth2 token from sandbox")
        try:
            async with self._session.post(
                OAUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=None,
            ) as resp:
                body = await resp.text()
                if resp.status in (401, 403):
                    raise ShellEvAuthError(
                        f"Sandbox OAuth rejected credentials with HTTP {resp.status}: {body[:500]}"
                    )
                if resp.status >= 400:
                    raise ShellEvApiError(
                        f"Sandbox OAuth returned HTTP {resp.status}: {body[:500]}"
                    )
                data = await resp.json()
        except ClientError as err:
            raise ShellEvApiError(f"Network error fetching OAuth token: {err}") from err

        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        self._token_expires_at = datetime.now() + timedelta(seconds=max(expires_in - 60, 0))
        return self._access_token

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        token = await self._get_token()
        request_id = str(uuid.uuid4())

        try:
            async with self._session.get(
                f"{API_BASE}{path}",
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "RequestId": request_id,
                    "Accept": "application/json",
                },
                timeout=None,
            ) as resp:
                body = await resp.text()
                if resp.status == 401:
                    self._access_token = None
                    raise ShellEvAuthError(f"Bearer token rejected by sandbox API: {body[:500]}")
                if resp.status == 404:
                    raise ShellEvLocationNotFoundError(f"Endpoint {path} returned 404")
                if resp.status >= 400:
                    raise ShellEvApiError(
                        f"Sandbox Shell EV API returned HTTP {resp.status} for {path}: {body[:500]}"
                    )
                return await resp.json()
        except ClientError as err:
            raise ShellEvApiError(f"Network error fetching {path}: {err}") from err

    async def locations_nearby(
        self,
        latitude: float,
        longitude: float,
        limit: int = 25,
        radius: int | None = None,
    ) -> list[Location]:
        params: dict[str, Any] = {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "limit": max(1, min(int(limit), 100)),
        }
        if radius is not None:
            params["radius"] = max(1, int(radius))

        _LOGGER.debug("Fetching nearby Shell EV sandbox locations with params %s", params)
        result = await self._get_json("/locations/nearby", params)
        locations = self._locations_from_payload(result)
        if not locations:
            raise ShellEvLocationNotFoundError("No nearby sandbox locations returned")
        return locations

    async def location_by_id(
        self,
        location_id: str,
        latitude: float | None = None,
        longitude: float | None = None,
        limit: int = 25,
    ) -> Location:
        location_id = str(location_id).strip()
        if not location_id:
            raise ShellEvLocationNotFoundError("No location external ID supplied")

        search_attempts: list[tuple[str, dict[str, Any]]] = [
            ("/locations", {"locationExternalId": location_id, "perPage": 1, "pageNumber": 1})
        ]
        if latitude is not None and longitude is not None:
            search_attempts.append(
                (
                    "/locations/nearby",
                    {
                        "latitude": latitude,
                        "longitude": longitude,
                        "limit": max(1, min(int(limit), 100)),
                        "locationExternalId": location_id,
                    },
                )
            )

        for path, params in search_attempts:
            result = await self._get_json(path, params)
            location = self._find_location_in_payload(result, location_id)
            if location is not None:
                return self._parse_location(location)

        raise ShellEvLocationNotFoundError(f"No location returned for external ID '{location_id}'")

    def _locations_from_payload(self, payload: dict[str, Any]) -> list[Location]:
        items = payload.get("data", [])
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            return []
        return [self._parse_location(item) for item in items if isinstance(item, dict)]

    @staticmethod
    def _find_location_in_payload(payload: dict[str, Any], location_id: str) -> dict[str, Any] | None:
        items = payload.get("data", [])
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            return None
        for item in items:
            if isinstance(item, dict) and str(item.get("externalId", "")).strip() == location_id:
                return item
        if len(items) == 1 and isinstance(items[0], dict):
            return items[0]
        return None

    @staticmethod
    def _parse_connector(data: dict) -> Connector:
        ep = data.get("electricalProperties") or {}
        tariff_data = data.get("tariff") or {}
        return Connector(
            uid=data.get("uid", 0),
            externalId=data.get("externalId", ""),
            connectorType=data.get("connectorType", "Unspecified"),
            electricalProperties=ElectricalProperties(
                powerType=ep.get("powerType", ""),
                voltage=float(ep.get("voltage", 0)),
                amperage=float(ep.get("amperage", 0)),
                maxElectricPower=float(ep.get("maxElectricPower", 0)),
            ),
            fixedCable=bool(data.get("fixedCable", False)),
            tariff=Tariff(
                startFee=float(tariff_data.get("startFee", 0)),
                perMinute=float(tariff_data.get("perMinute", 0)),
                perKWh=float(tariff_data.get("perKWh", 0)),
                currency=tariff_data.get("currency", ""),
                updated=tariff_data.get("updated", ""),
                updatedBy=tariff_data.get("updatedBy", ""),
                structure=tariff_data.get("structure", ""),
            ),
        )

    def _parse_evse(self, data: dict) -> Evse:
        return Evse(
            uid=data.get("uid", 0),
            externalId=data.get("externalId", ""),
            evseId=data.get("evseId", ""),
            status=data.get("status", "Unknown"),
            connectors=[self._parse_connector(c) for c in (data.get("connectors") or [])],
        )

    def _parse_location(self, data: dict) -> Location:
        coords = data.get("coordinates") or {}
        addr = data.get("address") or {}
        acc = data.get("accessibility") or {}
        return Location(
            uid=data.get("uid", 0),
            externalId=str(data.get("externalId", "")),
            coordinates=Coordinates(
                latitude=float(coords.get("latitude", 0)),
                longitude=float(coords.get("longitude", 0)),
            ),
            operatorName=data.get("operatorName", ""),
            address=Address(
                streetAndNumber=addr.get("streetAndNumber", ""),
                postalCode=addr.get("postalCode", ""),
                city=addr.get("city", ""),
                country=addr.get("country", ""),
            ),
            evses=[self._parse_evse(e) for e in (data.get("evses") or [])],
            accessibilityV2=AccessibilityV2(status=acc.get("status", "")),
            suboperatorName=data.get("suboperatorName", ""),
            supportPhoneNumber=data.get("supportPhoneNumber", ""),
            openTwentyFourSeven=bool(data.get("openTwentyFourSeven", True)),
        )
