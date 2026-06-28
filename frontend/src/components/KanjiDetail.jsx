import { useEffect, useState } from "react";
import { getKanji } from "../api";
import { displayChar } from "../utils";

export default function KanjiDetail({ kanjiId, onSelectPart, onBack }) {
  const [kanji, setKanji] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getKanji(kanjiId)
      .then(setKanji)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [kanjiId]);

  if (loading) return <div className="status">Loading…</div>;
  if (error) return <div className="status error">Error: {error}</div>;
  if (!kanji) return null;

  return (
    <div className="detail-panel">
      <button className="back-btn" onClick={onBack}>← Back</button>

      <div className="detail-header">
        <span className="detail-char">{displayChar(kanji.character) ?? "·"}</span>
        <div className="detail-meta">
          <div className="detail-keyword">{kanji.keyword || kanji.id}</div>
          <div className="detail-badges">
            {kanji.frame && <span className="badge badge-frame">RTK #{kanji.frame}</span>}
            {kanji.jlpt && <span className="badge badge-jlpt">{kanji.jlpt}</span>}
            {kanji.stroke_count && <span className="badge badge-strokes">{kanji.stroke_count} strokes</span>}
          </div>
          <div className="detail-id">{kanji.id}</div>
        </div>
      </div>

      {kanji.aliases.length > 0 && (
        <section className="detail-section">
          <h3>Aliases / names</h3>
          <div className="tag-list">
            {kanji.aliases.map((a) => (
              <span key={a} className="tag">{a}</span>
            ))}
          </div>
        </section>
      )}

      {kanji.parts_detail && kanji.parts_detail.length > 0 && (
        <section className="detail-section">
          <h3>Made from</h3>
          <div className="parts-list">
            {kanji.parts_detail.map((part, i) => (
              <button
                key={i}
                className="part-chip"
                onClick={() => part.id && onSelectPart(part.id)}
                disabled={!part.id}
              >
                <span className="part-chip-char">{displayChar(part.character) ?? "·"}</span>
                <span className="part-chip-label">{part.keyword || part.id}</span>
                {part.frame && <span className="part-chip-frame">#{part.frame}</span>}
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
