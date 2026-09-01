import { displayChar } from "../utils";
import { resolveImageUrl } from "../api";

export default function KanjiCard({ kanji, onSelect }) {
  const char = displayChar(kanji.character);
  return (
    <button type="button" className="kanji-card" onClick={() => onSelect(kanji.id)}>
      <div className="kanji-char">
        {char ?? (kanji.image_url
          ? <img className="kanji-char-img" src={resolveImageUrl(kanji.image_url)} alt={kanji.keyword || kanji.id} />
          : "·")}
      </div>
      <div className="kanji-keyword">{kanji.keyword || kanji.id}</div>
      <div className="kanji-meta">
        {kanji.frame && <span className="meta-frame">#{kanji.frame}</span>}
        {kanji.jlpt && <span className="meta-jlpt">{kanji.jlpt}</span>}
      </div>
    </button>
  );
}
