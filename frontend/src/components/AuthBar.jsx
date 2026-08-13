import { useEffect, useRef, useState } from "react";
import { login, register, logout, googleLogin } from "../api";
import { t } from "../i18n";

// Public identifier, safe to embed in the built bundle — see CLAUDE.md "Google SSO".
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

let googleScriptPromise = null;
function loadGoogleScript() {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (!googleScriptPromise) {
    googleScriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      script.onload = resolve;
      script.onerror = () => { googleScriptPromise = null; reject(new Error("Failed to load Google sign-in")); };
      document.head.appendChild(script);
    });
  }
  return googleScriptPromise;
}

export default function AuthBar({ user, setUser, lang = "en", uiLang, studyScript }) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const googleBtnRef = useRef(null);
  // "Latest ref" so the Google callback (registered once per popover-open, not
  // per keystroke) always reads current prefs without re-initializing the button.
  const prefsRef = useRef({ uiLang, studyScript });
  prefsRef.current = { uiLang, studyScript };

  function resetForm() {
    setUsername("");
    setPassword("");
    setError("");
  }

  useEffect(() => {
    if (!open || user || !GOOGLE_CLIENT_ID) return;
    let cancelled = false;
    loadGoogleScript()
      .then(() => {
        if (cancelled || !googleBtnRef.current) return;
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: async ({ credential }) => {
            setBusy(true);
            setError("");
            try {
              const me = await googleLogin(credential, {
                ui_language: prefsRef.current.uiLang,
                study_script: prefsRef.current.studyScript,
              });
              setUser(me);
              setOpen(false);
              resetForm();
            } catch (err) {
              setError(err.message);
            } finally {
              setBusy(false);
            }
          },
        });
        googleBtnRef.current.innerHTML = "";
        window.google.accounts.id.renderButton(googleBtnRef.current, { theme: "outline", size: "large", width: 240 });
      })
      .catch((err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, user]);

  async function handleSubmit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const me = mode === "login"
        ? await login(username.trim(), password)
        // Seed the new account with whatever language/study-script this (possibly
        // anonymous) session already had set locally, so registering doesn't
        // silently reset a choice the user already made.
        : await register(username.trim(), password, { ui_language: uiLang, study_script: studyScript });
      setUser(me);
      setOpen(false);
      resetForm();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleLogout() {
    setBusy(true);
    try {
      await logout();
    } finally {
      setUser(null);
      setBusy(false);
    }
  }

  if (user) {
    return (
      <div className="auth-bar">
        <span className="auth-username">{user.username}</span>
        <button className="auth-link-btn" onClick={handleLogout} disabled={busy}>
          {t(lang, "logoutBtn")}
        </button>
      </div>
    );
  }

  return (
    <div className="auth-bar">
      {!open ? (
        <button className="auth-link-btn" onClick={() => setOpen(true)}>
          {t(lang, "loginRegisterBtn")}
        </button>
      ) : (
        <div className="auth-popover">
          <div className="auth-tabs">
            <button
              className={`auth-tab ${mode === "login" ? "auth-tab-active" : ""}`}
              onClick={() => { setMode("login"); setError(""); }}
              type="button"
            >
              {t(lang, "loginTab")}
            </button>
            <button
              className={`auth-tab ${mode === "register" ? "auth-tab-active" : ""}`}
              onClick={() => { setMode("register"); setError(""); }}
              type="button"
            >
              {t(lang, "registerTab")}
            </button>
          </div>
          <form className="auth-form" onSubmit={handleSubmit}>
            <input
              className="input"
              placeholder={t(lang, "usernamePlaceholder")}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
            <input
              className="input"
              type="password"
              placeholder={mode === "register" ? t(lang, "passwordPlaceholderRegister") : t(lang, "passwordPlaceholder")}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={mode === "register" ? 8 : undefined}
              required
            />
            <div className="auth-form-actions">
              <button className="btn-primary" type="submit" disabled={busy}>
                {mode === "login" ? t(lang, "loginSubmit") : t(lang, "registerSubmit")}
              </button>
              <button
                className="auth-link-btn"
                type="button"
                onClick={() => { setOpen(false); resetForm(); }}
              >
                {t(lang, "cancelBtn")}
              </button>
            </div>
          </form>
          {GOOGLE_CLIENT_ID && (
            <div className="auth-google">
              <div className="auth-divider">{t(lang, "authDividerOr")}</div>
              <div ref={googleBtnRef} />
            </div>
          )}
          {error && <div className="auth-error">{error}</div>}
        </div>
      )}
    </div>
  );
}
