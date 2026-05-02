"""Config flow for Shell Recharge integration."""

from __future__ import annotations

from asyncio import CancelledError
from typing import Any

import voluptuous as vol
from aiohttp.client_exceptions import ClientError
from homeassistant import config_entries
from homeassistant.data_entry_flow import section
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from shellrecharge.user import LoginFailedError

from .api import ShellEvApi, ShellEvAuthError, ShellEvLocationNotFoundError
from .const import DOMAIN

import shellrecharge

RECHARGE_SCHEMA = vol.Schema(
    {
        vol.Optional("public"): section(
            vol.Schema(
                {
                    vol.Required("client_id"): str,
                    vol.Required("client_secret"): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Required("latitude"): NumberSelector(
                        NumberSelectorConfig(mode=NumberSelectorMode.BOX, step=0.000001)
                    ),
                    vol.Required("longitude"): NumberSelector(
                        NumberSelectorConfig(mode=NumberSelectorMode.BOX, step=0.000001)
                    ),
                    vol.Optional("radius", default=5000): NumberSelector(
                        NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=100, max=50000, step=100)
                    ),
                    vol.Optional("limit", default=25): NumberSelector(
                        NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=100, step=1)
                    ),
                    vol.Optional("serial_number"): str,
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

            if pub.get("client_id") and pub.get("client_secret") and pub.get("latitude") is not None and pub.get("longitude") is not None:
                latitude = float(pub["latitude"])
                longitude = float(pub["longitude"])
                radius = int(pub.get("radius", 5000))
                limit = int(pub.get("limit", 25))
                unique_id = f"public-{latitude:.6f}-{longitude:.6f}-{radius}-{limit}"
                api = ShellEvApi(
                    websession=async_get_clientsession(self.hass),
                    client_id=pub["client_id"],
                    client_secret=pub["client_secret"],
                )
                # Validate OAuth and that the location search returns data.
                await api.locations_nearby(latitude, longitude, limit=limit, radius=radius)

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
            self.hass.logger.error("Shell Recharge authentication failed: %s", exc)
        except ShellEvLocationNotFoundError as exc:
            errors["base"] = "empty_response"
            self.hass.logger.error("Shell Recharge no public locations found: %s", exc)
        except (ClientError, TimeoutError, CancelledError):
            errors["base"] = "cannot_connect"

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
