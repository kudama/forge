# Lightroom Classic → Synology Photos
Project brief · 2026-10-25 · planning baseline

## Outcome
Export finished still images from Lightroom Classic directly into real Synology Photos virtual albums, including albums shown in the mobile app. A mounted-share export or target folder alone does not meet this requirement.

User-approved scope: custom Classic export destination, existing-album selection and new-album creation, ordinary Lightroom rendering controls, NAS-generated previews, and 2FA with a remembered Mac. This intake authorizes planning, GitHub records and bounded local implementation proposals; no live NAS credentials or access are currently provided.

## MVP user flow
1. Install a standalone .lrplugin on macOS and choose Synology Photos in Export.
2. Connect to the user's NAS over certificate-validated HTTPS using a non-admin account.
3. Enter password and OTP locally on first login; opt into Remember this Mac.
4. Load writable manual albums; choose one by stable ID or explicitly create one.
5. Use Lightroom's standard JPEG quality, sizing, sharpening, watermark and metadata settings.
6. Export: render JPEG, upload, resolve the Photos item ID, add it to the selected album, verify membership, report per-image outcome.
7. Later connections use the remembered-device credential when accepted; re-prompt if revoked/expired.

## Boundaries
Still JPEGs and manual virtual albums first. No video, local thumbnail tooling, background sync, Publish Service, server, database, AI runtime dependency, delete synchronization or public NAS exposure. Lightroom and Synology retain their respective rendering/indexing responsibilities. The plugin is an independent application, built by Forge.

## Architecture and contracts
Prefer Lua plus Lightroom's HTTP, UI and task facilities; small Synology adapter isolates private API variation. No persistent helper/service unless a verified SDK constraint requires one and Forge reviews the decision. Inspect the installed SDK before choosing credential storage; use Keychain-backed storage with verified behavior. If a native bridge is necessary, propose the smallest safe implementation before adding it.

Adapter operations: connect/authenticate; list writable albums with pagination and stable IDs; create manual album; upload rendered JPEG and obtain or resolve Photos item ID; add item to album; verify membership; logout/forget local credentials. Methods, versions, request encoding, auth/token requirements and Personal/Shared Space semantics remain unverified against the user's NAS.

Upload is not success until membership is verified. Track upload and membership separately. If membership fails, retain the known item ID for a bounded retry during that export; never blindly re-upload after an ambiguous response. Do not promise durable deduplication across exports in MVP. Define duplicate filename and existing-file policy before implementing upload. Do not delete remote files to recover failures.

## Authentication
Use SYNO.API.Auth over HTTPS, password + OTP for initial device enrollment, returned session/device material for supported later logins. Remembered-device authentication is a user decision, not disabling account 2FA. Verify actual fields and lifecycle against installed DSM; do not assume a generic refresh-token/OAuth flow.

Secrets (password, session, device credential and CSRF material as applicable) never enter presets, preferences, Git, prompts, fixtures, logs, command arguments or error bodies. Persist only necessary credentials in verified Keychain-backed storage; keep short-lived sessions in memory where practical. OTP stays transient; no OTP seed storage or automatic generation. Separate secrets by canonical NAS origin and account. Require trusted TLS; no ignore-certificate switch or credential-bearing URL. Do not forward credentials across origins.

Forget this Mac clears local stored credentials and current session and attempts appropriate logout. Explain that this does not prove server-side remembered-device revocation; document DSM's revocation path after verification.

## Feasibility gate and evidence
Adobe officially supports Lua export destinations and custom Export UI:
https://developer.adobe.com/lightroom-classic/
DSM login including OTP/remembered-device parameters:
https://global.download.synology.com/download/Document/Software/DeveloperGuide/Os/DSM/All/enu/DSM_Login_Web_API_Guide_enu.pdf
Synology Photos operations are not established here as a supported public contract. Inspect these implementation references and confirm with sanitized live observations:
https://github.com/N4S4/synology-api
https://github.com/zeichensatz/SynologyPhotosAPI
Photo StatLr is a feature reference, not code to copy without license review:
https://github.com/flingo64/PhotoStation-Upload-Lr-Plugin

Gate: a disposable image is uploaded, assigned to an actual manual album, and visible there in web/mobile; reconnect using remembered-device material succeeds; revocation triggers safe reauthentication. Record DSM/Photos/Classic/macOS versions and sanitized request/response shapes. No live test has run. User must enter secrets locally; local coding workers get only synthetic fixtures. Inspect album ownership/permissions and report unsupported cases instead of silently substituting folder uploads.

## Validation and release
Offline checks: first-login OTP challenge, successful enrollment, remembered reconnect, rejected/revoked device, session expiry, TLS failure, secret redaction, album pagination/duplicate names/access denied, indexing delay, timeout/ambiguous upload, membership-only retry, cancel and partial batch failure. Integration acceptance uses disposable user-selected assets and album; no production cleanup or deletion inferred.

Release requires plugin load/export in actual Classic on macOS, real album membership visible on mobile, secure-storage verification, remembered-device lifecycle, per-file failure reporting and install/uninstall guide. Record independently observed results separately from mocks and worker claims.

## Delivery and delegation
Canonical planning temporarily resides in kudama/forge. Intended standalone repository: kudama/app-lightroom-synology-photos (proposed name, not created). GitHub connector lacks repository creation; local gh authentication failed on 2026-10-25. Do not claim repository/bootstrap complete.

Follow docs/backlog.md and docs/work-orders.md. Local implementers return bounded proposals from exact-source manifests, without credentials, NAS access or GitHub writes. Forge owns auth/security decisions, integration review, applying changes and independent tests. Before dispatch record repository/revision/file hashes, executor, actual controller task ID and effective grants. No controller tool is exposed in this session; queued issues are not running assignments.

First wave: Forge validates protocol/SDK contracts; local implementer can propose offline skeleton against this brief. Later: secure auth, album adapter, reliable upload/membership, Export UI integration, acceptance/package. Keep blocked dependencies explicit.

## Status
2026-10-25: requirements captured; no plugin implementation, live NAS verification, standalone repository or local-agent execution is claimed. Next: establish source repository and verify protocol/credential contracts; dispatch one scoped local skeleton proposal after controller access/preflight.
