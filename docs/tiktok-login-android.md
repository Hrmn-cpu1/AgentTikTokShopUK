# TikTok Login Kit on private Android APK

Architecture change audited on 2026-09-28. TikTok Sandbox Web configuration and the owner Target User were verified in the portal. Real-device authorization has not yet been run.

## Active Web Login Kit path

- The APK posts to `/v1/tiktok/native-web-intent` with its same-origin operator session and CSRF token. The backend creates a five-minute, one-time state bound to that session and returns the official TikTok Web authorization URL with only `user.info.basic`.
- Capacitor Browser opens that URL in an external Chrome Custom Tab; TikTok credentials are not entered into an embedded WebView.
- The HTTPS callback accepts only unconsumed Web or native-Web intents. For the native Web flow, it validates the original server-side operator session recorded in the intent, consumes state before the code exchange, exchanges the code server-side, verifies the returned identity/scope, and encrypts access and refresh tokens at rest.
- On success, the callback shows a success page in the external browser. Closing the Chrome Custom Tab returns to the APK, and the Capacitor Browser completion event refreshes `/v1/tiktok/connection`. No callback data or credentials are passed to the APK.
- The HTTPS callback is not registered as an Android App Link in the APK. That avoids Android intercepting the request before Railway can perform the server-side exchange.
- Web Login Kit uses server-side state and does not use PKCE. TikTok documents PKCE for the separate mobile/desktop flow. `video.upload` and `video.publish` remain outside this Login Kit scope.

## Retained OpenSDK implementation

- The OpenSDK 2.3.1 source, `AuthRequest`/`AuthApi`, PKCE helper, Android Keystore-backed verifier store, `/v1/tiktok/android-intent`, and `/v1/tiktok/android-exchange` remain in the repository while Web login is being validated on a real device.
- Those OpenSDK paths are not called by the active APK login button. Do not remove them until real Web login is proven and the owner confirms the retained code is unnecessary.

## Current limits / external gates

- The registered Web redirect URI is `https://tiktok-shop-profit-agent-uk-production.up.railway.app/v1/tiktok/callback`; the Web/Desktop URL is the Railway HTTPS origin. Android platform registration and Google Play URL are not used.
- The repo has no release keystore/signing configuration. The existing APK workflow is debug-signed. The owner must install the resulting APK and complete the real TikTok authorization to prove Chrome Custom Tab return, token issuance, token storage, and CONNECTED identity.
- Repository tests and CI can prove implementation behavior with a fake provider only. They cannot prove real TikTok authorization or token issuance. The OpenSDK PKCE path remains unproven on a real account and is not part of this Web flow.

## Current official source basis

- TikTok Login Kit Web uses the registered HTTPS callback and the Web OAuth authorization endpoint: <https://developers.tiktok.com/docs/en/login-kit-web/>
- TikTok token management uses server-side exchange and storage; PKCE is required for the separate mobile/desktop flow: <https://developers.tiktok.com/docs/en/oauth-user-access-token-management/>
- Official Android OpenSDK: <https://github.com/tiktok/tiktok-opensdk-android/tree/v2.3.1>
