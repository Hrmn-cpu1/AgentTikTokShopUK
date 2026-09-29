from urllib.parse import parse_qs, urlparse

from server.tiktok_provider import OfficialTikTokProvider, TOKEN_URL


def test_login_authorization_requests_identity_scope_only():
    provider = OfficialTikTokProvider("public-key", "server-only-secret",
        "https://agent.example/v1/tiktok/callback")
    query = parse_qs(urlparse(provider.authorization_url("state-value")).query)
    assert query["scope"] == ["user.info.basic"]
    assert query["state"] == ["state-value"]
    assert query["redirect_uri"] == ["https://agent.example/v1/tiktok/callback"]
    assert "video.upload" not in query["scope"][0]
    assert "video.publish" not in query["scope"][0]


def test_token_exchange_includes_pkce_verifier_only_for_android(monkeypatch):
    provider = OfficialTikTokProvider("public-key", "server-only-secret",
        "https://agent.example/v1/tiktok/callback")
    requests = []

    def post(url, payload):
        requests.append((url, payload.copy()))
        return {"open_id":"creator-1", "access_token":"access", "refresh_token":"refresh",
            "scope":"user.info.basic", "token_type":"Bearer", "expires_in":86400,
            "refresh_expires_in":31536000}

    monkeypatch.setattr(provider, "_post", post)
    provider.exchange("web-code")
    provider.exchange("android-code", "v" * 32)
    assert requests[0][0] == TOKEN_URL
    assert "code_verifier" not in requests[0][1]
    assert requests[1][1]["code_verifier"] == "v" * 32


import pytest

from server.tiktok_provider import ProviderError, TikTokOfficialProvider


def test_content_posting_boundary_is_fail_closed_and_scope_explicit():
    boundary = TikTokOfficialProvider(content_posting_approved=True)
    caps = boundary.capabilities({"user.info.basic", "video.upload"}, active=True)
    assert caps["videoUpload"] == "AVAILABLE"
    assert caps["videoPublish"] == "UNAVAILABLE"
    result = boundary.dry_run(
        target="TIKTOK_OFFICIAL_UPLOAD_DRAFT",
        granted_scopes={"video.upload"},
        active=True,
        artifact_verified=True,
        contract_valid=True,
        target_bound=True,
    )
    assert result["result"] == "DRY_RUN_ONLY"
    assert result["externalEffect"] is False
    with pytest.raises(ProviderError, match="disabled"):
        boundary.dispatch()


def test_content_posting_dry_run_requires_approval_scope_and_binding():
    boundary = TikTokOfficialProvider(content_posting_approved=False)
    with pytest.raises(ProviderError, match="approval"):
        boundary.dry_run(
            target="TIKTOK_OFFICIAL_DIRECT_POST",
            granted_scopes={"video.publish"},
            active=True,
            artifact_verified=True,
            contract_valid=True,
            target_bound=True,
        )
    approved = TikTokOfficialProvider(content_posting_approved=True)
    with pytest.raises(ProviderError, match="video.publish"):
        approved.dry_run(
            target="TIKTOK_OFFICIAL_DIRECT_POST",
            granted_scopes={"user.info.basic"},
            active=True,
            artifact_verified=True,
            contract_valid=True,
            target_bound=True,
        )


def test_content_posting_reconciliation_never_equates_processing_with_confirmation():
    boundary = TikTokOfficialProvider()
    assert boundary.reconcile({"status": "PROCESSING_UPLOAD"})["state"] == "PROCESSING"
    assert boundary.reconcile({"status": "SEND_TO_USER_INBOX"})["confirmed"] is False
    assert boundary.reconcile({"status": "PUBLISH_COMPLETE"})["confirmed"] is False
    confirmed = boundary.reconcile({
        "status": "PUBLISH_COMPLETE",
        "publicaly_available_post_id": ["731234567890"],
    })
    assert confirmed == {"state": "CONFIRMED", "confirmed": True, "publicPostId": "731234567890"}
    assert boundary.reconcile({"status": "FAILED", "fail_reason": "duration_check_failed"})["state"] == "FAILED"
