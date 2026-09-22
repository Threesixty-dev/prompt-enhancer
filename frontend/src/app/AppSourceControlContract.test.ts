import ts from "typescript";
import { describe, expect, it } from "vitest";

const SOURCE_FILES = import.meta.glob("../**/*.tsx", {
  eager: true,
  import: "default",
  query: "?raw",
}) as Record<string, string>;

function tagName(node: ts.JsxOpeningLikeElement): string {
  return node.tagName.getText();
}

function attribute(
  node: ts.JsxOpeningLikeElement,
  name: string,
): ts.JsxAttribute | undefined {
  return node.attributes.properties.find(
    (property): property is ts.JsxAttribute => (
      ts.isJsxAttribute(property) && property.name.getText() === name
    ),
  );
}

function literalAttributeValue(value: ts.JsxAttribute | undefined): string | null {
  if (value?.initializer && ts.isStringLiteral(value.initializer)) return value.initializer.text;
  return null;
}

function hasStaticDisabledReason(node: ts.JsxOpeningLikeElement): boolean {
  const disabled = attribute(node, "disabled");
  const staticallyDisabled = disabled !== undefined && (
    disabled.initializer === undefined || (
      ts.isJsxExpression(disabled.initializer)
      && disabled.initializer.expression?.kind === ts.SyntaxKind.TrueKeyword
    )
  );
  if (!staticallyDisabled) return false;
  return ["title", "aria-describedby"].some((name) => {
    const reason = literalAttributeValue(attribute(node, name));
    return reason !== null && reason.trim().length !== 0;
  });
}

function hasSemanticButtonAction(node: ts.JsxOpeningLikeElement, insideForm: boolean): boolean {
  const type = literalAttributeValue(attribute(node, "type"));
  return attribute(node, "onClick") !== undefined
    || attribute(node, "formAction") !== undefined
    || type === "submit"
    || type === "reset"
    || (type === null && insideForm)
    // A control the browser cannot activate may represent a deliberately
    // unavailable action, but only when its literal reason is exposed.
    || hasStaticDisabledReason(node);
}

function buttonActionFindings(sourceText: string): string[] {
  const source = ts.createSourceFile("synthetic.tsx", sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const findings: string[] = [];
  const visit = (node: ts.Node, insideForm: boolean): void => {
    const nextInsideForm = insideForm || (
      (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node))
      && tagName(ts.isJsxElement(node) ? node.openingElement : node) === "form"
    );
    if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) {
      const opening = ts.isJsxElement(node) ? node.openingElement : node;
      const hasSpread = opening.attributes.properties.some(ts.isJsxSpreadAttribute);
      if (tagName(opening) === "button" && !hasSpread && !hasSemanticButtonAction(opening, nextInsideForm)) {
        findings.push("button has no click or form action");
      }
    }
    ts.forEachChild(node, (child) => visit(child, nextInsideForm));
  };
  visit(source, false);
  return findings;
}

function hasApprovedErrorRecovery(node: ts.JsxOpeningLikeElement): boolean {
  if (attribute(node, "onRetry") !== undefined) return true;
  return literalAttributeValue(attribute(node, "recovery")) === "preserve-work-before-reload";
}

