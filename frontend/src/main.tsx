import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { createHttpTransport } from "./shared/api/httpTransport";
import { createSyntheticTransport } from "./shared/api/syntheticTransport";
import { createBrowserPlatform } from "./shared/platform/browserPlatform";
import "./styles.css";

const syntheticPreview = import.meta.env.DEV;
const transport = syntheticPreview ? createSyntheticTransport() : createHttpTransport();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App
      mode={syntheticPreview ? "synthetic" : "local"}
      platform={createBrowserPlatform()}
      transport={transport}
    />
  </StrictMode>,
);
