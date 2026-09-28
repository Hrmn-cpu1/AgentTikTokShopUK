# TikTok Android Login Kit audit

Audited on 2026-09-28 at repository HEAD `d29b6aefd7a85a1e18b82efa35d23b2ceaf8daeb`.

## Before this change

- `src/ConnectionGate.tsx` called `/v1/tiktok/authorize-native`, then opened the returned `https://www.tiktok.com/v2/auth/authorize/` URL with Capacitor Browser. That is the **Web OAuth authorization shape**, not TikTok Android OpenSDK.
- The URL requested `user.info.basic,video.upload,video.publish`.
- The backend marked the intent as `ANDROID`, but exchanged the code in its HTTPS GET callback without `code_verifier`; it then opened a custom URI that carried no code. The Android app did not use TikTok OpenSDK or PKCE.
- `AndroidManifest.xml` had only a custom-scheme wake-up intent filter. No TikTok HTTPS App Link was registered.
- `server/tiktok_provider.py` already had unmounted video helper functions, but no Content Posting API route or demonstrated end-to-end posting flow.

## Current implementation

- Android uses TikTok OpenSDK Login Kit 2.3.1, `AuthRequest`, `AuthApi`, and SDK `PKCEUtils`.
- Each authorization gets an unpredictable state from the authenticated backend and a new SDK PKCE verifier. OpenSDK 2.3.1 `PKCEUtils` generates a 32-character alphanumeric verifier and derives the SHA-256 challenge. The verifier is encrypted in a short-lived Android Keystore-backed store across the external TikTok/Chrome handoff.
- TikTok returns the authorization response to the Android activity through the HTTPS App Link. The app checks state, then posts the code, verifier, and state to `/v1/tiktok/android-exchange` using the operator's same-origin session and CSRF token.
- The backend consumes the state before external exchange, requires the state to match the operator session, sends the verifier to TikTok's v2 token endpoint, verifies `user.info.basic`, encrypts tokens at rest, and returns only public connection state.
- The Web Login Kit remains a separate backend redirect flow and does not use PKCE. Android and Web request `user.info.basic` only. `video.upload` and `video.publish` remain isolated for a later Content Posting phase.

## Current limits / external gates

- The Android redirect URI is `https://tiktok-shop-profit-agent-uk-production.up.railway.app/v1/tiktok/callback`; Android must capture it as a verified App Link. The backend's public `/.well-known/assetlinks.json` publishes the Digital Asset Links association from the non-secret Railway variable `ANDROID_APP_SHA256_FINGERPRINTS`, which must contain the exact signing certificate SHA-256.
- The repo has no release keystore/signing configuration. The existing APK workflow is debug-signed, and its runner-generated debug certificate is not a production identity. Do not register a debug fingerprint as the Play Store release fingerprint.
- The callback URI, package `com.tiktokshopprofitagent.app`, app client key, Android certificate fingerprints, and `user.info.basic` must be registered in the existing TikTok Developer app. No TikTok account login or authorization has been observed.
- Repository tests and CI can prove implementation behavior with a fake provider only. They cannot prove TikTok account authorization, Android App Link verification, token issuance by TikTok, Play signing, or review approval.

## Current official source basis

- TikTok Android Login Kit instructions require `AuthApi`, `AuthRequest`, `user.info.basic`, HTTPS `redirectUri`, `codeVerifier`, activity callback parsing, and sending `code` plus `code_verifier` to the server: <https://developers.tiktok.com/docs/en/login-kit-android-quickstart-v2/>
- TikTok token management requires `code_verifier` for mobile and desktop, the same redirect URI used to request the code, and server-side token storage: <https://developers.tiktok.com/docs/en/oauth-user-access-token-management>
- Official Android OpenSDK: <https://github.com/tiktok/tiktok-opensdk-android/tree/v2.3.1>