function errorStateRecoveryFindings(sourceText: string): string[] {
  const source = ts.createSourceFile("synthetic.tsx", sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const findings: string[] = [];
  const visit = (node: ts.Node): void => {
    if ((ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node))) {
      const opening = ts.isJsxElement(node) ? node.openingElement : node;
      if (tagName(opening) === "ErrorState" && !hasApprovedErrorRecovery(opening)) {
        findings.push("error state has no recovery action");
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return findings;
}

function lineOf(source: ts.SourceFile, node: ts.Node): number {
  return source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
}

function isHiddenJsxElement(node: ts.JsxElement | ts.JsxSelfClosingElement): boolean {
  const opening = ts.isJsxElement(node) ? node.openingElement : node;
  return literalAttributeValue(attribute(opening, "aria-hidden")) === "true";
}

function hasPotentialAccessibleContent(node: ts.JsxElement | ts.JsxFragment): boolean {
  return node.children.some((child) => {
    if (ts.isJsxText(child)) return child.text.trim() !== "";
    if (ts.isJsxExpression(child)) return child.expression !== undefined;
    if (ts.isJsxFragment(child)) return hasPotentialAccessibleContent(child);
    if (ts.isJsxElement(child) || ts.isJsxSelfClosingElement(child)) {
      if (isHiddenJsxElement(child)) return false;
      const opening = ts.isJsxElement(child) ? child.openingElement : child;
      if (tagName(opening) === "Icon") return false;
      if (
        attribute(opening, "aria-label") !== undefined
        || attribute(opening, "aria-labelledby") !== undefined
        || attribute(opening, "alt") !== undefined
      ) return true;
      return ts.isJsxElement(child) && hasPotentialAccessibleContent(child);
    }
    return false;
  });
}

describe("static interactive-element contracts", () => {
  it("keeps native buttons and links wired to a semantic action", () => {
    const findings: string[] = [];

    for (const [path, contents] of Object.entries(SOURCE_FILES)) {
      if (path.includes(".test.")) continue;
      const displayPath = path.replace(/^\.\.\//, "");
      const source = ts.createSourceFile(
        path,
        contents,
        ts.ScriptTarget.Latest,
        true,
        ts.ScriptKind.TSX,
      );

      const visit = (node: ts.Node, insideForm: boolean): void => {
        const nextInsideForm = insideForm || (
          (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node))
          && tagName(ts.isJsxElement(node) ? node.openingElement : node) === "form"
        );

        if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) {
          const opening = ts.isJsxElement(node) ? node.openingElement : node;
          const tag = tagName(opening);
          const hasSpread = opening.attributes.properties.some(ts.isJsxSpreadAttribute);

          if (tag === "button" && !hasSpread) {
            if (!hasSemanticButtonAction(opening, nextInsideForm)) {
              findings.push(`${displayPath}:${lineOf(source, opening)} button has no click or form action`);
            }

            if (
              attribute(opening, "aria-label") === undefined
              && attribute(opening, "aria-labelledby") === undefined
              && (!ts.isJsxElement(node) || !hasPotentialAccessibleContent(node))
            ) {
              findings.push(`${displayPath}:${lineOf(source, opening)} button has no potential accessible name`);
            }

            const disabled = attribute(opening, "disabled");
            if (
              disabled !== undefined
              && disabled.initializer === undefined
              && attribute(opening, "aria-describedby") === undefined
              && attribute(opening, "title") === undefined
            ) {
              findings.push(`${displayPath}:${lineOf(source, opening)} permanently disabled button has no accessible reason`);
            }
          }

          if (tag === "a" && !hasSpread && attribute(opening, "href") === undefined) {
            findings.push(`${displayPath}:${lineOf(source, opening)} link has no href`);
          }

          if (tag === "ErrorState" && !hasApprovedErrorRecovery(opening)) {
            findings.push(`${displayPath}:${lineOf(source, opening)} error state has no recovery action`);
          }
        }

        ts.forEachChild(node, (child) => visit(child, nextInsideForm));
      };

      visit(source, false);
    }

    expect(findings).toEqual([]);
  });

  it("accepts only the documented literal non-retryable ErrorState recovery mode", () => {
    expect(errorStateRecoveryFindings('<ErrorState message="Synthetic failure" />')).toEqual([
      "error state has no recovery action",
    ]);
    expect(errorStateRecoveryFindings('<ErrorState message="Synthetic failure" recovery="unknown" />')).toEqual([
      "error state has no recovery action",
    ]);
    expect(errorStateRecoveryFindings('<ErrorState message="Synthetic failure" recovery={mode} />')).toEqual([
      "error state has no recovery action",
    ]);
    expect(errorStateRecoveryFindings('<ErrorState message="Synthetic failure" recovery="preserve-work-before-reload" />')).toEqual([]);
    expect(errorStateRecoveryFindings('<ErrorState message="Synthetic failure" onRetry={retry} />')).toEqual([]);
  });

  it("accepts only literal, explained static disabled controls without an action", () => {
    expect(buttonActionFindings('<button disabled title="Unavailable">Cancel</button>')).toEqual([]);
    expect(buttonActionFindings('<button disabled aria-describedby="reason">Cancel</button>')).toEqual([]);
    expect(buttonActionFindings('<button disabled={true} title="Unavailable">Cancel</button>')).toEqual([]);
    expect(buttonActionFindings('<button disabled={false} title="Unavailable">Cancel</button>')).toEqual([
      "button has no click or form action",
    ]);
    expect(buttonActionFindings('<button disabled={blocked} title="Unavailable">Cancel</button>')).toEqual([
      "button has no click or form action",
    ]);
    expect(buttonActionFindings('<button disabled title=" ">Cancel</button>')).toEqual([
      "button has no click or form action",
    ]);
    expect(buttonActionFindings('<button disabled>Cancel</button>')).toEqual([
      "button has no click or form action",
    ]);
    expect(buttonActionFindings('<button title="Unavailable">Cancel</button>')).toEqual([
      "button has no click or form action",
    ]);
  });
});
