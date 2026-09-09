import Glyph from "./Glyph";

export default function KanjiCard({ kanji, onSelect }) {
  return (
    <button type="button" className="kanji-card" onClick={() => onSelect(kanji.id)}>
      <div className="kanji-char">
        <Glyph character={kanji.character} imageUrl={kanji.image_url}
               keyword={kanji.keyword} id={kanji.id} imgClassName="kanji-char-img" />
      </div>
      <div className="kanji-keyword">{kanji.keyword || kanji.id}</div>
      <div className="kanji-meta">
        {kanji.frame && <span className="meta-frame">#{kanji.frame}</span>}
        {kanji.jlpt && <span className="meta-jlpt">{kanji.jlpt}</span>}
      </div>
    </button>
  );
}
