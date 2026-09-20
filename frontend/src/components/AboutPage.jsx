import { t } from "../i18n";

const REPO_URL = "https://github.com/vk2705/kanji";
const APK_URL = "https://github.com/vk2705/kanji/raw/master/android/releases/rtk-kanji-latest.apk";
const PRIVACY_URL = "privacy.html";
const CHANGELOG_URL = "https://github.com/vk2705/kanji/blob/master/CHANGELOG.md";

export default function AboutPage({ lang, onBack }) {
  const whatsNewItems = t(lang, "aboutWhatsNewItems");
  return (
    <div className="form-view">
      {onBack && <button className="back-btn" onClick={onBack}>{t(lang, "backBtn")}</button>}
      <h2>{t(lang, "aboutHeading")}</h2>
      <p className="about-intro">{t(lang, "aboutIntro")}</p>

      <div className="contrib-section">
        <h3>{t(lang, "aboutWhatsNewHeading")}</h3>
        <ul>
          {whatsNewItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <a className="about-link" href={CHANGELOG_URL} target="_blank" rel="noreferrer">
          {t(lang, "aboutChangelogLinkLabel")}
        </a>
      </div>

      <div className="contrib-section">
        <h3>{t(lang, "aboutRepoHeading")}</h3>
        <a className="about-link" href={REPO_URL} target="_blank" rel="noreferrer">
          {t(lang, "aboutRepoLinkLabel")}
        </a>
      </div>

      <div className="contrib-section">
        <h3>{t(lang, "aboutDownloadHeading")}</h3>
        <a className="about-link" href={APK_URL} target="_blank" rel="noreferrer">
          {t(lang, "aboutDownloadLinkLabel")}
        </a>
        <p className="login-hint">{t(lang, "aboutDownloadNote")}</p>
      </div>

      <div className="contrib-section">
        <h3>{t(lang, "aboutPrivacyHeading")}</h3>
        <a className="about-link" href={PRIVACY_URL} target="_blank" rel="noreferrer">
          {t(lang, "aboutPrivacyLinkLabel")}
        </a>
      </div>
    </div>
  );
}
