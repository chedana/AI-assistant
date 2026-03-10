import type { ConstraintsMeta } from "../types/chat";

type Props = {
  constraints: ConstraintsMeta;
  onRemove: (clearFields: string[]) => void;
  inline?: boolean;
};

type FieldConfig = {
  label: (value: unknown) => string | null;
  clearFields: string[];   // backend AgentState field names to clear
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
  },
  location: {
    label: (v) => {
      const arr = Array.isArray(v) ? v : [v];
      const parts = arr.map(String).filter(Boolean);
      return parts.length ? parts.join(", ") : null;
    },
    clearFields: ["location_keywords"],
  },
  bedrooms: {
    label: formatBedrooms,
    clearFields: ["layout_options"],
  },
  furnish_type: {
    label: formatFurnishing,
    clearFields: ["furnish_type"],
  },
  let_type: {
    label: (v) => formatFurnishing(v),
    clearFields: ["let_type"],
  },
  available_from: {
    label: formatAvailableFrom,
    clearFields: ["available_from"],
  },
  min_tenancy_months: {
    label: (v) => {
      const n = Number(v);
      return isNaN(n) || n === 0 ? null : `${n} month min tenancy`;
    },
    clearFields: ["min_tenancy_months"],
  },
};

export default function ConstraintTags({ constraints, onRemove, inline }: Props) {
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
    return [{ key, display, clearFields }];
  });

  if (entries.length === 0) return null;

  const chips = entries.map(({ key, display, clearFields }) => (
    <span
      key={key}
      className="inline-flex items-center gap-1 rounded-full bg-neutral-700 px-2.5 py-1 text-xs text-text"
    >
      {display}
      <button
        onClick={() => onRemove(clearFields)}
        className="ml-0.5 text-muted hover:text-text"
        title={`Remove ${display}`}
      >
        &times;
      </button>
    </span>
  ));

  if (inline) return <>{chips}</>;

  return (
    <div className="sticky top-0 z-10 flex flex-wrap gap-2 border-b border-border bg-surface/90 px-4 py-2 backdrop-blur">
      {chips}
    </div>
  );
}
