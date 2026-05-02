"""Config flow for Shell Recharge integration."""

from __future__ import annotations

from asyncio import CancelledError
from typing import Any

import logging
import voluptuous as vol
from aiohttp.client_exceptions import ClientError
from homeassistant import config_entries
from homeassistant.data_entry_flow import section
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from shellrecharge.user import LoginFailedError

from .api import ShellEvApi, ShellEvApiError, ShellEvAuthError, ShellEvLocationNotFoundError
from .const import DOMAIN

import shellrecharge

_LOGGER = logging.getLogger(__name__)

RECHARGE_SCHEMA = vol.Schema(
    {
        vol.Optional("public"): section(
            vol.Schema(
                {
                    vol.Required("client_id"): str,
                    vol.Required("client_secret"): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Required("latitude"): vol.Coerce(float),
                    vol.Required("longitude"): vol.Coerce(float),
                    vol.Optional("limit", default=25): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=100)
                    ),
                }
            ),
            {"collapsed": False},
        ),
        vol.Optional("private"): section(
            vol.Schema(
                {
                    vol.Optional("email"): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.EMAIL)
                    ),
                    vol.Optional("password"): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            {"collapsed": True},
        ),
    }
)


class ShellRechargeFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for shell_recharge_ev."""

    VERSION = 5

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=RECHARGE_SCHEMA)

        try:
            pub = user_input.get("public") or {}
            priv = user_input.get("private") or {}

            if (
                pub.get("client_id")
                and pub.get("client_secret")
                and pub.get("latitude") is not None
                and pub.get("longitude") is not None
            ):
                latitude = float(pub["latitude"])
                longitude = float(pub["longitude"])
                limit = int(pub.get("limit", 25))
                unique_id = f"public-{latitude:.6f}-{longitude:.6f}-{limit}"
                api = ShellEvApi(
                    websession=async_get_clientsession(self.hass),
                    client_id=pub["client_id"],
                    client_secret=pub["client_secret"],
                )
                # Validate OAuth and the nearby search. Do not send radius; Shell sandbox rejects it in some tenants.
                await api.locations_nearby(latitude, longitude, limit=limit)
                user_input["public"] = {
                    "client_id": pub["client_id"],
                    "client_secret": pub["client_secret"],
                    "latitude": latitude,
                    "longitude": longitude,
                    "limit": limit,
                }

            elif priv.get("email") and priv.get("password"):
                unique_id = priv["email"]
                shell_api = shellrecharge.Api(websession=async_get_clientsession(self.hass))
                user = await shell_api.get_user(
                    email=unique_id,
                    pwd=priv["password"],
                )
                user_input["private"]["api_key"] = user.cookies["tnm_api"]

            else:
                errors["base"] = "missing_data"
                return self.async_show_form(
                    step_id="user", data_schema=RECHARGE_SCHEMA, errors=errors
                )

        except LoginFailedError:
            errors["base"] = "login_failed"
        except ShellEvAuthError as exc:
            errors["base"] = "auth_failed"
            _LOGGER.error("Shell Recharge authentication failed: %s", exc)
        except ShellEvLocationNotFoundError as exc:
            errors["base"] = "empty_response"
            _LOGGER.error("Shell Recharge no public locations found: %s", exc)
        except (ShellEvApiError, ClientError, TimeoutError, CancelledError) as exc:
            errors["base"] = "cannot_connect"
            _LOGGER.error("Shell Recharge API/connection failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            errors["base"] = "unknown"
            _LOGGER.exception("Unexpected Shell Recharge config-flow error: %s", exc)

        if not errors:
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured(updates=user_input)
            return self.async_create_entry(
                title=f"Shell Recharge {unique_id}",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user", data_schema=RECHARGE_SCHEMA, errors=errors
        )
