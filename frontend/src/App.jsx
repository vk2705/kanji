import { useEffect, useRef, useState } from "react";
import { searchByParts, searchByText, searchByChar, getMe, updatePreferences, recordPageView } from "./api";
import ResultsGrid from "./components/ResultsGrid";
import KanjiDetail from "./components/KanjiDetail";
import AuthBar from "./components/AuthBar";
import AboutPage from "./components/AboutPage";
import CreateKanji from "./components/CreateKanji";
import MyContributions from "./components/MyContributions";
import AutocompleteInput from "./components/AutocompleteInput";
import { t } from "./i18n";
import { stateToParams, paramsToState, paramsToUrl } from "./urlState";
import "./App.css";

const STUDY_SCRIPTS = [
  { value: "", labelKey: "studyAll" },
  { value: "ja-kanji", labelKey: "studyJapanese" },
  { value: "zh-Hans", labelKey: "studyChineseSimplified" },
  { value: "zh-Hant", labelKey: "studyChineseTraditional" },
];

// Mirrors backend SOURCE_SCOPES (database.py) — which contributors' data to search
// within. "mine" only makes sense while logged in; it's dropped from the active set
// (see the effect below) rather than left selectable-but-inert when logged out.
const SOURCE_SCOPES = [
  { value: "system", labelKey: "sourceSystem" },
  { value: "community", labelKey: "sourceCommunity" },
  { value: "mine", labelKey: "sourceMine" },
];

function readLocal(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

function writeLocal(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // ignore (private browsing / storage disabled)
  }
}

// Parsed once, outside the component, so the very first render (before any effect
// runs) already reflects a shared/back-navigated URL instead of flashing the default
// empty state first.
const initialUrlState = paramsToState(window.location.search);

