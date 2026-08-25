import { describe, expect, it } from "vitest";
import agentPageCss from "./AgentPage.css?raw";

describe("AgentPage layout contract", () => {
  it("does not let tall neighboring panels stretch the conversation below the viewport", () => {
    expect(agentPageCss).toMatch(/\.agent__layout\s*\{[^}]*align-items:\s*start;/);
    expect(agentPageCss).toMatch(/\.agent__workbench\s*\{[^}]*align-items:\s*start;[^}]*align-self:\s*start;/);
    expect(agentPageCss).toMatch(/\.agent__main\s*\{[^}]*height:\s*clamp\(32rem,\s*calc\(100dvh\s*-\s*15rem\),\s*46rem\);/);
  });

  it("keeps the transcript as the shrinking scroll region and preserves full-height window mode", () => {
    expect(agentPageCss).toMatch(/\.agent__log\s*\{[^}]*overflow-y:\s*auto;[^}]*min-height:\s*0;/);
    expect(agentPageCss).toMatch(/\.agent__layout--window \.agent__main\s*\{\s*height:\s*100%;\s*}/);
  });

  it("puts the conversation before secondary panels whenever the session layout stacks", () => {
    expect(agentPageCss).toMatch(/@media \(max-width:\s*1380px\)[\s\S]*?\.agent__workbench\[data-has-workspace="true"\] > \.agent__main\s*\{\s*grid-row:\s*1;/);
    expect(agentPageCss).toMatch(/@media \(max-width:\s*900px\)[\s\S]*?\.agent__layout--session:not\(\.agent__layout--window\) > \.agent__workbench\s*\{\s*grid-row:\s*1;/);
  });
});
