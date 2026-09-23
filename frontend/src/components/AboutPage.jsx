import { t } from "../i18n";
import ViewNavigation from "./ViewNavigation";

const REPO_URL = "https://github.com/vk2705/kanji";
const APK_URL = "https://github.com/vk2705/kanji/raw/master/android/releases/rtk-kanji-latest.apk";
const PRIVACY_URL = "privacy.html";
const CHANGELOG_URL = "https://github.com/vk2705/kanji/blob/master/CHANGELOG.md";
const BOOK_URL = "https://uhpress.hawaii.edu/title/remembering-the-kanji-1/";
const PROVENANCE_URL = "https://github.com/vk2705/kanji/blob/master/docs/DATA_SOURCES.md";

export default function AboutPage({ lang, onBack, onHome }) {
  const whatsNewItems = t(lang, "aboutWhatsNewItems");
  return (
    <div className="form-view">
      <ViewNavigation onBack={onBack} onHome={onHome} lang={lang} />
      <h2>{t(lang, "aboutHeading")}</h2>
      <p className="about-intro">{t(lang, "aboutIntro")}</p>
      <p className="about-intro">{t(lang, "aboutIntro2")}</p>

      <div className="contrib-section">
        <h3>{t(lang, "aboutCreditsHeading")}</h3>
        <p className="login-hint">{t(lang, "aboutCreditsBook")}</p>
        <a className="about-link" href={BOOK_URL} target="_blank" rel="noreferrer">
          {t(lang, "aboutCreditsBookLinkLabel")}
        </a>
        <p className="login-hint">{t(lang, "aboutCreditsData")}</p>
        <a className="about-link" href={PROVENANCE_URL} target="_blank" rel="noreferrer">
          {t(lang, "aboutCreditsProvenanceLinkLabel")}
        </a>
      </div>

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
