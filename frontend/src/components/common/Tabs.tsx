import { useRef, type KeyboardEvent } from "react";

export interface TabItem<T extends string> {
  id: T;
  label: string;
}

interface TabsProps<T extends string> {
  /** Names the tab list for screen readers, e.g. "Main view". */
  label: string;
  tabs: TabItem<T>[];
  selected: T;
  onSelect: (id: T) => void;
  /** Prefix for element ids: tab "chat" gets id `${idPrefix}-tab-chat` and controls `${idPrefix}-panel-chat`. */
  idPrefix: string;
}

/** The id of a tab's panel, for the `id` of the element the tab controls. */
export function tabPanelId(idPrefix: string, tabId: string): string {
  return `${idPrefix}-panel-${tabId}`;
}

/** The id of a tab button, for the panel's aria-labelledby. */
export function tabId(idPrefix: string, id: string): string {
  return `${idPrefix}-tab-${id}`;
}

/**
 * A tab list following the ARIA "tabs" pattern:
 * - only the selected tab is in the Tab order (tabIndex 0, others -1), so
 *   Tab moves past the whole list in one step;
 * - Left/Right arrows (and Home/End) move to another tab and select it.
 */
export function Tabs<T extends string>({ label, tabs, selected, onSelect, idPrefix }: TabsProps<T>) {
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    const current = tabs.findIndex((tab) => tab.id === selected);
    let next: number;
    if (event.key === "ArrowRight") {
      next = (current + 1) % tabs.length; // wraps from the last tab to the first
    } else if (event.key === "ArrowLeft") {
      next = (current - 1 + tabs.length) % tabs.length;
    } else if (event.key === "Home") {
      next = 0;
    } else if (event.key === "End") {
      next = tabs.length - 1;
    } else {
      return;
    }
    event.preventDefault(); // stop the page from scrolling
    onSelect(tabs[next].id);
    buttons.current[next]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={label}
      onKeyDown={handleKeyDown}
      className="flex gap-1 border-b border-gray-200"
    >
      {tabs.map((tab, index) => {
        const isSelected = tab.id === selected;
        return (
          <button
            key={tab.id}
            ref={(element) => {
              buttons.current[index] = element;
            }}
            id={tabId(idPrefix, tab.id)}
            type="button"
            role="tab"
            aria-selected={isSelected}
            aria-controls={tabPanelId(idPrefix, tab.id)}
            tabIndex={isSelected ? 0 : -1}
            onClick={() => onSelect(tab.id)}
            className={`-mb-px border-b-2 px-4 py-2 ${
              isSelected ? "border-blue-700 font-semibold text-blue-700" : "border-transparent text-gray-600"
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
