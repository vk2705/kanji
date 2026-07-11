import { useState } from "react";
import { login, register, logout } from "../api";
import { t } from "../i18n";

export default function AuthBar({ user, setUser, lang = "en", uiLang, studyScript }) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function resetForm() {
    setUsername("");
    setPassword("");
    setError("");
  }

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
            {error && <div className="auth-error">{error}</div>}
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
        </div>
      )}
    </div>
  );
}
