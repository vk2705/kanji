package help.alteon.kanji

import android.app.Application

/** No shared state needed yet — exists so MainActivity has an explicit android:name
 * to attach to rather than the implicit default Application, in case a future feature
 * (e.g. a WorkManager-based background sync) needs one. */
class KanjiApp : Application()
