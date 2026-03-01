import type { ConstraintsMeta } from "../types/chat";

type Props = {
  constraints: ConstraintsMeta;
  onRemove: (clearFields: string[], actionLabel: string) => void;
};

type FieldConfig = {
  label: (value: unknown) => string | null;
  clearFields: string[];   // backend AgentState field names to clear
  actionLabel: string;     // shown as assistant acknowledgment
};

function formatBedrooms(value: unknown): string | null {
  const arr = Array.isArray(value) ? value.map(Number).filter(v => !isNaN(v)) : [];
  if (arr.length === 0) return null;
  const min = Math.min(...arr);
  const max = Math.max(...arr);
  if (min === 0 && max === 0) return "Studio";
  const label = (n: number) => n === 1 ? "1 bed" : `${n} beds`;
  if (min === max) return label(min);
  return `${min}–${max} beds`;
}

function formatFurnishing(value: unknown): string | null {
  const v = Array.isArray(value) ? value.join(", ") : String(value ?? "");
  if (!v.trim()) return null;
  return v.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function formatAvailableFrom(value: unknown): string | null {
  const s = String(value ?? "").trim();
  if (!s) return null;
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return "From " + d.toLocaleDateString("en-GB", { month: "short", year: "numeric" });
}

const FIELD_CONFIG: Record<string, FieldConfig> = {
  budget: {
    label: (v) => (v ? String(v) : null),
    clearFields: ["max_rent_pcm"],
    actionLabel: "Removing budget filter…",
  },
  location: {
    label: (v) => {
      const arr = Array.isArray(v) ? v : [v];
      const parts = arr.map(String).filter(Boolean);
      return parts.length ? parts.join(", ") : null;
    },
    clearFields: ["location_keywords"],
    actionLabel: "Removing location filter…",
  },
  bedrooms: {
    label: formatBedrooms,
    clearFields: ["layout_options"],
    actionLabel: "Removing bedroom filter…",
  },
  furnish_type: {
    label: formatFurnishing,
    clearFields: ["furnish_type"],
    actionLabel: "Removing furnishing filter…",
  },
  let_type: {
    label: (v) => formatFurnishing(v),
    clearFields: ["let_type"],
    actionLabel: "Removing let type filter…",
  },
  available_from: {
    label: formatAvailableFrom,
    clearFields: ["available_from"],
    actionLabel: "Removing availability filter…",
  },
  min_tenancy_months: {
    label: (v) => {
      const n = Number(v);
      return isNaN(n) || n === 0 ? null : `${n} month min tenancy`;
    },
    clearFields: ["min_tenancy_months"],
    actionLabel: "Removing tenancy filter…",
  },
};

export default function ConstraintTags({ constraints, onRemove }: Props) {
  const entries = Object.entries(constraints).flatMap(([key, value]) => {
    const config = FIELD_CONFIG[key];
    const display = config
      ? config.label(value)
      : (() => {
          if (value == null) return null;
          if (Array.isArray(value)) return value.length ? value.join(", ") : null;
          return String(value);
        })();
    if (!display) return [];
    const clearFields = config?.clearFields ?? [key];
    const actionLabel = config?.actionLabel ?? `Removing ${key} filter…`;
    return [{ key, display, clearFields, actionLabel }];
  });

  if (entries.length === 0) return null;

  return (
    <div className="sticky top-0 z-10 flex flex-wrap gap-2 border-b border-border bg-surface/90 px-4 py-2 backdrop-blur">
      {entries.map(({ key, display, clearFields, actionLabel }) => (
        <span
          key={key}
          className="inline-flex items-center gap-1 rounded-full bg-neutral-700 px-2.5 py-1 text-xs text-text"
        >
          {display}
          <button
            onClick={() => onRemove(clearFields, actionLabel)}
            className="ml-0.5 text-muted hover:text-text"
            title={`Remove ${display}`}
          >
            &times;
          </button>
        </span>
      ))}
    </div>
  );
}
