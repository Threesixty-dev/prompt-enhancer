import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { createHttpTransport } from "./shared/api/httpTransport";
import { createBrowserPlatform } from "./shared/platform/browserPlatform";
import {
  createRuntimeComposition,
  resolveRuntimeDataMode,
} from "./shared/platform/runtimeMode";
import { startUiRevisionGuard } from "./shared/platform/uiRevisionGuard";
import "./styles.css";

async function mountApp() {
  const mode = resolveRuntimeDataMode({
    development: import.meta.env.DEV,
    viteMode: import.meta.env.MODE,
  });
  const syntheticPreview = mode === "synthetic_demo";
  const transport = syntheticPreview
    ? (await import("./shared/api/syntheticTransport")).createSyntheticTransport()
    : createHttpTransport();
  const runtime = createRuntimeComposition(mode, transport);
  const uiRevisionGuard = startUiRevisionGuard({
    enabled: !syntheticPreview,
    moduleUrl: import.meta.url,
  });

  if (import.meta.hot) {
    import.meta.hot.dispose(() => uiRevisionGuard.dispose());
  }

  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App platform={createBrowserPlatform()} runtime={runtime} />
    </StrictMode>,
  );
}

void mountApp();