export default function App() {
  const [tab, setTab] = useState(initialUrlState.tab ?? 0);
  const [view, setView] = useState(initialUrlState.view || "search"); // "search" | "create" | "contributions" | "about"
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const searchController = useRef(null);
  const resultsRef = useRef(null);
  const [selectedId, setSelectedId] = useState(initialUrlState.selectedId || null);
  const [detailStack, setDetailStack] = useState([]);
  const [user, setUser] = useState(null);
  const [authResolved, setAuthResolved] = useState(false);
  const [uiLang, setUiLang] = useState(() => readLocal("ui_language", "en"));
  const [studyScript, setStudyScript] = useState(() => initialUrlState.studyScript || readLocal("study_script", ""));
  const [sources, setSources] = useState(
    () => new Set(initialUrlState.sources || SOURCE_SCOPES.map((s) => s.value))
  );
  // True while we're applying a URL (initial load or Back/Forward) rather than
  // reacting to the user's own actions — suppresses the effect that would otherwise
  // push a *new* history entry in response to state changes we just pulled *from*
  // history, which would turn Back into a no-op loop.
  const applyingUrlRef = useRef(true);

  const tt = (key, ...args) => t(uiLang, key, ...args);

  // index.html hardcodes lang="en"; keep the document's declared language in sync
  // with the active UI language so screen readers pronounce Russian text correctly.
  useEffect(() => {
    document.documentElement.lang = uiLang;
  }, [uiLang]);

  useEffect(() => {
    getMe()
      .then((me) => {
        if (me.authenticated) {
          setUser(me);
          // Account is the source of truth once logged in; falls back to whatever
          // was already showing (this device's localStorage value) if unset. A
          // study-language carried in a shared/back-navigated URL wins over the
          // account default, though — the whole point of sharing a link is that the
          // recipient sees what was shared, not their own saved preference.
          if (!initialUrlState.studyScript) {
            if (me.ui_language) setUiLang(me.ui_language);
            setStudyScript(me.study_script || "");
          } else if (me.ui_language) {
            setUiLang(me.ui_language);
          }
        } else {
          setUser(null);
        }
      })
      .catch(() => setUser(null))
      .finally(() => setAuthResolved(true));
  }, []);

  useEffect(() => {
    recordPageView();
    return () => searchController.current?.abort();
  }, []);

  // Pushes a new history entry reflecting the given state, unless we're currently
  // applying a URL ourselves (initial load or a Back/Forward-triggered restore) —
  // otherwise restoring state from `popstate` would immediately re-push it, turning
  // Back into a no-op.
  function pushUrl(nextState) {
    if (applyingUrlRef.current) return;
    const url = paramsToUrl(stateToParams(nextState));
    if (url !== window.location.pathname + window.location.search) {
      window.history.pushState({ ...nextState, __kanjiNav: true }, "", url);
    }
  }

  function replaceUrl(nextState) {
    const url = paramsToUrl(stateToParams(nextState));
    window.history.replaceState({ ...nextState, __kanjiNav: true }, "", url);
  }

  // Runs the search (or loads the detail view) implied by whatever URL we just
  // landed on — the initial page load, and any later Back/Forward navigation
  // (see the popstate listener below).
  function applyUrlState(urlState) {
    applyingUrlRef.current = true;
    setView(urlState.view || "search");
    if (urlState.view && urlState.view !== "search") {
      applyingUrlRef.current = false;
      return;
    }
    setTab(urlState.tab ?? 0);
    setSelectedId(urlState.selectedId || null);
    setStudyScript(urlState.studyScript || "");
    if (urlState.sources) setSources(new Set(urlState.sources));
    setResults(null);
    setFallbackMsg("");
    setSearchError("");

    const script = urlState.studyScript || "";
    const srcs = urlState.sources || null;

    if (urlState.tab === 1) {
      setTextQuery(urlState.q || "");
      setCharQuery("");
      setParts(["", "", ""]);
      if (urlState.q) runTextSearch(urlState.q, script, srcs);
    } else if (urlState.tab === 2) {
      setCharQuery(urlState.q || "");
      setTextQuery("");
      setParts(["", "", ""]);
      if (urlState.q) runCharSearch(urlState.q, script, srcs);
    } else {
      const filled = urlState.q ? urlState.q.split(",") : [];
      setParts([...filled, "", "", ""].slice(0, Math.max(3, filled.length)));
      setTextQuery("");
      setCharQuery("");
      if (urlState.searchDepth) setSearchDepth(urlState.searchDepth);
      if (filled.length) runPartsSearch(filled, script, srcs, urlState.searchDepth || 1);
    }
    // Cleared on the next tick, after the state updates above have been applied —
    // the effects that would otherwise treat these as fresh user actions and push a
    // duplicate history entry run after this synchronous block.
    setTimeout(() => {
      applyingUrlRef.current = false;
    }, 0);
  }

  // Restore state on Back/Forward. The initial load is handled by a separate effect
  // below (it also needs to kick off the initial search, which this only does for
  // later navigations to keep the two paths symmetric).
  useEffect(() => {
    function onPopState() {
      applyUrlState(paramsToState(window.location.search));
    }
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  // Kick off whatever the initial URL asked for (a search, or a directly-linked
  // kanji) once on mount. Doesn't wait for auth to resolve — an anonymous view of a
  // shared link should work the same as a logged-in one, modulo "mine" (handled by
  // the existing sources-cleanup effect above).
  useEffect(() => {
    if (initialUrlState.view && initialUrlState.view !== "search") {
      applyingUrlRef.current = false;
      return;
    }
    if (initialUrlState.hasSearch && initialUrlState.tab !== undefined) {
      const script = initialUrlState.studyScript || "";
      const srcs = initialUrlState.sources || null;
      if (initialUrlState.tab === 1 && initialUrlState.q) {
        runTextSearch(initialUrlState.q, script, srcs);
      } else if (initialUrlState.tab === 2 && initialUrlState.q) {
        runCharSearch(initialUrlState.q, script, srcs);
      } else if (initialUrlState.tab === 0 && initialUrlState.q) {
        runPartsSearch(initialUrlState.q.split(","), script, srcs, initialUrlState.searchDepth || 1);
      }
    }
    applyingUrlRef.current = false;
  }, []);

  function changeUiLang(lang) {
    setUiLang(lang);
    writeLocal("ui_language", lang);
    if (user) updatePreferences({ ui_language: lang }).catch(() => {});
  }

  function changeStudyScript(script) {
    setStudyScript(script);
    writeLocal("study_script", script);
    if (user) updatePreferences({ study_script: script || null }).catch(() => {});
  }

  // Session-only preference (not persisted to the account, unlike ui_language/study_script).
  function toggleSource(value) {
    setSources((prev) => {
      const next = new Set(prev);
      if (next.has(value)) {
        next.delete(value);
      } else {
        next.add(value);
      }
      return next;
    });
  }

  // "mine" is meaningless while logged out; drop it so an anonymous session never
  // silently searches an empty scope after a logged-in tab logs out mid-session.
  // Gated on authResolved so a returning logged-in user doesn't lose "mine" from
  // the default set during the brief window before /auth/me responds (user is
  // still null then, indistinguishable from actually-logged-out without this flag).
  useEffect(() => {
    if (!authResolved || user) return;
    setSources((prev) => {
      if (!prev.has("mine")) return prev;
      const next = new Set(prev);
      next.delete("mine");
      return next.size ? next : new Set(SOURCE_SCOPES.map((s) => s.value));
    });
  }, [user]);

  // null (not an explicit full list) when every scope is active, so the API call
  // matches its own "no restriction" default instead of sending a redundant filter.
  const activeSources = sources.size >= SOURCE_SCOPES.length ? null : [...sources];

  const initialParts = initialUrlState.tab === 0 && initialUrlState.q ? initialUrlState.q.split(",") : [];
  const [parts, setParts] = useState(() => {
    const p = [...initialParts, "", "", ""].slice(0, Math.max(3, initialParts.length));
    return p;
  });
  const [textQuery, setTextQuery] = useState(() => (initialUrlState.tab === 1 ? initialUrlState.q || "" : ""));
  const [charQuery, setCharQuery] = useState(() => (initialUrlState.tab === 2 ? initialUrlState.q || "" : ""));
  const [fallbackMsg, setFallbackMsg] = useState("");
  // How many decomposition levels parts-search recurses through — 1 (direct match
  // only) is the historical default; the backend can go deeper but a common primitive
  // matches a large fraction of the dataset at high depth, so this stays an explicit
  // user choice rather than a fixed default (see search_by_parts's docstring).
  const [searchDepth, setSearchDepth] = useState(initialUrlState.searchDepth || 1);

  async function runSearch(fn) {
    searchController.current?.abort();
    const controller = new AbortController();
    searchController.current = controller;
    setLoading(true);
    setFallbackMsg("");
    setSearchError("");
    // On a small screen the search form can fill the whole viewport, so the results
    // (appearing below it) are invisible until the user scrolls — nothing on the
    // form itself changes when the search starts, so it looks like the button did
    // nothing. Scroll the results area into view right away (not after the response
    // arrives) so the loading indicator, and then the results, are visible immediately.
    // Deferred to the next frame: setLoading(true) above hasn't been committed to the
    // DOM yet at this point (React batches state updates), so scrolling synchronously
    // here would measure the *pre-loading* layout — often the same empty state as
    // before the click, which made this look like it did nothing on a real device.
    requestAnimationFrame(() => {
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    try {
      await fn(controller.signal);
    } catch (error) {
      if (error.name !== "AbortError") {
        setSearchError(error.message || String(error));
      }
    } finally {
      if (searchController.current === controller) {
        searchController.current = null;
        setLoading(false);
      }
    }
  }

  function canSearchSelectedSources() {
    if (sources.size > 0) return true;
    setSearchError(tt("selectSourceError"));
    return false;
  }

  function runPartsSearch(filled, script, srcs, depth) {
    runSearch(async (signal) => {
      const data = await searchByParts(filled, script || null, srcs, depth, signal);
      if (data.results.length === 0 && filled.length === 1) {
        const text = await searchByText(filled[0], script || null, srcs, signal);
        setResults(text.results);
        if (text.results.length > 0) {
          setFallbackMsg(tt("fallbackMsg", filled[0]));
        }
      } else {
        setResults(data.results);
      }
    });
  }

  function runTextSearch(query, script, srcs) {
    runSearch(async (signal) => {
      const data = await searchByText(query, script || null, srcs, signal);
      setResults(data.results);
    });
  }

  function runCharSearch(query, script, srcs) {
    runSearch(async (signal) => {
      const data = await searchByChar(query, script || null, srcs, signal);
      setResults(data ? [data] : []);
    });
  }

  async function handlePartsSearch(e) {
    e.preventDefault();
    const filled = parts.filter((p) => p.trim());
    if (!filled.length || !canSearchSelectedSources()) return;
    setSelectedId(null);
    pushUrl({ tab: 0, parts, textQuery, charQuery, searchDepth, studyScript, sources: [...sources], selectedId: null, view: "search" });
    runPartsSearch(filled, studyScript, activeSources, searchDepth);
  }

  async function handleTextSearch(e) {
    e.preventDefault();
    if (!textQuery.trim() || !canSearchSelectedSources()) return;
    setSelectedId(null);
    pushUrl({ tab: 1, parts, textQuery, charQuery, searchDepth, studyScript, sources: [...sources], selectedId: null, view: "search" });
    runTextSearch(textQuery, studyScript, activeSources);
  }

  async function handleCharSearch(e) {
    e.preventDefault();
    if (!charQuery.trim() || !canSearchSelectedSources()) return;
    setSelectedId(null);
    pushUrl({ tab: 2, parts, textQuery, charQuery, searchDepth, studyScript, sources: [...sources], selectedId: null, view: "search" });
    runCharSearch(charQuery, studyScript, activeSources);
  }

  function handleTabChange(i) {
    setTab(i);
    setResults(null);
    setSelectedId(null);
    setFallbackMsg("");
    setSearchError("");
  }

  function selectKanji(id) {
    if (selectedId && selectedId !== id) {
      setDetailStack((stack) => [...stack, selectedId]);
    }
    setSelectedId(id);
    setView("search");
    pushUrl({ tab, parts, textQuery, charQuery, searchDepth, studyScript, sources: [...sources], selectedId: id, view: "search" });
  }

  function openView(v) {
    setView(v);
    setSelectedId(null);
    pushUrl({ view: v });
  }

  // Each detail opened from another detail is retained explicitly, so Back follows
  // the decomposition trail before returning to the still-preserved search results.
  function goBackToSearch() {
    const previousId = detailStack.at(-1);
    if (previousId) {
      setDetailStack((stack) => stack.slice(0, -1));
      setSelectedId(previousId);
      replaceUrl({ tab, parts, textQuery, charQuery, searchDepth, studyScript, sources: [...sources], selectedId: previousId, view: "search" });
      return;
    }
    setSelectedId(null);
    setView("search");
    replaceUrl({ tab, parts, textQuery, charQuery, searchDepth, studyScript, sources: [...sources], selectedId: null, view: "search" });
  }

  function goHome() {
    setTab(0);
    setParts(["", "", ""]);
    setTextQuery("");
    setCharQuery("");
    setSearchDepth(1);
    setResults(null);
    setFallbackMsg("");
    setSearchError("");
    setDetailStack([]);
    setSelectedId(null);
    setView("search");
    replaceUrl({ tab: 0, parts: ["", "", ""], textQuery: "", charQuery: "", searchDepth: 1, studyScript, sources: [...sources], selectedId: null, view: "search" });
  }

  const TABS = [tt("tabParts"), tt("tabText"), tt("tabChar")];

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-controls">
          <div className="lang-toggle">
            {["en", "ru"].map((l) => (
              <button
                key={l}
                className={`lang-btn ${uiLang === l ? "lang-btn-active" : ""}`}
                onClick={() => changeUiLang(l)}
                aria-pressed={uiLang === l}
              >
                {l.toUpperCase()}
              </button>
            ))}
          </div>
          {user && (
            <>
              <button className="header-nav-btn" onClick={() => openView("create")}>
                {tt("newKanjiBtn")}
              </button>
              <button className="header-nav-btn" onClick={() => openView("contributions")}>
                {tt("myContributionsBtn")}
              </button>
            </>
          )}
          <button className="header-nav-btn" onClick={() => openView("about")}>
            {tt("aboutLinkBtn")}
          </button>
          <AuthBar
            user={user}
            setUser={setUser}
            lang={uiLang}
            uiLang={uiLang}
            studyScript={studyScript || null}
          />
        </div>
        <h1>{tt("appTitle")}</h1>
        <p className="subtitle">{tt("appSubtitle")}</p>
      </header>

      <main className="app-main">
        {selectedId ? (
          <KanjiDetail
            kanjiId={selectedId}
            onSelectPart={selectKanji}
            onBack={goBackToSearch}
            onHome={goHome}
            user={user}
            lang={uiLang}
            sources={activeSources}
          />
        ) : view === "create" ? (
          <CreateKanji lang={uiLang} onDone={selectKanji} onBack={goBackToSearch} onHome={goHome} />
        ) : view === "contributions" ? (
          <MyContributions lang={uiLang} onSelectKanji={selectKanji} onBack={goBackToSearch} onHome={goHome} />
        ) : view === "about" ? (
          <AboutPage lang={uiLang} onBack={goBackToSearch} onHome={goHome} />
        ) : (
          <>
            <div className="study-language">
              <label htmlFor="study-script-select">{tt("studyLanguageLabel")}</label>
              <select
                id="study-script-select"
                className="input"
                value={studyScript}
                onChange={(e) => changeStudyScript(e.target.value)}
              >
                {STUDY_SCRIPTS.map((s) => (
                  <option key={s.value} value={s.value}>{tt(s.labelKey)}</option>
                ))}
              </select>
            </div>

            <fieldset className="source-filter">
              <legend>{tt("sourcesLabel")}</legend>
              {SOURCE_SCOPES.filter((s) => user || s.value !== "mine").map((s) => (
                <label key={s.value} className="source-filter-option">
                  <input
                    type="checkbox"
                    checked={sources.has(s.value)}
                    onChange={() => toggleSource(s.value)}
                  />
                  {tt(s.labelKey)}
                </label>
              ))}
            </fieldset>

            <div className="tabs" role="tablist" aria-label={tt("searchModeLabel")}>
              {TABS.map((label, i) => (
                <button
                  key={label}
                  type="button"
                  role="tab"
                  aria-selected={tab === i}
                  aria-controls={`search-panel-${i}`}
                  className={`tab ${tab === i ? "tab-active" : ""}`}
                  onClick={() => handleTabChange(i)}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="search-panel" id={`search-panel-${tab}`} role="tabpanel">
              {tab === 0 && (
                <form onSubmit={handlePartsSearch} className="search-form">
                  <p className="search-hint">{tt("partsHint")}</p>
                  <div className="parts-inputs">
                    {parts.map((p, i) => (
                      <AutocompleteInput
                        key={i}
                        className="input"
                        placeholder={tt("partsPlaceholder", i + 1)}
                        aria-label={tt("partsPlaceholder", i + 1)}
                        value={p}
                        script={studyScript || null}
                        onChange={(v) => {
                          const next = [...parts];
                          next[i] = v;
                          setParts(next);
                        }}
                      />
                    ))}
                  </div>
                  <div className="search-depth">
                    <label htmlFor="search-depth-select">{tt("searchDepthLabel")}</label>
                    <select
                      id="search-depth-select"
                      className="input"
                      value={searchDepth}
                      onChange={(e) => setSearchDepth(Number(e.target.value))}
                    >
                      {[1, 2, 3, 4, 5].map((d) => (
                        <option key={d} value={d}>{tt(`searchDepth${d}`)}</option>
                      ))}
                    </select>
                    <p className="search-depth-hint">{tt("searchDepthHint")}</p>
                  </div>
                  <button className="btn-primary" type="submit">{tt("searchBtn")}</button>
                </form>
              )}

              {tab === 1 && (
                <form onSubmit={handleTextSearch} className="search-form">
                  <p className="search-hint">{tt("textHint")}</p>
                  <input
                    className="input"
                    placeholder={tt("textPlaceholder")}
                    aria-label={tt("textHint")}
                    value={textQuery}
                    onChange={(e) => setTextQuery(e.target.value)}
                  />
                  <button className="btn-primary" type="submit">{tt("searchBtn")}</button>
                </form>
              )}

              {tab === 2 && (
                <form onSubmit={handleCharSearch} className="search-form">
                  <p className="search-hint">{tt("charHint")}</p>
                  <input
                    className="input input-large"
                    placeholder={tt("charPlaceholder")}
                    aria-label={tt("charHint")}
                    value={charQuery}
                    onChange={(e) => setCharQuery(e.target.value)}
                    maxLength={2}
                  />
                  <button className="btn-primary" type="submit">{tt("searchBtn")}</button>
                </form>
              )}
            </div>

            <div ref={resultsRef}>
              {fallbackMsg && (
                <p className="fallback-msg">{fallbackMsg}</p>
              )}
              {searchError && (
                <div className="status error" role="alert">{tt("errorPrefix", searchError)}</div>
              )}
              <ResultsGrid
                results={results}
                onSelect={selectKanji}
                loading={loading}
                lang={uiLang}
              />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
