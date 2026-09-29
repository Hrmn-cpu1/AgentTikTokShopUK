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

    def exchange(self, code: str, code_verifier: str | None = None) -> Tokens:
        payload = {"grant_type": "authorization_code", "code": code,
            "redirect_uri": self.redirect_uri}
        if code_verifier is not None:
            payload["code_verifier"] = code_verifier
        result = self._post(TOKEN_URL, payload)
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


CONTENT_TARGET_SCOPE = {
    "TIKTOK_OFFICIAL_DIRECT_POST": "video.publish",
    "TIKTOK_OFFICIAL_UPLOAD_DRAFT": "video.upload",
}


class TikTokOfficialProvider:
    """Fail-closed Content Posting boundary for controlled certification."""

    provider = "TIKTOK_OFFICIAL"

    def __init__(self, *, enabled: bool = False, content_posting_approved: bool = False,
                 certified: bool = False):
        self.enabled = bool(enabled)
        self.content_posting_approved = bool(content_posting_approved)
        self.certified = bool(certified)

    @staticmethod
    def _scopes(granted_scopes) -> set[str]:
        if isinstance(granted_scopes, str):
            return set(granted_scopes.replace(",", " ").split())
        return {str(item) for item in granted_scopes or () if str(item)}

    def capabilities(self, granted_scopes, *, active: bool = True) -> dict:
        scopes = self._scopes(granted_scopes)
        return {
            "provider": self.provider,
            "connection": "ACTIVE" if active else "UNKNOWN",
            "contentPostingApproval": "APPROVED" if self.content_posting_approved else "NOT_PROVEN",
            "videoUpload": "AVAILABLE" if active and self.content_posting_approved and "video.upload" in scopes
                else "UNAVAILABLE",
            "videoPublish": "AVAILABLE" if active and self.content_posting_approved and "video.publish" in scopes
                else "UNAVAILABLE",
            "realDispatch": "CERTIFICATION_REQUIRED",
            "configuredDispatchFlag": self.enabled,
            "certified": self.certified,
            "grantedScopes": sorted(scopes),
        }

    def prepare(self, *, target: str, granted_scopes, active: bool,
                artifact_verified: bool, contract_valid: bool, target_bound: bool) -> dict:
        required_scope = CONTENT_TARGET_SCOPE.get(target)
        if required_scope is None:
            raise ProviderError("Unsupported TikTok delivery target")
        scopes = self._scopes(granted_scopes)
        if not active:
            raise ProviderError("Active TikTok connection required")
        if not self.content_posting_approved:
            raise ProviderError("TikTok Content Posting approval is not proven")
        if required_scope not in scopes:
            raise ProviderError(f"Required TikTok scope is missing: {required_scope}")
        if not artifact_verified:
            raise ProviderError("Verified QUALITY_PASS artifact required")
        if not contract_valid:
            raise ProviderError("Frozen Action Contract / Effect Ledger binding required")
        if not target_bound:
            raise ProviderError("Target TikTok account binding required")
        return {"target": target, "requiredScope": required_scope, "prepared": True}

    def dry_run(self, **kwargs) -> dict:
        prepared = self.prepare(**kwargs)
        return {**prepared, "result": "DRY_RUN_ONLY", "externalEffect": False}

    def dispatch(self, *args, **kwargs):
        if not self.enabled:
            raise ProviderError("TikTok real dispatch is disabled")
        if not self.certified:
            raise ProviderError("TikTok real dispatch is not certified")
        raise ProviderError("Controlled real dispatch is intentionally unavailable in the correction gate")

    def status(self, access_token: str, publish_id: str) -> dict:
        if not publish_id:
            raise ProviderError("publish_id is required")
        return fetch_publish_status(access_token, publish_id)

    def observe(self, access_token: str, publish_id: str) -> dict:
        return self.status(access_token, publish_id)

    @staticmethod
    def reconcile(observation: dict) -> dict:
        status = str(observation.get("status") or "")
        public_ids = observation.get("publicaly_available_post_id") or []
        if isinstance(public_ids, str):
            public_ids = [public_ids]
        public_ids = [str(item) for item in public_ids if item]
        if status == "FAILED":
            return {"state": "FAILED", "confirmed": False,
                "failureReason": observation.get("fail_reason")}
        if status == "PUBLISH_COMPLETE" and public_ids:
            return {"state": "CONFIRMED", "confirmed": True, "publicPostId": public_ids[0]}
        if status in {"PROCESSING_UPLOAD", "PROCESSING_DOWNLOAD", "SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"}:
            return {"state": "PROCESSING", "confirmed": False}
        return {"state": "UNKNOWN", "confirmed": False}
