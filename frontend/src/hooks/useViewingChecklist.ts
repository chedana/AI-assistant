import { useState, useCallback, useMemo } from "react";
import { viewingChecklist, totalChecklistItems } from "../data/viewingChecklist";

function storageKey(listingUrl: string) {
  return `openclaw-viewing-${encodeURIComponent(listingUrl)}`;
}

function loadChecked(listingUrl: string): Set<string> {
  try {
    const raw = localStorage.getItem(storageKey(listingUrl));
    if (!raw) return new Set();
    const arr = JSON.parse(raw) as string[];
    return new Set(Array.isArray(arr) ? arr : []);
  } catch {
    return new Set();
  }
}

function saveChecked(listingUrl: string, checked: Set<string>) {
  if (checked.size === 0) {
    localStorage.removeItem(storageKey(listingUrl));
  } else {
    localStorage.setItem(storageKey(listingUrl), JSON.stringify([...checked]));
  }
}

export function useViewingChecklist(listingUrl: string) {
  const [checked, setChecked] = useState<Set<string>>(() => loadChecked(listingUrl));

  const toggle = useCallback(
    (id: string) => {
      setChecked((prev) => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        saveChecked(listingUrl, next);
        return next;
      });
    },
    [listingUrl],
  );

  const isChecked = useCallback((id: string) => checked.has(id), [checked]);

  const checkedCount = useCallback(
    (categoryTitle: string) => {
      const cat = viewingChecklist.find((c) => c.title === categoryTitle);
      if (!cat) return 0;
      return cat.items.filter((item) => checked.has(item.id)).length;
    },
    [checked],
  );

  const totalItems = totalChecklistItems;

  const totalChecked = useMemo(() => checked.size, [checked]);

  return { checked, toggle, isChecked, checkedCount, totalItems, totalChecked };
}

/** Quick check: does a listing have any items checked? (no hook needed) */
export function hasChecklistProgress(listingUrl: string): boolean {
  try {
    const raw = localStorage.getItem(storageKey(listingUrl));
    if (!raw) return false;
    const arr = JSON.parse(raw) as string[];
    return Array.isArray(arr) && arr.length > 0;
  } catch {
    return false;
  }
}
