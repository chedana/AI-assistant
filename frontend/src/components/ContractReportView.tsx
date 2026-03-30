import { useState } from "react";
import type { ContractReport, ClauseFlag } from "../types/chat";

type Props = {
  report: ContractReport;
  onUploadAnother: () => void;
};

const severityStyles: Record<ClauseFlag["severity"], { border: string; bg: string; label: string; labelColor: string }> = {
  info: { border: "border-green-500", bg: "bg-green-500/10", label: "Info", labelColor: "text-green-400" },
  warning: { border: "border-amber-500", bg: "bg-amber-500/10", label: "Warning", labelColor: "text-amber-400" },
  critical: { border: "border-red-500", bg: "bg-red-500/10", label: "Critical", labelColor: "text-red-400" },
};

const complianceIcons: Record<string, { icon: string; color: string }> = {
  pass: { icon: "\u2713", color: "text-green-400" },
  fail: { icon: "\u2717", color: "text-red-400" },
  unknown: { icon: "?", color: "text-muted" },
};

function KeyTerm({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-lg bg-surface px-3 py-2">
      <div className="text-[10px] font-bold uppercase tracking-widest text-muted">{label}</div>
      <div className="mt-0.5 text-sm font-medium text-text">{value ?? "N/A"}</div>
    </div>
  );
}

function ClauseItem({ clause }: { clause: ClauseFlag }) {
  const [expanded, setExpanded] = useState(false);
  const style = severityStyles[clause.severity];

  return (
    <button
      type="button"
      onClick={() => setExpanded(!expanded)}
      className={`w-full text-left rounded-lg border-l-4 ${style.border} ${style.bg} px-4 py-3 transition-colors hover:brightness-110`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`text-[10px] font-bold uppercase ${style.labelColor}`}>{style.label}</span>
          <span className="text-sm text-text">{clause.issue}</span>
        </div>
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`shrink-0 text-muted transition-transform ${expanded ? "rotate-180" : ""}`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>
      {expanded && (
        <div className="mt-3 space-y-2">
          <p className="text-xs italic text-muted">"{clause.clause_text}"</p>
          <p className="text-xs text-text">{clause.advice}</p>
        </div>
      )}
    </button>
  );
}

export default function ContractReportView({ report, onUploadAnother }: Props) {
  return (
    <div className="space-y-6">
      {/* Summary */}
      <div className="rounded-lg border-l-4 border-accent bg-panel p-4">
        <h3 className="text-sm font-bold text-text">Summary</h3>
        <p className="mt-1 text-sm leading-relaxed text-muted">{report.summary}</p>
      </div>

      {/* Key Terms Grid */}
      <div>
        <h3 className="mb-2 text-xs font-bold uppercase tracking-widest text-muted">Key Terms</h3>
        <div className="grid grid-cols-2 gap-2">
          <KeyTerm label="Tenancy Type" value={report.tenancy_type} />
          <KeyTerm label="Rent" value={report.rent} />
          <KeyTerm label="Deposit" value={report.deposit} />
          <KeyTerm label="Notice Period" value={report.notice_period} />
          <KeyTerm label="Break Clause" value={report.break_clause} />
        </div>
      </div>

      {/* Clause Flags */}
      {report.clauses.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-bold uppercase tracking-widest text-muted">
            Flagged Clauses ({report.clauses.length})
          </h3>
          <div className="space-y-2">
            {report.clauses.map((clause, i) => (
              <ClauseItem key={i} clause={clause} />
            ))}
          </div>
        </div>
      )}

      {/* Compliance Checklist */}
      {report.compliance.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-bold uppercase tracking-widest text-muted">Compliance</h3>
          <div className="space-y-1.5">
            {report.compliance.map((item, i) => {
              const style = complianceIcons[item.status] ?? complianceIcons.unknown;
              return (
                <div key={i} className="flex items-start gap-3 rounded-lg bg-surface px-3 py-2">
                  <span className={`mt-0.5 text-sm font-bold ${style.color}`}>{style.icon}</span>
                  <div>
                    <div className="text-sm font-medium text-text">{item.check}</div>
                    <div className="text-xs text-muted">{item.detail}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Disclaimer */}
      {report.disclaimer && (
        <p className="text-xs italic text-muted">{report.disclaimer}</p>
      )}

      {/* Upload Another */}
      <button
        type="button"
        onClick={onUploadAnother}
        className="w-full rounded-lg bg-accent/10 py-2.5 text-sm font-medium text-accent transition-colors hover:bg-accent/20 active:scale-[0.98]"
      >
        Upload another contract
      </button>
    </div>
  );
}
