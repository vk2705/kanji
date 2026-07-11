import { useEffect, useState } from "react";
import { getKanji, addAlias, addStory } from "../api";
import { displayChar } from "../utils";
import { t } from "../i18n";

function PartAliasAdder({ partId, lang }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [added, setAdded] = useState(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!value.trim()) return;
    setBusy(true);
    try {
      const res = await addAlias(partId, value.trim(), "private");
      setAdded(res.alias);
      setValue("");
      setOpen(false);
    } catch {
      // silently ignore — this is a minor inline affordance, not worth a modal error
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button type="button" className="part-add-btn" onClick={() => setOpen(true)}>
        {added ? `“${added}”` : "+"}
      </button>
    );
  }

  return (
    <form className="part-add-form" onSubmit={handleSubmit}>
      <input
        className="input part-add-input"
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={t(lang, "addNamePlaceholder")}
      />
      <button className="btn-primary part-add-submit" type="submit" disabled={busy}>
        {t(lang, "addBtn")}
      </button>
    </form>
  );
}

export default function KanjiDetail({ kanjiId, onSelectPart, onBack, user, lang = "en" }) {
  const [kanji, setKanji] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [storyText, setStoryText] = useState("");
  const [storyPublic, setStoryPublic] = useState(false);
  const [savingStory, setSavingStory] = useState(false);

  function load() {
    setLoading(true);
    setError(null);
    getKanji(kanjiId)
      .then((k) => {
        setKanji(k);
        const mine = k.stories?.find((s) => s.is_mine);
        setStoryText(mine?.story ?? "");
        setStoryPublic(mine?.visibility === "public");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [kanjiId]);

  async function handleSaveStory(e) {
    e.preventDefault();
    if (!storyText.trim()) return;
    setSavingStory(true);
    try {
      await addStory(kanji.id, storyText.trim(), storyPublic ? "public" : "private");
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingStory(false);
    }
  }

  if (loading) return <div className="status">{t(lang, "loading")}</div>;
  if (error) return <div className="status error">{t(lang, "errorPrefix", error)}</div>;
  if (!kanji) return null;

  const otherStories = kanji.stories?.filter((s) => !s.is_mine) ?? [];

  return (
    <div className="detail-panel">
      <button className="back-btn" onClick={onBack}>{t(lang, "backBtn")}</button>

      <div className="detail-header">
        <span className="detail-char">{displayChar(kanji.character) ?? "·"}</span>
        <div className="detail-meta">
          <div className="detail-keyword">{kanji.keyword || kanji.id}</div>
          <div className="detail-badges">
            {kanji.frame && <span className="badge badge-frame">{t(lang, "rtkFrame", kanji.frame)}</span>}
            {kanji.jlpt && <span className="badge badge-jlpt">{kanji.jlpt}</span>}
            {kanji.stroke_count && <span className="badge badge-strokes">{t(lang, "strokesLabel", kanji.stroke_count)}</span>}
          </div>
          <div className="detail-id">{kanji.id}</div>
        </div>
      </div>

      {kanji.aliases.length > 0 && (
        <section className="detail-section">
          <h3>{t(lang, "aliasesHeading")}</h3>
          <div className="tag-list">
            {kanji.aliases.map((a) => (
              <span key={a.id} className="tag">{a.alias}</span>
            ))}
          </div>
        </section>
      )}

      {kanji.decompositions?.[0]?.parts_detail?.length > 0 && (
        <section className="detail-section">
          <h3>{t(lang, "madeFromHeading")}</h3>
          <div className="parts-list">
            {kanji.decompositions[0].parts_detail.map((part, i) => (
              <div key={i} className="part-chip-wrap">
                <button
                  className="part-chip"
                  onClick={() => part.id && onSelectPart(part.id)}
                  disabled={!part.id}
                >
                  <span className="part-chip-char">{displayChar(part.character) ?? "·"}</span>
                  <span className="part-chip-label">{part.keyword || part.id}</span>
                  {part.frame && <span className="part-chip-frame">#{part.frame}</span>}
                </button>
                {user && part.id && <PartAliasAdder partId={part.id} lang={lang} />}
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="detail-section">
        <h3>{t(lang, "yourStoryHeading")}</h3>
        {user ? (
          <form className="story-form" onSubmit={handleSaveStory}>
            <textarea
              className="input story-textarea"
              value={storyText}
              onChange={(e) => setStoryText(e.target.value)}
              placeholder={t(lang, "yourStoryPlaceholder")}
              rows={4}
            />
            <div className="story-form-actions">
              <label className="story-visibility">
                <input
                  type="checkbox"
                  checked={storyPublic}
                  onChange={(e) => setStoryPublic(e.target.checked)}
                />
                {t(lang, "makePublicLabel")}
              </label>
              <button className="btn-primary" type="submit" disabled={savingStory}>
                {t(lang, "saveBtn")}
              </button>
            </div>
          </form>
        ) : (
          <p className="login-hint">{t(lang, "loginHintContribute")}</p>
        )}

        {otherStories.length > 0 && (
          <div className="other-stories">
            <h4>{t(lang, "otherStoriesHeading")}</h4>
            {otherStories.map((s) => (
              <div key={s.id} className="other-story">
                <div className="other-story-owner">{s.owner}</div>
                <div className="other-story-text">{s.story}</div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
