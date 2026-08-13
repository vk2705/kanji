import { useEffect, useState } from "react";
import { getMyContributions, setKanjiVisibility, setRowVisibility } from "../api";
import { displayChar } from "../utils";
import { t } from "../i18n";

function VisibilityToggle({ visibility, onToggle, lang }) {
  const isPublic = visibility === "public";
  return (
    <button
      type="button"
      className={`visibility-btn ${isPublic ? "is-public" : ""}`}
      onClick={onToggle}
    >
      {isPublic ? t(lang, "visibilityPublicLabel") : t(lang, "visibilityPrivateLabel")}
    </button>
  );
}

export default function MyContributions({ lang, onSelectKanji }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  function load() {
    getMyContributions().then(setData).catch((e) => setError(e.message));
  }

  useEffect(load, []);

  async function toggleKanji(row) {
    const next = row.visibility === "public" ? "private" : "public";
    await setKanjiVisibility(row.id, next);
    load();
  }

  async function toggleRow(table, row) {
    const next = row.visibility === "public" ? "private" : "public";
    await setRowVisibility(table, row.id, next);
    load();
  }

  if (error) return <div className="status error">{t(lang, "errorPrefix", error)}</div>;
  if (!data) return <div className="status">{t(lang, "loading")}</div>;

  const isEmpty = !data.kanji.length && !data.decompositions.length
    && !data.aliases.length && !data.stories.length;

  function rowLabel(row) {
    return displayChar(row.character) || row.keyword || row.kanji_id || row.id;
  }

  return (
    <div className="form-view">
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
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
