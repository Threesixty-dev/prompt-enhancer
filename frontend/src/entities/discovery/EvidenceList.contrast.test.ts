import { describe, expect, it } from "vitest";
import appCss from "../../styles.css?raw";
import themeCss from "../../app/theme.css?raw";

/*
 * The discovery evidence heading renders a 12px bold <strong> on the warm card
 * surface, so it is measured against the WCAG normal-text ratio. It carries no
 * colour of its own and inherits the route ink from `:root`, which is the pair
 * pinned here for both themes. A browser sweep can only observe this pair once
 * the shell theme transition has finished, so the same obligation is asserted
 * statically: a palette regression fails here regardless of rendering timing.
 */
const NORMAL_TEXT_RATIO = 4.5;

function tokenBlock(css: string, selector: string): string {
  const start = css.indexOf(`${selector} {`);
  expect(start, `${selector} is missing`).toBeGreaterThanOrEqual(0);
  const end = css.indexOf("}", start);
  expect(end, `${selector} is unterminated`).toBeGreaterThan(start);
  return css.slice(start, end);
}

function token(block: string, name: string): string {
  const value = block.match(new RegExp(`--${name}:\\s*(#[0-9a-f]{6})\\b`, "iu"))?.[1] ?? "";
  expect(value, `--${name} is not a plain hex token`).toMatch(/^#[0-9a-f]{6}$/iu);
  return value;
}

function relativeLuminance(hex: string): number {
  const channels = [1, 3, 5].map((offset) => {
    const value = Number.parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrast(foreground: string, background: string): number {
  const first = relativeLuminance(foreground);
  const second = relativeLuminance(background);
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}

describe("discovery evidence heading contrast", () => {
  it("inherits the route ink instead of a muted token", () => {
    expect(appCss).toMatch(/:root\s*\{[^}]*\bcolor:\s*var\(--ink-950\);/u);

    const heading = appCss.match(/\.evidence-item__heading strong\s*\{([^}]*)\}/u)?.[1] ?? "";
    expect(heading, ".evidence-item__heading strong is missing").toMatch(/font-size:/u);
    expect(heading).not.toMatch(/\bcolor:/u);

    // No later rule may quietly mute the same element.
    const overrides = [...appCss.matchAll(/\.evidence-item__heading[^{,]*strong[^{]*\{([^}]*)\}/gu)]
      .filter((match) => /\bcolor:/u.test(match[1]));
    expect(overrides.map((match) => match[0])).toEqual([]);
  });

  it("keeps the settled heading readable on the evidence card in both themes", () => {
    const light = tokenBlock(appCss, ":root");
    const dark = tokenBlock(themeCss, ':root[data-theme="dark"]');

    expect(contrast(token(light, "ink-950"), token(light, "surface-warm")))
      .toBeGreaterThanOrEqual(NORMAL_TEXT_RATIO);
    expect(contrast(token(dark, "ink-950"), token(dark, "surface-warm")))
      .toBeGreaterThanOrEqual(NORMAL_TEXT_RATIO);
  });

  it("keeps the heading version tag readable on the same card in both themes", () => {
    expect(appCss).toMatch(/\.evidence-item__heading \.mono\s*\{[^}]*color:\s*var\(--ink-500\);/u);

    const light = tokenBlock(appCss, ":root");
    const dark = tokenBlock(themeCss, ':root[data-theme="dark"]');

    expect(contrast(token(light, "ink-500"), token(light, "surface-warm")))
      .toBeGreaterThanOrEqual(NORMAL_TEXT_RATIO);
    expect(contrast(token(dark, "ink-500"), token(dark, "surface-warm")))
      .toBeGreaterThanOrEqual(NORMAL_TEXT_RATIO);
  });
});
