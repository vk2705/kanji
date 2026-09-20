import { useEffect, useState } from "react";
import { getMyContributions, setKanjiVisibility, setRowVisibility } from "../api";
import { displayChar } from "../utils";
import { t } from "../i18n";

function VisibilityToggle({ visibility, onToggle, lang, busy, error }) {
  const isPublic = visibility === "public";
  return (
    <span className="visibility-toggle-wrap">
      <button
        type="button"
        className={`visibility-btn ${isPublic ? "is-public" : ""}`}
        onClick={onToggle}
        disabled={busy}
      >
        {isPublic ? t(lang, "visibilityPublicLabel") : t(lang, "visibilityPrivateLabel")}
      </button>
      {error && <span className="status error visibility-toggle-error">{t(lang, "errorPrefix", error)}</span>}
    </span>
  );
}

export default function MyContributions({ lang, onSelectKanji, onBack }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [rowState, setRowState] = useState({}); // key -> { busy, error }

  function load() {
    getMyContributions().then(setData).catch((e) => setError(e.message));
  }

  useEffect(load, []);

  async function toggleKanji(row) {
    const key = `kanji:${row.id}`;
    const next = row.visibility === "public" ? "private" : "public";
    setRowState((s) => ({ ...s, [key]: { busy: true, error: null } }));
    try {
      await setKanjiVisibility(row.id, next);
      setRowState((s) => ({ ...s, [key]: { busy: false, error: null } }));
      load();
    } catch (e) {
      setRowState((s) => ({ ...s, [key]: { busy: false, error: e.message } }));
    }
  }

  async function toggleRow(table, row) {
    const key = `${table}:${row.id}`;
    const next = row.visibility === "public" ? "private" : "public";
    setRowState((s) => ({ ...s, [key]: { busy: true, error: null } }));
    try {
      await setRowVisibility(table, row.id, next);
      setRowState((s) => ({ ...s, [key]: { busy: false, error: null } }));
      load();
    } catch (e) {
      setRowState((s) => ({ ...s, [key]: { busy: false, error: e.message } }));
    }
  }

  if (error) {
    return (
      <div className="form-view">
        {onBack && <button className="back-btn" onClick={onBack}>{t(lang, "backBtn")}</button>}
        <div className="status error">{t(lang, "errorPrefix", error)}</div>
      </div>
    );
  }
  if (!data) return <div className="status">{t(lang, "loading")}</div>;

  const isEmpty = !data.kanji.length && !data.decompositions.length
    && !data.aliases.length && !data.stories.length;

  function rowLabel(row) {
    return displayChar(row.character) || row.keyword || row.kanji_id || row.id;
  }

  return (
    <div className="form-view">
      {onBack && <button className="back-btn" onClick={onBack}>{t(lang, "backBtn")}</button>}
      <h2>{t(lang, "myContributionsHeading")}</h2>

      {isEmpty && <p className="login-hint">{t(lang, "noContributions")}</p>}

      {data.kanji.length > 0 && (
        <div className="contrib-section">
          <h3>{t(lang, "contribKanjiHeading")}</h3>
          {data.kanji.map((row) => (
            <div key={row.id} className="contrib-row">
              <button className="contrib-row-link" onClick={() => onSelectKanji(row.id)}>
                {rowLabel(row)}
              </button>
              <VisibilityToggle
                visibility={row.visibility}
                onToggle={() => toggleKanji(row)}
                lang={lang}
                busy={rowState[`kanji:${row.id}`]?.busy}
                error={rowState[`kanji:${row.id}`]?.error}
              />
            </div>
          ))}
        </div>
      )}

      {data.decompositions.length > 0 && (
        <div className="contrib-section">
          <h3>{t(lang, "contribDecompositionsHeading")}</h3>
          {data.decompositions.map((row) => (
            <div key={row.id} className="contrib-row">
              <button className="contrib-row-link" onClick={() => onSelectKanji(row.kanji_id)}>
                {rowLabel(row)}
              </button>
              <VisibilityToggle
                visibility={row.visibility}
                onToggle={() => toggleRow("decompositions", row)}
                lang={lang}
                busy={rowState[`decompositions:${row.id}`]?.busy}
                error={rowState[`decompositions:${row.id}`]?.error}
              />
            </div>
          ))}
        </div>
      )}

      {data.aliases.length > 0 && (
        <div className="contrib-section">
          <h3>{t(lang, "contribAliasesHeading")}</h3>
          {data.aliases.map((row) => (
            <div key={row.id} className="contrib-row">
              <button className="contrib-row-link" onClick={() => onSelectKanji(row.kanji_id)}>
                {row.alias} — {rowLabel(row)}
              </button>
              <VisibilityToggle
                visibility={row.visibility}
                onToggle={() => toggleRow("aliases", row)}
                lang={lang}
                busy={rowState[`aliases:${row.id}`]?.busy}
                error={rowState[`aliases:${row.id}`]?.error}
              />
            </div>
          ))}
        </div>
      )}

      {data.stories.length > 0 && (
        <div className="contrib-section">
          <h3>{t(lang, "contribStoriesHeading")}</h3>
          {data.stories.map((row) => (
            <div key={row.id} className="contrib-row">
              <button className="contrib-row-link" onClick={() => onSelectKanji(row.kanji_id)}>
                {rowLabel(row)}
              </button>
              <VisibilityToggle
                visibility={row.visibility}
                onToggle={() => toggleRow("stories", row)}
                lang={lang}
                busy={rowState[`stories:${row.id}`]?.busy}
                error={rowState[`stories:${row.id}`]?.error}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
