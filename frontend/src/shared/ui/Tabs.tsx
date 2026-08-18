import { moveRovingFocus } from "./rovingFocus";

export interface TabDescriptor<Id extends string> {
  id: Id;
  label: string;
  /** Visible secondary text (count, hint); never hover-only. */
  detail?: string;
  /** Optional numeric badge such as an unread count. */
  badge?: number;
  badgeLabel?: string;
}

/**
 * Roving-focus tab strip. Tabs are `role="tab"` buttons inside a labelled
 * `role="tablist"`; the caller renders the matching `role="tabpanel"` with
 * `id={tabPanelId(idPrefix, id)}` and `aria-labelledby={tabId(idPrefix, id)}`.
 * Arrow keys move focus and selection; Tab leaves the strip.
 */
export function tabId(prefix: string, id: string): string {
  return `${prefix}-tab-${id}`;
}

export function tabPanelId(prefix: string, id: string): string {
  return `${prefix}-panel-${id}`;
}

export function TabList<Id extends string>({
  idPrefix,
  label,
  tabs,
  value,
  onChange,
  compact = false,
}: {
  idPrefix: string;
  label: string;
  tabs: readonly TabDescriptor<Id>[];
  value: Id;
  onChange: (id: Id) => void;
  compact?: boolean;
}) {
  return (
    <div
      aria-label={label}
      className={`ui-tabs${compact ? " ui-tabs--compact" : ""}`}
      onKeyDown={(event) => moveRovingFocus(event, (index) => onChange(tabs[index].id))}
      role="tablist"
    >
      {tabs.map((tab) => {
        const selected = tab.id === value;
        return (
          <button
            aria-controls={tabPanelId(idPrefix, tab.id)}
            aria-selected={selected}
            className="ui-tabs__tab"
            id={tabId(idPrefix, tab.id)}
            key={tab.id}
            onClick={() => onChange(tab.id)}
            role="tab"
            tabIndex={selected ? 0 : -1}
            type="button"
          >
            <span>{tab.label}</span>
            {tab.detail !== undefined && <small>{tab.detail}</small>}
            {tab.badge !== undefined && tab.badge > 0 && (
              <span aria-label={tab.badgeLabel ?? `${tab.badge} unread`} className="ui-tabs__badge">{tab.badge}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
