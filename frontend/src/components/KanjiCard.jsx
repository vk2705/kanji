export default function KanjiCard({ kanji, onSelect }) {
  const char = kanji.character && !["?", "??", ""].includes(kanji.character)
    ? kanji.character
    : null;

  return (
    <div className="kanji-card" onClick={() => onSelect(kanji.id)}>
      <div className="kanji-char">{char ?? "·"}</div>
      <div className="kanji-keyword">{kanji.keyword || kanji.id}</div>
      <div className="kanji-meta">
        {kanji.frame && <span className="meta-frame">#{kanji.frame}</span>}
        {kanji.jlpt && <span className="meta-jlpt">{kanji.jlpt}</span>}
      </div>
    </div>
  );
}
