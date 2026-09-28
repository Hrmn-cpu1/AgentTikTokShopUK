# Content engine research notes

Scope: patterns only. None of the unaudited uploaders below is a production dependency. No cookie reuse, anti-bot evasion, private TikTok signing, CAPTCHA bypass, or bulk posting is selected.

## OSS references and classification

| Project | Classification | Useful pattern | Limitation / risk |
| --- | --- | --- | --- |
| [lofe-w/tiktok-creative-center-scraper-public](https://github.com/lofe-w/tiktok-creative-center-scraper-public) | UNOFFICIAL-BUT-PUBLIC-DATA (cookie/internal API dependent) | Normalize Creative Center datasets, region filters, item references and collection jobs | Internal endpoints/cookies are brittle and account-sensitive; not selected as a provider |
| [silencoo/TikTok-Api](https://github.com/silencoo/TikTok-Api) | PRIVATE/REVERSE-ENGINEERED; some retrieval targets are public data | Separate extraction from normalization and retain source IDs | TikTok private web endpoints, changing signatures, proxy/stealth advice; not selected |
| [GabrielLaxy/TikTokAIVideoGenerator](https://github.com/GabrielLaxy/TikTokAIVideoGenerator) | OFFICIAL tooling not implied; local content pipeline | Script → assets/voice → captions → FFmpeg/MoviePy render; explicit dependencies | Groq/Together credentials, Whisper/ImageMagick/FFmpeg and asset/voice rights/costs; only the staged pipeline idea is reused |
| [psyv27/tiktok-publisher](https://github.com/psyv27/tiktok-publisher) | OFFICIAL API integration pattern (repo itself is third-party) | OAuth scopes, upload-vs-direct-post separation, status transitions and refresh handling | Repository claims are not evidence this client is audited or currently works; official scopes/consent still gate it |
| [wkaisertexas/tiktok-uploader](https://github.com/wkaisertexas/tiktok-uploader) | BROWSER-AUTOMATION | Queue lifecycle, scheduling, captions and retries | Browser/session automation is brittle and account/ToS risky; not selected |
| [YanivGabay/tiktok-uploader](https://github.com/YanivGabay/tiktok-uploader) | BROWSER-AUTOMATION | CLI queue and explicit upload lifecycle | Session token reuse and UI breakage; not selected |
| [makiisthenes/TiktokAutoUploader](https://github.com/makiisthenes/TiktokAutoUploader) | PRIVATE/REVERSE-ENGINEERED; UNSAFE/BYPASS indicators | Job queue, retries and upload progress as abstract ideas | Requests/proxy/private-flow approaches are high fragility and account risk; not selected |
| [jefftko/PostFlow](https://github.com/jefftko/PostFlow) | BROWSER-AUTOMATION | Queue, draft lifecycle, cover, schedule and status recovery patterns | Playwright/QR session reuse; not selected for production delivery |
| [hyqshr/Douyin-Tiktok-Uploader](https://github.com/hyqshr/Douyin-Tiktok-Uploader) | BROWSER-AUTOMATION / unofficial | Multi-stage upload job and failure reporting | UI/session path is not a stable public API; not selected |

## Cross-synthesis

- Discovery should preserve the raw source reference, collection time, geography, and each absent metric as `UNKNOWN`. This implementation starts with unauthenticated Google Trends RSS restricted to `geo=BR`; it signals public search interest, never TikTok views or engagement.
- Rank from named, reproducible components and retain those components with the selected evidence. Deduplicate using a stable source + market + topic identity.
- Keep the creative plan as the single input to rendering. Preserve hook, scene durations, caption/hashtags, asset rights plan, experiment hypothesis, and next mutation.
- Render locally with FFmpeg and persist a media hash plus manifest, captions, and a thumbnail. A queue can use lease/retry/idempotency ideas from the OSS projects without copying their uploader mechanisms.
- Delivery must be a separate state machine from render. Observe only provider status or owner-supplied verifiable evidence. Tie each lesson to the prior experiment before selecting its mutation.
- Deduplicate before retrying external effects; never automatically retry a possibly accepted post without checking status.

## Locale search

Searches for Portuguese/Brazilian, English, Chinese, Russian, and Spanish TikTok content automation repositories were performed. The concrete project set above includes English and Chinese material. No distinct Portuguese-, Russian-, or Spanish-language repository was selected as sufficiently relevant and verifiable; this avoids inventing regional validation. Brazil coverage here comes from a source explicitly filtered to BR, not from repository language.

## TikTok delivery gate

- Official Upload API uses the `video.upload` scope and sends content to the creator's inbox/editing flow; delivery is not the same as a published post.
- Direct Post uses `video.publish`, creator capability information, user consent, and a status lookup. TikTok says unaudited clients are restricted to private visibility and may be blocked by account/client constraints.
- TikTok's Direct Post guidelines say API clients must not be limited to private/internal use and explicitly reject a utility for uploading to accounts managed by the developer/team. That conflicts with this owner's private-only APK, so API upload/direct post is not a selected route even if a new scope were requested.
- The connected account currently proves `user.info.basic` only. This implementation does not request a new scope or attempt API upload. The app uses the documented Android `ACTION_SEND` video intent with a FileProvider URI to open TikTok's composer when TikTok is installed; the creator retains the final publish action. This is a composer handoff, not proof of publication.
- Browser uploaders are technically capable of automating a final UI step, but are **TECHNICALLY POSSIBLE / NOT SELECTED** because session reuse, UI brittleness, account risk, and terms risk are not acceptable for this account.

Official references: [Content Posting API overview](https://developers.tiktok.com/products/content-posting-api/), [Upload API getting started](https://developers.tiktok.com/doc/content-posting-api-get-started-upload-content), [Direct Post](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post), [post status](https://developers.tiktok.com/docs/en/content-posting-api-reference-get-video-status), [Android Share Kit and intents](https://developers.tiktok.com/docs/en/share-kit-android-quickstart-v2), [content sharing guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines).
