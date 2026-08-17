import { useEffect, useState } from "react";
import { getKanji, addAlias, addStory, createDecomposition, uploadKanjiImage, resolveImageUrl } from "../api";
import { displayChar } from "../utils";
import { t } from "../i18n";

function AliasAdder({ targetId, lang }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [added, setAdded] = useState(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!value.trim()) return;
    setBusy(true);
    try {
      const res = await addAlias(targetId, value.trim(), "private");
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

export function ImageUpload({ kanjiId, lang, onUploaded }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function handleChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await uploadKanjiImage(kanjiId, file);
      onUploaded();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="image-upload">
      <input type="file" accept="image/gif,image/png,image/jpeg,image/webp" onChange={handleChange} disabled={busy} />
      {error ? <span className="image-upload-hint status error">{error}</span> : (
        <span className="image-upload-hint">{t(lang, "uploadImageHint")}</span>
      )}
    </div>
  );
}

export function DecompositionForm({ kanjiId, lang, onAdded }) {
  const [parts, setParts] = useState("");
  const [label, setLabel] = useState("");
  const [isPublic, setIsPublic] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    const partList = parts.split(",").map((p) => p.trim()).filter(Boolean);
    if (!partList.length) return;
    setBusy(true);
    setError(null);
    try {
      await createDecomposition(kanjiId, {
        parts: partList,
        label: label.trim() || null,
        visibility: isPublic ? "public" : "private",
      });
      setParts("");
      setLabel("");
      onAdded();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="story-form" onSubmit={handleSubmit}>
      <input
        className="input"
        value={parts}
        onChange={(e) => setParts(e.target.value)}
        placeholder={t(lang, "decompositionPartsPlaceholder")}
      />
      <input
        className="input"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder={t(lang, "decompositionLabelPlaceholder")}
      />
      <div className="story-form-actions">
        <label className="story-visibility">
          <input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} />
          {t(lang, "makePublicLabel")}
        </label>
        <button className="btn-primary" type="submit" disabled={busy}>
          {t(lang, "addDecompositionSubmit")}
        </button>
      </div>
      {error && <div className="status error">{error}</div>}
    </form>
  );
}

