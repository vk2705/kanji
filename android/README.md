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

- **Google Sign-In will likely not work inside the WebView.** Google
  actively blocks its OAuth flow inside generic embedded WebViews
  (`disallowed_useragent`) as an anti-phishing measure. `MainActivity`
  already routes any off-host navigation (which includes Google's
  account-chooser redirect) out to the system browser as a partial
  mitigation, but the Google Identity Services JS SDK itself
  (`AuthBar.jsx`) may still fail before that redirect ever happens. Local
  username/password auth is unaffected. Fixing this properly means Chrome
  Custom Tabs plus a real OAuth redirect flow — a bigger change than this
  first pass, and out of scope until someone hits it in practice.
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
