import { t } from "../i18n";

export default function ViewNavigation({ lang, onBack, onHome }) {
  return (
    <div className="view-navigation">
      {onBack && <button className="back-btn" onClick={onBack}>{t(lang, "backBtn")}</button>}
      {onHome && <button className="home-btn" onClick={onHome}>{t(lang, "homeBtn")}</button>}
    </div>
  );
}