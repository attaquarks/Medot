import React from "react";
import ReactDOM from "react-dom/client";
import App, { setLaunchToken, completeDeepLink } from "./App";

// Inside the Tauri shell the Rust side announces the runtime handshake
// (launch token) and forwards OAuth deep links. Outside Tauri (plain browser
// dev) these imports fail silently — sign-in is then unavailable by design.
const isTauri = "__TAURI_INTERNALS__" in window;

async function bootstrap() {
  if (isTauri) {
    const { listen } = await import("@tauri-apps/api/event");
    await listen<{ launch_token: string }>("runtime-ready", (event) => {
      setLaunchToken(event.payload.launch_token);
    });
    await listen<{ url: string }>("deep-link", (event) => {
      completeDeepLink(event.payload.url);
    });
  }
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}

bootstrap();
