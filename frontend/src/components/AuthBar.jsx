import { useState } from "react";
import { login, register, logout } from "../api";

export default function AuthBar({ user, setUser }) {
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
      const fn = mode === "login" ? login : register;
      const me = await fn(username.trim(), password);
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
          Log out
        </button>
      </div>
    );
  }

  return (
    <div className="auth-bar">
      {!open ? (
        <button className="auth-link-btn" onClick={() => setOpen(true)}>
          Log in / Register
        </button>
      ) : (
        <div className="auth-popover">
          <div className="auth-tabs">
            <button
              className={`auth-tab ${mode === "login" ? "auth-tab-active" : ""}`}
              onClick={() => { setMode("login"); setError(""); }}
              type="button"
            >
              Log in
            </button>
            <button
              className={`auth-tab ${mode === "register" ? "auth-tab-active" : ""}`}
              onClick={() => { setMode("register"); setError(""); }}
              type="button"
            >
              Register
            </button>
          </div>
          <form className="auth-form" onSubmit={handleSubmit}>
            <input
              className="input"
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
            <input
              className="input"
              type="password"
              placeholder={mode === "register" ? "Password (min 8 chars)" : "Password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={mode === "register" ? 8 : undefined}
              required
            />
            {error && <div className="auth-error">{error}</div>}
            <div className="auth-form-actions">
              <button className="btn-primary" type="submit" disabled={busy}>
                {mode === "login" ? "Log in" : "Create account"}
              </button>
              <button
                className="auth-link-btn"
                type="button"
                onClick={() => { setOpen(false); resetForm(); }}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
