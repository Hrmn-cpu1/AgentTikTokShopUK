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
            "scope": "user.info.basic,user.info.stats,video.list,video.upload,video.publish", "response_type": "code", "redirect_uri": self.redirect_uri, "state": state})

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


CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
DIRECT_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
UPLOAD_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

def _bearer_post(url: str, access_token: str, payload: dict) -> dict:
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(url, json=payload, headers={"Authorization": "Bearer " + access_token,
                "Content-Type": "application/json; charset=UTF-8"})
            response.raise_for_status()
            result = response.json()
        if result.get("error", {}).get("code") != "ok":
            raise ProviderError("TikTok content posting rejected")
        return result.get("data", {})
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        raise ProviderError("TikTok content posting unavailable") from exc

def query_creator_info(access_token: str) -> dict:
    return _bearer_post(CREATOR_INFO_URL, access_token, {})

def init_video_upload(access_token: str, size: int) -> dict:
    return _bearer_post(UPLOAD_INIT_URL, access_token, {"source_info":{"source":"FILE_UPLOAD",
        "video_size":size,"chunk_size":size,"total_chunk_count":1}})

def init_direct_post(access_token: str, size: int, title: str, privacy_level: str, is_aigc: bool=True) -> dict:
    return _bearer_post(DIRECT_INIT_URL, access_token, {"post_info":{"title":title,
        "privacy_level":privacy_level,"disable_duet":False,"disable_comment":False,
        "disable_stitch":False,"is_aigc":is_aigc},"source_info":{"source":"FILE_UPLOAD",
        "video_size":size,"chunk_size":size,"total_chunk_count":1}})

def upload_video_bytes(upload_url: str, video: bytes) -> None:
    try:
        with httpx.Client(timeout=60) as client:
            response = client.put(upload_url, content=video, headers={"Content-Type":"video/mp4",
                "Content-Length":str(len(video)),"Content-Range":f"bytes 0-{len(video)-1}/{len(video)}"})
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ProviderError("TikTok video upload failed") from exc

def fetch_publish_status(access_token: str, publish_id: str) -> dict:
    return _bearer_post(STATUS_URL, access_token, {"publish_id":publish_id})