function PartChip({ part, lang, user, onSelectPart }) {
  const [expanded, setExpanded] = useState(false);
  const partChar = displayChar(part.character);
  // sub_decompositions is a list of alternative decompositions of THIS part (e.g. a
  // system breakdown and a user's own) — usually just one, but every alternative
  // renders as its own line when expanded, same idea as the top-level decompositions
  // list in KanjiDetail below, all the way down the tree.
  const subDecompositions = (part.sub_decompositions ?? []).filter((sd) => sd.parts.length > 0);
  const hasSubParts = subDecompositions.length > 0;

  return (
    <div className="part-chip-wrap">
      <div className="part-chip-row">
        {hasSubParts && (
          <button
            type="button"
            className="part-chip-expand"
            onClick={() => setExpanded((e) => !e)}
            aria-label={t(lang, expanded ? "collapsePart" : "expandPart")}
            title={t(lang, expanded ? "collapsePart" : "expandPart")}
          >
            {expanded ? "▾" : "▸"}
          </button>
        )}
        <button
          className="part-chip"
          onClick={() => part.id && onSelectPart(part.id)}
          disabled={!part.id}
        >
          <span className="part-chip-char">
            {partChar ?? (part.image_url
              ? <img className="part-chip-img" src={resolveImageUrl(part.image_url)} alt={part.keyword || part.id} />
              : "·")}
          </span>
          <span className="part-chip-label">{part.keyword || part.id}</span>
          {part.frame && <span className="part-chip-frame">#{part.frame}</span>}
        </button>
        {user && part.id && <AliasAdder targetId={part.id} lang={lang} />}
      </div>
      {hasSubParts && expanded && (
        <div className="sub-decompositions">
          {subDecompositions.map((sd, i) => (
            <div key={sd.id} className="sub-decomposition">
              {subDecompositions.length > 1 && (
                <div className="sub-decomposition-label">{sd.label || sd.owner || `#${i + 1}`}</div>
              )}
              <div className="parts-list sub-parts">
                {sd.parts.map((sub, j) => (
                  <PartChip key={j} part={sub} lang={lang} user={user} onSelectPart={onSelectPart} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function KanjiDetail({ kanjiId, onSelectPart, onBack, user, lang = "en", sources = null }) {
  const [kanji, setKanji] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [storyText, setStoryText] = useState("");
  const [storyPublic, setStoryPublic] = useState(false);
  const [savingStory, setSavingStory] = useState(false);

  function load() {
    setLoading(true);
    setError(null);
    getKanji(kanjiId, sources)
      .then((k) => {
        setKanji(k);
        const mine = k.stories?.find((s) => s.is_mine);
        setStoryText(mine?.story ?? "");
        setStoryPublic(mine?.visibility === "public");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  // sources is a freshly-built array/null each App render, so key on its sorted
  // contents rather than identity to avoid refetching on unrelated re-renders.
  const sourcesKey = sources ? [...sources].sort().join(",") : "";
  useEffect(() => load(), [kanjiId, sourcesKey]);

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
  const decompositions = kanji.decompositions ?? [];
  const nonEmptyDecompositions = decompositions.filter((d) => d.parts_detail.length > 0);
  const char = displayChar(kanji.character);

  return (
    <div className="detail-panel">
      <button className="back-btn" onClick={onBack}>{t(lang, "backBtn")}</button>

      <div className="detail-header">
        <span className="detail-char">
          {char ?? (kanji.image_url
            ? <img className="detail-char-img" src={resolveImageUrl(kanji.image_url)} alt={kanji.keyword || kanji.id} />
            : "·")}
        </span>
        <div className="detail-meta">
          <div className="detail-keyword">
            {kanji.keyword || kanji.id}
            {user && <AliasAdder targetId={kanji.id} lang={lang} />}
          </div>
          <div className="detail-badges">
            {kanji.frame && <span className="badge badge-frame">{t(lang, "rtkFrame", kanji.frame)}</span>}
            {kanji.jlpt && <span className="badge badge-jlpt">{kanji.jlpt}</span>}
            {kanji.stroke_count && <span className="badge badge-strokes">{t(lang, "strokesLabel", kanji.stroke_count)}</span>}
          </div>
          <div className="detail-id">{kanji.id}</div>
        </div>
      </div>

      {user && kanji.is_mine && !char && (
        <section className="detail-section">
          <h3>{t(lang, "uploadImageHeading")}</h3>
          <ImageUpload kanjiId={kanji.id} lang={lang} onUploaded={() => load()} />
        </section>
      )}

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

      {(nonEmptyDecompositions.length > 0 || user) && (
        <section className="detail-section">
          <h3>{t(lang, "madeFromHeading")}</h3>

          {/* Every visible decomposition renders as its own line — a kanji taught two
              different ways (e.g. the system breakdown and a user's own alternate)
              shows both at once, not behind a tab you have to click to see. */}
          {nonEmptyDecompositions.map((d, i) => (
            <div key={d.id} className="decomposition-block">
              {nonEmptyDecompositions.length > 1 && (
                <div className="decomposition-label">{d.label || d.owner || `#${i + 1}`}</div>
              )}
              <div className="parts-list">
                {d.parts_detail.map((part, j) => (
                  <PartChip key={j} part={part} lang={lang} user={user} onSelectPart={onSelectPart} />
                ))}
              </div>
            </div>
          ))}

          {user && (
            <details style={{ marginTop: 14 }}>
              <summary className="login-hint" style={{ cursor: "pointer" }}>
                {t(lang, "addDecompositionHeading")}
              </summary>
              <DecompositionForm kanjiId={kanji.id} lang={lang} onAdded={() => load()} />
            </details>
          )}
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
