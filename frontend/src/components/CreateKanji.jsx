import { useState } from "react";
import { createKanji } from "../api";
import { t } from "../i18n";
import { ImageUpload, DecompositionForm } from "./KanjiDetail";

const SCRIPTS = ["ja-kanji", "zh-Hans", "zh-Hant", "zh-Hani"];

export default function CreateKanji({ lang, onDone }) {
  const [keyword, setKeyword] = useState("");
  const [character, setCharacter] = useState("");
  const [script, setScript] = useState("ja-kanji");
  const [isPrivate, setIsPrivate] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [created, setCreated] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!keyword.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await createKanji({
        keyword: keyword.trim(),
        character: character.trim() || null,
        script,
        visibility: isPrivate ? "private" : "public",
      });
      setCreated({ id: res.id, character: character.trim() });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (created) {
    return (
      <div className="form-view">
        <h2>{t(lang, "createKanjiHeading")}</h2>
        <p className="login-hint">{t(lang, "createdKanjiNote")}</p>

        {!created.character && (
          <section className="detail-section">
            <h3>{t(lang, "uploadImageHeading")}</h3>
            <ImageUpload kanjiId={created.id} lang={lang} onUploaded={() => {}} />
          </section>
        )}

        <section className="detail-section">
          <h3>{t(lang, "addDecompositionHeading")}</h3>
          <DecompositionForm kanjiId={created.id} lang={lang} onAdded={() => {}} />
        </section>

        <button className="btn-primary" onClick={() => onDone(created.id)}>
          {t(lang, "doneBtn")}
        </button>
      </div>
    );
  }

  return (
    <div className="form-view">
      <h2>{t(lang, "createKanjiHeading")}</h2>
      <form className="story-form" onSubmit={handleSubmit}>
        <input
          className="input"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder={t(lang, "keywordPlaceholder")}
          autoFocus
        />
        <input
          className="input"
          value={character}
          onChange={(e) => setCharacter(e.target.value)}
          placeholder={t(lang, "characterPlaceholder")}
          maxLength={2}
        />
        <div>
          <div className="form-field-label">{t(lang, "scriptLabel")}</div>
          <select className="input" value={script} onChange={(e) => setScript(e.target.value)}>
            {SCRIPTS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div className="story-form-actions">
          <label className="story-visibility">
            <input
              type="checkbox"
              checked={isPrivate}
              onChange={(e) => setIsPrivate(e.target.checked)}
            />
            {t(lang, "makePrivateCheckbox")}
          </label>
          <button className="btn-primary" type="submit" disabled={busy}>
            {t(lang, "createSubmit")}
          </button>
        </div>
        {error && <div className="status error">{error}</div>}
      </form>
    </div>
  );
}
