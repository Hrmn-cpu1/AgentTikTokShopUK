"""Official TikTok Login Kit web endpoints only; commerce authorization is separate."""
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field


AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
REVOKE_URL = "https://open.tiktokapis.com/v2/oauth/revoke/"
USER_URL = "https://open.tiktokapis.com/v2/user/info/"


class ProviderError(Exception):
    pass


class Tokens(BaseModel):
    open_id: str = Field(min_length=1)
    access_token: str = Field(min_length=1)
    refresh_token: str = Field(min_length=1)
    scope: str
    token_type: str
    expires_in: int = Field(gt=0)
    refresh_expires_in: int = Field(gt=0)


class OfficialTikTokProvider:
    def __init__(self, client_key: str, client_secret: str, redirect_uri: str):
        self.client_key = client_key
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def authorization_url(self, state: str) -> str:
        return AUTHORIZE_URL + "?" + urlencode({"client_key": self.client_key,
            "scope": "user.info.basic", "response_type": "code", "redirect_uri": self.redirect_uri, "state": state})

    def _post(self, url: str, payload: dict[str, str]) -> dict:
        try:
            with httpx.Client(timeout=10) as client:
                response = client.post(url, data={"client_key": self.client_key,
                    "client_secret": self.client_secret, **payload})
                response.raise_for_status()
                result = response.json()
            if not isinstance(result, dict) or result.get("error"):
                raise ProviderError("TikTok rejected authorization")
            return result
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("TikTok authorization unavailable") from exc

    def exchange(self, code: str) -> Tokens:
        result = self._post(TOKEN_URL, {"grant_type": "authorization_code", "code": code,
            "redirect_uri": self.redirect_uri})
        try:
            tokens = Tokens.model_validate(result)
            if tokens.token_type != "Bearer":
                raise ValueError("unexpected token type")
            return tokens
        except ValueError as exc:
            raise ProviderError("Invalid TikTok token response") from exc

    def refresh(self, refresh_token: str) -> Tokens:
        result = self._post(TOKEN_URL, {"grant_type": "refresh_token", "refresh_token": refresh_token})
        try:
            tokens = Tokens.model_validate(result)
            if tokens.token_type != "Bearer":
                raise ValueError("unexpected token type")
            return tokens
        except ValueError as exc:
            raise ProviderError("Invalid TikTok refresh response") from exc

    def identity(self, access_token: str) -> tuple[str, str | None]:
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(USER_URL, params={"fields": "open_id,display_name"},
                    headers={"Authorization": f"Bearer {access_token}"})
                response.raise_for_status()
                result = response.json()
            if result.get("error", {}).get("code") != "ok":
                raise ProviderError("TikTok identity unavailable")
            user = result["data"]["user"]
            if not isinstance(user["open_id"], str) or not user["open_id"]:
                raise ProviderError("TikTok identity unavailable")
            return user["open_id"], user.get("display_name")
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ProviderError("TikTok identity unavailable") from exc

    def revoke(self, access_token: str) -> None:
        self._post(REVOKE_URL, {"token": access_token})
