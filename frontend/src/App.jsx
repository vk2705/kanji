import { useEffect, useState } from "react";
import { searchByParts, searchByText, searchByChar, getMe } from "./api";
import ResultsGrid from "./components/ResultsGrid";
import KanjiDetail from "./components/KanjiDetail";
import AuthBar from "./components/AuthBar";
import "./App.css";

const TABS = ["By Parts", "By Text", "By Character"];

export default function App() {
  const [tab, setTab] = useState(0);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [user, setUser] = useState(null);

  useEffect(() => {
    getMe()
      .then((me) => setUser(me.authenticated ? me : null))
      .catch(() => setUser(null));
  }, []);

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
      const data = await searchByParts(filled);
      if (data.results.length === 0 && filled.length === 1) {
        const text = await searchByText(filled[0]);
        setResults(text.results);
        if (text.results.length > 0) {
          setFallbackMsg(`No kanji use "${filled[0]}" as a primitive. Showing keyword matches instead:`);
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
      const data = await searchByText(textQuery);
      setResults(data.results);
    });
  }

  async function handleCharSearch(e) {
    e.preventDefault();
    if (!charQuery.trim()) return;
    runSearch(async () => {
      const data = await searchByChar(charQuery);
      setResults(data ? [data] : []);
    });
  }

  function handleTabChange(i) {
    setTab(i);
    setResults(null);
    setSelectedId(null);
    setFallbackMsg("");
  }

  return (
    <div className="app">
      <header className="app-header">
        <AuthBar user={user} setUser={setUser} />
        <h1>RTK Kanji Search</h1>
        <p className="subtitle">Search kanji by their primitive elements</p>
      </header>

      <main className="app-main">
        {selectedId ? (
          <KanjiDetail
            kanjiId={selectedId}
            onSelectPart={setSelectedId}
            onBack={() => setSelectedId(null)}
          />
        ) : (
          <>
            <div className="tabs">
              {TABS.map((t, i) => (
                <button
                  key={t}
                  className={`tab ${tab === i ? "tab-active" : ""}`}
                  onClick={() => handleTabChange(i)}
                >
                  {t}
                </button>
              ))}
            </div>

            <div className="search-panel">
              {tab === 0 && (
                <form onSubmit={handlePartsSearch} className="search-form">
                  <p className="search-hint">
                    Enter 1–3 RTK primitive names (e.g. <em>sun</em>, <em>mouth</em>, <em>needle</em>)
                  </p>
                  <div className="parts-inputs">
                    {parts.map((p, i) => (
                      <input
                        key={i}
                        className="input"
                        placeholder={`Primitive ${i + 1}`}
                        value={p}
                        onChange={(e) => {
                          const next = [...parts];
                          next[i] = e.target.value;
                          setParts(next);
                        }}
                      />
                    ))}
                  </div>
                  <button className="btn-primary" type="submit">Search</button>
                </form>
              )}

              {tab === 1 && (
                <form onSubmit={handleTextSearch} className="search-form">
                  <p className="search-hint">
                    Search by any part of a kanji keyword or alias (e.g. <em>brig</em> → bright)
                  </p>
                  <input
                    className="input"
                    placeholder="Type to search…"
                    value={textQuery}
                    onChange={(e) => setTextQuery(e.target.value)}
                  />
                  <button className="btn-primary" type="submit">Search</button>
                </form>
              )}

              {tab === 2 && (
                <form onSubmit={handleCharSearch} className="search-form">
                  <p className="search-hint">
                    Paste a kanji character to look it up (e.g. <em>明</em>)
                  </p>
                  <input
                    className="input input-large"
                    placeholder="paste kanji here…"
                    value={charQuery}
                    onChange={(e) => setCharQuery(e.target.value)}
                    maxLength={2}
                  />
                  <button className="btn-primary" type="submit">Search</button>
                </form>
              )}
            </div>

            {fallbackMsg && (
              <p className="fallback-msg">{fallbackMsg}</p>
            )}
            <ResultsGrid
              results={results}
              onSelect={setSelectedId}
              loading={loading}
            />
          </>
        )}
      </main>
    </div>
  );
}
