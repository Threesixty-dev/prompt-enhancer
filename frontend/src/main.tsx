import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { createHttpTransport } from "./shared/api/httpTransport";
import { createSyntheticTransport } from "./shared/api/syntheticTransport";
import { createBrowserPlatform } from "./shared/platform/browserPlatform";
import { resolveRuntimeDataMode } from "./shared/platform/runtimeMode";
import { startUiRevisionGuard } from "./shared/platform/uiRevisionGuard";
import "./styles.css";

const mode = resolveRuntimeDataMode({
  development: import.meta.env.DEV,
  viteMode: import.meta.env.MODE,
});
const syntheticPreview = mode === "synthetic";
const transport = syntheticPreview ? createSyntheticTransport() : createHttpTransport();
const uiRevisionGuard = startUiRevisionGuard({
  enabled: !syntheticPreview,
  moduleUrl: import.meta.url,
});

if (import.meta.hot) {
  import.meta.hot.dispose(() => uiRevisionGuard.dispose());
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App
      mode={mode}
      platform={createBrowserPlatform()}
      transport={transport}
    />
  </StrictMode>,
);
