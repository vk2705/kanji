import { t } from "../i18n";

const REPO_URL = "https://github.com/vk2705/kanji";
const APK_URL = "https://github.com/vk2705/kanji/raw/master/android/releases/rtk-kanji-latest.apk";

export default function AboutPage({ lang }) {
  return (
    <div className="form-view">
      <h2>{t(lang, "aboutHeading")}</h2>
      <p className="about-intro">{t(lang, "aboutIntro")}</p>

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
    </div>
  );
}
