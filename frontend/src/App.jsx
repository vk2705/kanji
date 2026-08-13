import { useEffect, useState } from "react";
import { searchByParts, searchByText, searchByChar, getMe, updatePreferences } from "./api";
import ResultsGrid from "./components/ResultsGrid";
import KanjiDetail from "./components/KanjiDetail";
import AuthBar from "./components/AuthBar";
import CreateKanji from "./components/CreateKanji";
import MyContributions from "./components/MyContributions";
import { t } from "./i18n";
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

export default function App() {
  const [tab, setTab] = useState(0);
  const [view, setView] = useState("search"); // "search" | "create" | "contributions"
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [user, setUser] = useState(null);
  const [uiLang, setUiLang] = useState(() => readLocal("ui_language", "en"));
  const [studyScript, setStudyScript] = useState(() => readLocal("study_script", ""));
  const [sources, setSources] = useState(() => new Set(SOURCE_SCOPES.map((s) => s.value)));

  const tt = (key, ...args) => t(uiLang, key, ...args);

  useEffect(() => {
    getMe()
      .then((me) => {
        if (me.authenticated) {
          setUser(me);
          // Account is the source of truth once logged in; falls back to whatever
          // was already showing (this device's localStorage value) if unset.
          if (me.ui_language) setUiLang(me.ui_language);
          setStudyScript(me.study_script || "");
        } else {
          setUser(null);
        }
      })
      .catch(() => setUser(null));
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
  useEffect(() => {
    if (user) return;
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

  const [parts, setParts] = useState(["", "", ""]);
  const [textQuery, setTextQuery] = useState("");
  const [charQuery, setCharQuery] = useState("");
  const [fallbackMsg, setFallbackMsg] = useState("");

  async function runSearch(fn) {
    setLoading(true);
    setResults(null);
    setSelectedId(null);
    setFallbackMsg("");
    try {
      await fn();
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  async function handlePartsSearch(e) {
    e.preventDefault();
    const filled = parts.filter((p) => p.trim());
    if (!filled.length) return;
    runSearch(async () => {
      const data = await searchByParts(filled, studyScript || null, activeSources);
      if (data.results.length === 0 && filled.length === 1) {
        const text = await searchByText(filled[0], studyScript || null, activeSources);
        setResults(text.results);
        if (text.results.length > 0) {
          setFallbackMsg(tt("fallbackMsg", filled[0]));
        }
      } else {
        setResults(data.results);
      }
    });
  }

  async function handleTextSearch(e) {
    e.preventDefault();
    if (!textQuery.trim()) return;
    runSearch(async () => {
      const data = await searchByText(textQuery, studyScript || null, activeSources);
      setResults(data.results);
    });
  }

  async function handleCharSearch(e) {
    e.preventDefault();
    if (!charQuery.trim()) return;
    runSearch(async () => {
      const data = await searchByChar(charQuery, studyScript || null, activeSources);
      setResults(data ? [data] : []);
    });
  }

  function handleTabChange(i) {
    setTab(i);
    setResults(null);
    setSelectedId(null);
    setFallbackMsg("");
  }

  function selectKanji(id) {
    setSelectedId(id);
    setView("search");
  }

  function openView(v) {
    setView(v);
    setSelectedId(null);
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
            onBack={() => setSelectedId(null)}
            user={user}
            lang={uiLang}
            sources={activeSources}
          />
        ) : view === "create" ? (
          <CreateKanji lang={uiLang} onDone={selectKanji} />
        ) : view === "contributions" ? (
          <MyContributions lang={uiLang} onSelectKanji={selectKanji} />
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

            <div className="tabs">
              {TABS.map((label, i) => (
                <button
                  key={label}
                  className={`tab ${tab === i ? "tab-active" : ""}`}
                  onClick={() => handleTabChange(i)}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="search-panel">
              {tab === 0 && (
                <form onSubmit={handlePartsSearch} className="search-form">
                  <p className="search-hint">{tt("partsHint")}</p>
                  <div className="parts-inputs">
                    {parts.map((p, i) => (
                      <input
                        key={i}
                        className="input"
                        placeholder={tt("partsPlaceholder", i + 1)}
                        value={p}
                        onChange={(e) => {
                          const next = [...parts];
                          next[i] = e.target.value;
                          setParts(next);
                        }}
                      />
                    ))}
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
                    value={charQuery}
                    onChange={(e) => setCharQuery(e.target.value)}
                    maxLength={2}
                  />
                  <button className="btn-primary" type="submit">{tt("searchBtn")}</button>
                </form>
              )}
            </div>

            {fallbackMsg && (
              <p className="fallback-msg">{fallbackMsg}</p>
            )}
            <ResultsGrid
              results={results}
              onSelect={selectKanji}
              loading={loading}
              lang={uiLang}
            />
          </>
        )}
      </main>
    </div>
  );
}
