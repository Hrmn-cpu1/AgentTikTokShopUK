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
