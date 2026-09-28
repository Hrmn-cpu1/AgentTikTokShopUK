"""Fake official provider: engineering coverage without real commercial authorization."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from server.api import create_app
from server.models import OperatorSession, TikTokConnection, TikTokOAuthIntent
from server.tiktok_provider import ProviderError, Tokens

TOKEN = "test-only-operator-secret-32-characters-long"


LOGIN = "operator-login-key-with-at-least-32-characters"
ENCRYPTION_KEY = Fernet.generate_key()


@pytest.fixture()
def database(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'login.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config(str(Path(__file__).resolve().parents[2] / "alembic.ini")), "head")
    return url


class FakeProvider:
    def __init__(self):
        self.client_key = "test-tiktok-client-key"
        self.redirect_uri = "https://agent.example/v1/tiktok/callback"
        self.revoked = False
        self.fail_revoke = False
        self.fail_refresh = False
        self.open_id = "creator-uk-1"
        self.refresh_count = 0
        self.exchange_verifiers = []

    def authorization_url(self, state):
        return "https://www.tiktok.com/v2/auth/authorize/?" + f"state={state}&scope=user.info.basic"

    def exchange(self, code, code_verifier=None):
        if code != "valid-code":
            raise ProviderError("Code rejected")
        self.exchange_verifiers.append(code_verifier)
        return Tokens(open_id=self.open_id, access_token="secret-access", refresh_token="secret-refresh",
            scope="user.info.basic", token_type="Bearer", expires_in=86400, refresh_expires_in=31536000)

    def identity(self, access_token):
        assert access_token in {"secret-access", "rotated-access"}
        return self.open_id, "UK Creator"

    def refresh(self, token):
        if self.fail_refresh:
            raise ProviderError("Refresh failed")
        assert token in {"secret-refresh", "rotated-refresh"}
        self.refresh_count += 1
        return Tokens(open_id=self.open_id, access_token="rotated-access", refresh_token="rotated-refresh",
            scope="user.info.basic", token_type="Bearer", expires_in=86400, refresh_expires_in=31536000)

    def revoke(self, access_token):
        if self.fail_revoke:
            raise ProviderError("Revoke failed")
        assert access_token in {"secret-access", "rotated-access"}
        self.revoked = True


def browser(database, provider):
    return TestClient(create_app(database, TOKEN, tiktok_provider=provider,
        operator_login_secret=LOGIN, token_encryption_key=ENCRYPTION_KEY), base_url="https://agent.example")


def login(client):
    assert client.post("/v1/operator/login", json={"access_key": LOGIN}).status_code == 200
    assert client.get("/v1/operator/session").json() == {"authenticated": True}


def begin(client):
    response = client.get("/v1/tiktok/authorize", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith("https://www.tiktok.com/v2/auth/authorize/")
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def connect(client):
    state = begin(client)
    response = client.get("/v1/tiktok/callback", params={"state": state, "code": "valid-code"}, follow_redirects=False)
    assert response.status_code == 303
    return state


def test_session_state_callback_secrets_and_restart(database):
    provider = FakeProvider()
    anonymous = browser(database, provider)
    assert anonymous.get("/v1/tiktok/connection").status_code == 401
    assert anonymous.get("/v1/tiktok/authorize").status_code == 401
    assert anonymous.post("/v1/operator/login", json={"access_key": "bad"}).status_code == 401
    c = browser(database, provider)
    login(c)
    assert c.get("/v1/tiktok/connection").json()["capabilities"]["IDENTITY"] == "UNKNOWN"
    state = begin(c)
    assert c.get("/v1/tiktok/callback", params={"state": "wrong", "code": "valid-code"}).status_code == 403
    assert anonymous.get("/v1/tiktok/callback", params={"state": state, "code": "valid-code"}).status_code == 401
    assert c.get("/v1/tiktok/callback", params={"state": state, "code": "wrong"}).status_code == 502
    assert c.get("/v1/tiktok/callback", params={"state": state, "code": "valid-code"}).status_code == 403
    state = connect(c)
    assert c.get("/v1/tiktok/callback", params={"state": state, "code": "valid-code"}).status_code == 403
    output = c.get("/v1/tiktok/connection").text
    assert "secret-access" not in output and "secret-refresh" not in output
    assert "encrypted" not in output and "creator-uk-1" in output
    state = c.get("/v1/tiktok/connection").json()
    assert state["connection"]["status"] == "ACTIVE"
    assert state["capabilities"]["IDENTITY"] == "AVAILABLE"
    assert state["capabilities"]["AFFILIATE"] == "UNKNOWN"
    assert state["capabilities"]["ORDER_READ"] == "UNKNOWN"
    assert state["mode"] == "LIMITED"
    csrf = c.cookies.get("operator_csrf")
    assert c.post("/v1/tiktok/manual-verification", json={"uk_market_evidence_ref":"shop:status:uk",
        "affiliate_evidence_ref":"affiliate:dashboard"}).status_code == 403
    assertion = c.post("/v1/tiktok/manual-verification",headers={"X-CSRF-Token":csrf},json={
        "uk_market_evidence_ref":"shop:status:uk","affiliate_evidence_ref":"affiliate:dashboard"}).json()
    assert assertion["mode"] == "MANUAL_VERIFIED"
    assert assertion["capabilities"]["AFFILIATE"] == "UNKNOWN"
    assert assertion["connection"]["manualVerification"]["source"] == "OPERATOR_ASSERTION"
    with Session(create_engine(database)) as session:
        row = session.scalar(select(TikTokConnection))
        assert row.encrypted_access_token != "secret-access"
        assert row.encrypted_refresh_token != "secret-refresh"
        original_id = row.connection_id
    recovered = browser(database, provider)
    recovered.cookies.update(c.cookies)
    assert recovered.get("/v1/tiktok/connection").json()["connection"]["connectionId"] == original_id
    connect(recovered)
    assert recovered.get("/v1/tiktok/connection").json()["connection"]["connectionId"] == original_id
    provider.open_id = "different-account"
    assert recovered.get("/v1/tiktok/callback", params={"state": begin(recovered), "code": "valid-code"}).status_code == 409


def test_expired_state_token_refresh_revocation_and_disconnect(database):
    provider = FakeProvider()
    c = browser(database, provider)
    login(c)
    state = begin(c)
    with Session(create_engine(database)) as session:
        intent = session.scalar(select(TikTokOAuthIntent))
        intent.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    assert c.get("/v1/tiktok/callback", params={"state": state, "code": "valid-code"}).status_code == 403
    connect(c)
    engine = create_engine(database)
    with Session(engine) as session:
        record = session.scalar(select(TikTokConnection))
        record.access_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    assert c.get("/v1/tiktok/connection").json()["connection"]["status"] == "ACTIVE"
    assert provider.refresh_count == 1
    with Session(engine) as session:
        record = session.scalar(select(TikTokConnection))
        assert Fernet(ENCRYPTION_KEY).decrypt(record.encrypted_refresh_token.encode()) == b"rotated-refresh"
        record.access_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    provider.fail_refresh = True
    assert c.get("/v1/tiktok/connection").json()["connection"]["status"] == "REFRESH_FAILED"
    assert c.get("/v1/tiktok/connection").json()["capabilities"]["IDENTITY"] == "UNKNOWN"
    provider.fail_refresh = False
    connect(c)
    assert c.post("/v1/tiktok/disconnect").status_code == 403
    csrf = c.cookies.get("operator_csrf")
    assert csrf
    provider.fail_revoke = True
    assert c.post("/v1/tiktok/disconnect", headers={"X-CSRF-Token": csrf}).status_code == 502
    assert c.get("/v1/tiktok/connection").json()["connection"]["status"] == "UNKNOWN"
    provider.fail_revoke = False
    assert c.post("/v1/tiktok/disconnect", headers={"X-CSRF-Token": csrf}).json()["connection"]["status"] == "REVOKED"
    assert provider.revoked
    assert c.get("/v1/tiktok/connection").json()["mode"] == "BLOCKED"
    assert c.get("/v1/tiktok/connection").json()["capabilities"]["IDENTITY"] == "BLOCKED"
    ledger = TestClient(create_app(database, TOKEN),headers={"Authorization":f"Bearer {TOKEN}"})
    assert ledger.post("/v1/experiments",json={"experiment_id":"EXP-CLOSED","decision_id":"DEC-CLOSED",
        "product_id":"product","creative_id":"creative","publication_action_id":"action",
        "authority_evidence_ref":"receipt:authority"}).status_code == 403
    assert c.post("/v1/tiktok/disconnect", headers={"X-CSRF-Token": csrf}).status_code == 200
    connect(c)
    assert c.get("/v1/tiktok/connection").json()["connection"]["status"] == "ACTIVE"


def test_refresh_expiry_blocks_and_callback_error_consumes_state(database):
    provider=FakeProvider()
    c=browser(database,provider)
    login(c)
    state=begin(c)
    assert c.get("/v1/tiktok/callback", params={"state":state,"error":"access_denied"}).status_code==400
    assert c.get("/v1/tiktok/callback", params={"state":state,"code":"valid-code"}).status_code==403
    connect(c)
    with Session(create_engine(database)) as session:
        record=session.scalar(select(TikTokConnection))
        record.refresh_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        session.commit()
    result=c.get("/v1/tiktok/connection").json()
    assert result["connection"]["status"]=="EXPIRED"
    assert result["capabilities"]["IDENTITY"]=="UNKNOWN"


def test_provider_identity_revocation_is_revalidated_and_manual_proof_expires(database):
    provider=FakeProvider()
    c=browser(database,provider)
    login(c)
    connect(c)
    csrf=c.cookies.get("operator_csrf")
    c.post("/v1/tiktok/manual-verification",headers={"X-CSRF-Token":csrf},json={
        "uk_market_evidence_ref":"market:uk:receipt","affiliate_evidence_ref":"affiliate:proof"})
    with Session(create_engine(database)) as session:
        record=session.scalar(select(TikTokConnection))
        record.manual_verified_at=datetime.now(timezone.utc)-timedelta(days=31)
        session.commit()
    assert c.get("/v1/tiktok/connection").json()["mode"]=="LIMITED"
    provider.open_id="revoked-or-different"
    with Session(create_engine(database)) as session:
        record=session.scalar(select(TikTokConnection))
        record.last_validated_at=datetime.now(timezone.utc)-timedelta(minutes=16)
        session.commit()
    assert c.get("/v1/tiktok/connection").json()["connection"]["status"]=="UNKNOWN"


def test_android_pkce_exchange_has_one_use_session_bound_state(database):
    provider=FakeProvider()
    app=browser(database,provider)
    login(app)
    csrf=app.cookies.get("operator_csrf")
    start=app.post("/v1/tiktok/android-intent",headers={"X-CSRF-Token":csrf})
    assert start.status_code==200
    payload=start.json()
    state=payload["state"]
    assert payload["clientKey"]==provider.client_key
    assert payload["redirectUri"]==provider.redirect_uri
    assert "secret" not in str(payload)
    body={"state":state,"code":"valid-code","code_verifier":"v"*32}
    assert app.post("/v1/tiktok/android-exchange",json={**body,"state":"wrong-state-value-at-least-20"},headers={"X-CSRF-Token":csrf}).status_code==403
    other=browser(database,provider)
    login(other)
    assert other.post("/v1/tiktok/android-exchange",json=body,
        headers={"X-CSRF-Token":other.cookies.get("operator_csrf")}).status_code==403
    result=app.post("/v1/tiktok/android-exchange",json=body,headers={"X-CSRF-Token":csrf})
    assert result.status_code==200
    assert result.json()["connection"]["status"]=="ACTIVE"
    assert "secret-access" not in result.text and "secret-refresh" not in result.text
    assert provider.exchange_verifiers==["v"*32]
    assert app.post("/v1/tiktok/android-exchange",json=body,headers={"X-CSRF-Token":csrf}).status_code==403
    assert app.get("/v1/tiktok/connection").json()["capabilities"]["IDENTITY"]=="AVAILABLE"
    another=app.post("/v1/tiktok/android-intent",headers={"X-CSRF-Token":csrf}).json()
    with Session(create_engine(database)) as session:
        intent=session.get(TikTokOAuthIntent, sha256(another["state"].encode()).hexdigest())
        owner=session.get(OperatorSession,intent.session_hash)
        owner.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        session.commit()
    assert app.post("/v1/tiktok/android-exchange",json={**body,"state":another["state"]},
        headers={"X-CSRF-Token":csrf}).status_code==401


def test_android_assetlinks_is_public_and_accepts_only_certificate_fingerprints(database, monkeypatch):
    provider=FakeProvider()
    c=browser(database,provider)
    monkeypatch.delenv("ANDROID_APP_SHA256_FINGERPRINTS", raising=False)
    assert c.get("/.well-known/assetlinks.json").json()==[]
    fingerprint=":".join(["AB"]*32)
    monkeypatch.setenv("ANDROID_APP_SHA256_FINGERPRINTS",fingerprint.lower())
    response=c.get("/.well-known/assetlinks.json")
    assert response.status_code==200
    assert response.json()==[{"relation":["delegate_permission/common.handle_all_urls"],
        "target":{"namespace":"android_app","package_name":"com.tiktokshopprofitagent.app",
            "sha256_cert_fingerprints":[fingerprint]}}]
    monkeypatch.setenv("ANDROID_APP_SHA256_FINGERPRINTS","not-a-certificate")
    assert c.get("/.well-known/assetlinks.json").status_code==500
