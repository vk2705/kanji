import KanjiCard from "./KanjiCard";
import { t } from "../i18n";

export default function ResultsGrid({ results, onSelect, loading, lang = "en" }) {
  if (loading) return <div className="status">{t(lang, "searching")}</div>;
  if (!results) return null;
  if (results.length === 0) return <div className="status">{t(lang, "noResults")}</div>;

  return (
    <div>
      <div className="results-count">{t(lang, "resultCount", results.length)}</div>
      <div className="results-grid">
        {results.map((k) => (
          <KanjiCard key={k.id} kanji={k} onSelect={onSelect} />
        ))}
      </div>
    </div>
  );
}
