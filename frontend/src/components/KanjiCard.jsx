import { displayChar } from "../utils";

export default function KanjiCard({ kanji, onSelect }) {
  return (
    <div className="kanji-card" onClick={() => onSelect(kanji.id)}>
      <div className="kanji-char">{displayChar(kanji.character) ?? "·"}</div>
      <div className="kanji-keyword">{kanji.keyword || kanji.id}</div>
      <div className="kanji-meta">
        {kanji.frame && <span className="meta-frame">#{kanji.frame}</span>}
        {kanji.jlpt && <span className="meta-jlpt">{kanji.jlpt}</span>}
      </div>
    </div>
  );
}
