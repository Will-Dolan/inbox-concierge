import { useEffect, useState } from "react";
import { api, ApiError, setToken } from "./api";
import { Login } from "./components/Login";
import { InboxView } from "./components/InboxView";

type AuthState = { status: "loading" } | { status: "signed-out" } | { status: "signed-in"; email: string };

export default function App() {
  const [auth, setAuth] = useState<AuthState>({ status: "loading" });

  useEffect(() => {
    const url = new URL(window.location.href);
    const token = url.searchParams.get("token");
    if (token) {
      setToken(token);
      url.searchParams.delete("token");
      window.history.replaceState({}, "", url.toString());
    }

    api
      .me()
      .then((me) => setAuth({ status: "signed-in", email: me.email }))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          setAuth({ status: "signed-out" });
        } else {
          setAuth({ status: "signed-out" });
        }
      });
  }, []);

  if (auth.status === "loading") {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }

  if (auth.status === "signed-out") {
    return <Login />;
  }

  async function handleLogout() {
    await api.logout();
    setAuth({ status: "signed-out" });
  }

  return <InboxView userEmail={auth.email} onLogout={handleLogout} />;
}
