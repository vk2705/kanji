# RTK Kanji — Android app

A thin native shell that loads the existing web app (`frontend/`, deployed
per the root `CLAUDE.md`'s Deployment section) in a `WebView`, rather than a
from-scratch native rewrite. `CLAUDE.md`'s "Known limitations" section
anticipated a native REST client with token auth someday — this is a
smaller, faster first step that ships the whole app (search, contributions,
auth, everything) with no backend changes at all.

## What it does

- Loads `https://srv.alteon.help/kanji/` (release build) — see
  `BuildConfig.APP_URL` in `app/build.gradle.kts`.
- Persists cookies across app restarts (`CookieManager`), so the existing
  cookie-session auth (`backend/auth.py`) just works, same as a browser tab.
- Supports the image-upload feature (`ImageUpload` in `KanjiDetail.jsx`) via
  `onShowFileChooser`, which a bare WebView doesn't handle for you.
- Back button navigates the WebView's own history before exiting the app.
- Pull-to-refresh, a top loading bar, and a simple offline/retry screen.
- External links (anything not on the app's own host) open in a real
  browser instead of inside the WebView.

## Building

Needs an Android SDK (`ANDROID_HOME`/`ANDROID_SDK_ROOT` set, or a
`local.properties` with `sdk.dir=...`) — Android Studio sets this up
automatically; from a bare CLI, install the `platform-tools`,
`platforms;android-34`, and `build-tools;34.0.0` packages via `sdkmanager`.

```bash
cd android
./gradlew :app:assembleDebug     # debug/ — points at a local dev server, see below
./gradlew :app:assembleRelease   # release/ — points at the live deployed site, unsigned
```

The release APK is unsigned (no signing config is checked into this repo,
deliberately — that's a secret). Sign it with your own keystore before
distributing:

```bash
apksigner sign --ks your-release-key.jks app/build/outputs/apk/release/app-release-unsigned.apk
```

## Running against a local dev backend

The **debug** build variant points `APP_URL` at `http://10.0.2.2:5173/` —
the standard emulator alias for the host machine's loopback — instead of the
production URL, so `./gradlew :app:installDebug` on an emulator talks to
whatever's running via `cd frontend && npm run dev` (and, for it to actually
work end-to-end, `cd backend && python3 -m uvicorn main:app --reload --port
8000` too) on the machine hosting the emulator. A physical device instead of
an emulator won't resolve `10.0.2.2` — point `APP_URL` at your machine's LAN
IP instead for that case.

## Known limitations

- **Google Sign-In doesn't work inside the WebView, and is hidden there
  rather than fixed (owner-reported 2026-09-04: a black screen on tapping
  it).** Google actively blocks its OAuth flow inside generic embedded
  WebViews (`disallowed_useragent`) as an anti-phishing measure — the
  Identity Services JS SDK's button/prompt (`AuthBar.jsx`) renders a
  blank/black frame instead of a real sign-in UI when it detects it's
  inside one. `MainActivity` appends a `KanjiAndroidApp` marker to the
  WebView's user agent string; `AuthBar.jsx` checks for that marker and
  skips loading the Google SDK entirely in that context, showing a short
  note pointing at username/password auth (unaffected) or the website
  instead. This avoids the broken/blank experience but doesn't restore
  Google Sign-In inside the app — fixing that properly still means Chrome
  Custom Tabs plus a real OAuth redirect flow, a bigger change than this
  mitigation, and still not done.
- No app icon variety (adaptive icon only, `minSdk = 26`) — devices on
  Android 7.1 and older aren't supported. Given this is a wrapper around a
  web app with no other native-code dependency on API level, lowering
  `minSdk` back to 24 just means adding a legacy PNG launcher icon
  fallback; nothing else changes.
- No offline caching of the web app itself — the offline screen is a
  network-error fallback with a retry button, not a real offline mode.
  Given the app talks to a live multi-user SQLite backend for every search,
  a meaningful offline mode would need its own design (e.g. a local cache
  of public data), not just a service-worker-style asset cache.
- Not published anywhere (no Play Store listing, no CI build pipeline) —
  this only builds locally / from source for now.

## Pre-built APK

`android/releases/rtk-kanji-latest.apk` is a **release**-variant build
(points at `https://srv.alteon.help/kanji/`, the live production site),
self-signed with a throwaway key generated just for this — not the app's
"real" signing identity, since none exists yet (see the Building section
above: no signing config is checked in, deliberately). This means:
- It installs fine via sideloading ("install from unknown sources"), same
  as any unsigned/self-signed APK.
- A future release signed with a *different* key (e.g. once there's a real
  keystore, or a Play Store listing) will be treated by Android as a
  different app for update purposes — you'd need to uninstall this one
  first, not upgrade over it.
- No auto-update mechanism; re-download this file to get a newer build.
  Rebuild it yourself with `./gradlew :app:assembleRelease` (see Building
  above) any time the web app changes, sign it with your own key via
  `apksigner`, and replace this file if you want the repo's copy to stay
  current.
- Direct download link (raw file, served via GitHub):
  `https://github.com/vk2705/kanji/raw/master/android/releases/rtk-kanji-latest.apk`

## Publishing to Google Play (not done yet)

What's ready:
- `applicationId = "help.alteon.kanji"`, `versionCode`/`versionName` are set
  and don't need to change for a first submission.
- A privacy policy page, required by Play Console's app-content
  questionnaire, is live at `https://srv.alteon.help/kanji/privacy.html`
  (source: `frontend/public/privacy.html`, EN/RU toggle) — paste that URL
  into the Play Console listing form.

What the app owner has to do (none of this is scriptable — it's tied to a
personal Google identity and a one-time $25 fee):
1. Register a Google Play Console developer account at
   [play.google.com/console](https://play.google.com/console).
2. Create the app listing: title, short/full description, category, content
   rating questionnaire, screenshots (phone screenshots are required — a
   real device or emulator capture of the app's search/detail screens), a
   feature graphic (1024×500), and the privacy policy URL above.
3. Build a **signed** `.aab` (Play requires an Android App Bundle, not an
   APK, for new apps) — either with your own keystore (`./gradlew
   :app:bundleRelease`, then sign it, same idea as the `apksigner` step
   above but producing an `.aab`) or, the currently Google-recommended path,
   let **Play App Signing** generate and hold the signing key for you after
   your first upload (upload an app-signing-key-less "upload key"-signed
   bundle; Play re-signs it with the key it manages). Either way, back up
   whatever key you generate yourself — losing it means you can never
   update the app under the same listing again.
4. Submit for review. First-time app review can take a few days; Google may
   ask for more information (especially around the login/account system and
   what data it collects — the privacy policy page above is written to
   answer that).

Known blocker specific to this app: **Google Sign-In inside the WebView**
(see "Known limitations" above) — worth testing explicitly during Play's
review, since Play's automated checks sometimes flag broken OAuth flows.
Local username/password login is unaffected either way.
