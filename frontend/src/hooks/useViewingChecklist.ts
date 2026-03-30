import { useState, useCallback, useMemo } from "react";
import { VIEWING_CHECKLIST } from "../data/viewingChecklist";

function storageKey(listingUrl: string): string {
  return `openclaw-viewing-${listingUrl}`;
}

function loadChecked(listingUrl: string): Set<string> {
  try {
    const raw = localStorage.getItem(storageKey(listingUrl));
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    if (Array.isArray(arr)) return new Set(arr as string[]);
  } catch {
    // corrupted data — start fresh
  }
  return new Set();
}

function saveChecked(listingUrl: string, checked: Set<string>) {
  localStorage.setItem(storageKey(listingUrl), JSON.stringify([...checked]));
}

export function useViewingChecklist(listingUrl: string) {
  const [checked, setChecked] = useState<Set<string>>(() => loadChecked(listingUrl));

  const toggle = useCallback(
    (itemId: string) => {
      setChecked((prev) => {
        const next = new Set(prev);
        if (next.has(itemId)) {
          next.delete(itemId);
        } else {
          next.add(itemId);
        }
        saveChecked(listingUrl, next);
        return next;
      });
    },
    [listingUrl],
  );

  const isChecked = useCallback((itemId: string) => checked.has(itemId), [checked]);

  const checkedCount = useCallback(
    (categoryTitle: string) => {
      const category = VIEWING_CHECKLIST.find((c) => c.title === categoryTitle);
      if (!category) return 0;
      return category.items.filter((item) => checked.has(item.id)).length;
    },
    [checked],
  );

  const totalCount = useCallback((categoryTitle: string) => {
    const category = VIEWING_CHECKLIST.find((c) => c.title === categoryTitle);
    return category ? category.items.length : 0;
  }, []);

  const totalChecked = useMemo(() => checked.size, [checked]);
  const totalItems = useMemo(
    () => VIEWING_CHECKLIST.reduce((sum, cat) => sum + cat.items.length, 0),
    [],
  );

  return { toggle, isChecked, checkedCount, totalCount, totalChecked, totalItems };
}

/** Quickly read checked count for a listing without the full hook (for badge indicators). */
export function getChecklistProgress(listingUrl: string): number {
  return loadChecked(listingUrl).size;
}
