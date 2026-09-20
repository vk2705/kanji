plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "help.alteon.kanji"
    compileSdk = 34

    defaultConfig {
        applicationId = "help.alteon.kanji"
        // 26 (Android 8.0) rather than lower — lets the launcher icon be a plain
        // adaptive-icon (vector foreground + solid background) with no legacy PNG
        // fallback needed, and covers the vast majority of active devices anyway.
        minSdk = 26
        targetSdk = 34
        versionCode = 2
        versionName = "1.1"

        // The app is a thin WebView shell around the existing React web app
        // (frontend/, deployed per CLAUDE.md's Deployment section) rather than
        // a from-scratch native rewrite — see android/README.md for why.
        //
        // Default APP_URL (used by any build type that doesn't override it,
        // i.e. `release`) — as of 2026-09-20 this is the new prod host
        // (kanji.alteon.help, on the Oracle Cloud VM). The old EC2 box
        // (srv.alteon.help) is now dev/legacy — see the `legacy` build type
        // below to point a build at it instead.
        buildConfigField("String", "APP_URL", "\"https://kanji.alteon.help/kanji/\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
        debug {
            // Point a debug build at a local dev server (`npm run dev` in frontend/,
            // per CLAUDE.md) reachable from the emulator via its host-loopback alias.
            buildConfigField("String", "APP_URL", "\"http://10.0.2.2:5173/\"")
        }
        create("legacy") {
            // Points at the old EC2 box (srv.alteon.help), now dev/legacy, instead
            // of the new prod host — for testing against that server specifically.
            // Otherwise identical to `release` (unminified, same proguard rules).
            // Suffixed applicationId so it can be installed alongside a release
            // build on the same device without one overwriting the other.
            initWith(getByName("release"))
            applicationIdSuffix = ".legacy"
            buildConfigField("String", "APP_URL", "\"https://srv.alteon.help/kanji/\"")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        buildConfig = true
        viewBinding = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("com.google.android.material:material:1.12.0")
}
