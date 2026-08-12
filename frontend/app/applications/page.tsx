"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type ApplicationDetail, type ApplicationOut } from "@/lib/api";

const STATUSES = [
  {
    value: "prepared",
    label: "Prepared",
    card: "border-l-slate-400 bg-slate-50/60 dark:bg-slate-900/45",
    control: "border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200",
  },
  {
    value: "applied",
    label: "Applied",
    card: "border-l-sky-500 bg-sky-50/60 dark:bg-sky-950/35",
    control: "border-sky-300 bg-sky-100 text-sky-800 dark:border-sky-700 dark:bg-sky-950 dark:text-sky-200",
  },
  {
    value: "interviewing",
    label: "Interviewing",
    card: "border-l-amber-500 bg-amber-50/60 dark:bg-amber-950/30",
    control: "border-amber-300 bg-amber-100 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200",
  },
  {
    value: "offer",
    label: "Offer",
    card: "border-l-emerald-500 bg-emerald-50/60 dark:bg-emerald-950/30",
    control: "border-emerald-300 bg-emerald-100 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-200",
  },
  {
    value: "rejected",
    label: "Rejected",
    card: "border-l-rose-500 bg-rose-50/60 dark:bg-rose-950/30",
    control: "border-rose-300 bg-rose-100 text-rose-800 dark:border-rose-700 dark:bg-rose-950 dark:text-rose-200",
  },
  {
    value: "withdrawn",
    label: "Withdrawn",
    card: "border-l-zinc-400 bg-zinc-50/70 dark:bg-zinc-900/45",
    control: "border-zinc-300 bg-zinc-100 text-zinc-700 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-200",
  },
] as const;

const FALLBACK_STATUS = {
  value: "unknown",
  label: "Unknown",
  card: "border-l-slate-400 bg-slate-50/60 dark:bg-slate-900/45",
  control: "border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200",
};

function statusDisplay(status: string) {
  return STATUSES.find((item) => item.value === status) ?? FALLBACK_STATUS;
}

function fitDisplay(application: ApplicationOut) {
  if (
    application.workflow_status === "queued" ||
    application.workflow_status === "running"
  ) {
    return {
      label: "Fit pending",
      style: "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-700 dark:bg-sky-950 dark:text-sky-200",
    };
  }
  if (application.workflow_status === "failed") {
    return {
      label: "Fit unavailable",
      style: "border-slate-200 bg-slate-100 text-slate-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200",
    };
  }

  const level = application.fit_match_level.trim().toLowerCase();
  if (level === "strong") {
    return {
      label: "Strong fit",
      style: "border-emerald-200 bg-emerald-100 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-200",
    };
  }
  if (level === "moderate") {
    return {
      label: "Moderate fit",
      style: "border-amber-200 bg-amber-100 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200",
    };
  }
  if (level === "weak") {
    return {
      label: "Weak fit",
      style: "border-rose-200 bg-rose-100 text-rose-800 dark:border-rose-700 dark:bg-rose-950 dark:text-rose-200",
    };
  }
  if (application.fit_match_level.trim()) {
    return {
      label: `${application.fit_match_level.trim()} fit`,
      style: "border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200",
    };
  }
  return {
    label: "Not rated",
    style: "border-slate-200 bg-slate-100 text-slate-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200",
  };
}

export default function ApplicationsPage() {
  const [rows, setRows] = useState<ApplicationOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    api
      .applications()
      .then(setRows)
      .catch((err) => setError(err instanceof Error ? err.message : "Load failed."))
      .finally(() => setLoading(false));
  }, []);

  const hasActiveWork = rows.some(
    (row) => row.workflow_status === "queued" || row.workflow_status === "running",
  );

  useEffect(() => {
    if (!hasActiveWork) return;
    const timer = window.setInterval(() => {
      api
        .applications()
        .then(setRows)
        .catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [hasActiveWork]);

  useEffect(() => {
    if (detailId === null) return;
    let cancelled = false;
    const load = () =>
      api
        .application(detailId)
        .then((value) => {
          if (!cancelled) setDetail(value);
        })
        .catch((err) => {
          if (!cancelled) {
            setError(err instanceof Error ? err.message : "Could not load details.");
          }
        })
        .finally(() => {
          if (!cancelled) setDetailLoading(false);
        });
    setDetailLoading(true);
    void load();
    const timer = window.setInterval(() => {
      if (detail?.workflow_status === "queued" || detail?.workflow_status === "running") {
        void load();
      }
    }, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [detailId, detail?.workflow_status]);

  const statusCounts = useMemo(
    () =>
      rows.reduce<Record<string, number>>((counts, row) => {
        counts[row.status] = (counts[row.status] ?? 0) + 1;
        return counts;
      }, {}),
    [rows],
  );

  const filteredRows = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return rows.filter((row) => {
      if (statusFilter !== "all" && row.status !== statusFilter) return false;
      if (!normalizedQuery) return true;
      return [row.title, row.company, row.notes]
        .join(" ")
        .toLocaleLowerCase()
        .includes(normalizedQuery);
    });
  }, [query, rows, statusFilter]);

  const usageTotals = useMemo(
    () =>
      rows.reduce(
        (totals, row) => {
          totals.input +=
            row.input_tokens + row.cached_input_tokens + row.cache_write_input_tokens;
          totals.output += row.output_tokens;
          totals.requests += row.llm_requests;
          if (row.estimated_cost_usd !== null) {
            totals.cost += row.estimated_cost_usd;
            totals.priced += 1;
          }
          return totals;
        },
        { input: 0, output: 0, requests: 0, cost: 0, priced: 0 },
      ),
    [rows],
  );

  async function update(id: number, patch: { status?: string; notes?: string }) {
    setError(null);
    try {
      const updated = await api.updateApplication(id, patch);
      setRows((prev) => prev.map((r) => (r.id === id ? updated : r)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed.");
    }
  }

  async function remove(row: ApplicationOut) {
    const name = row.title || row.company || "this application";
    if (!window.confirm(`Remove ${name} from your application tracker?`)) return;

    setError(null);
    setDeletingId(row.id);
    try {
      await api.deleteApplication(row.id);
      setRows((prev) => prev.filter((item) => item.id !== row.id));
      if (detailId === row.id) {
        setDetailId(null);
        setDetail(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Applications</h1>
        <p className="mt-1 text-sm text-muted">
          Every tailored resume you generated, with the version that was sent. Local only.
        </p>
      </header>

      {loading && <p className="text-sm text-muted">Loading…</p>}
      {error && <p className="card border-gold/60 bg-gold/10 p-4 text-sm">{error}</p>}

      {!loading && rows.length > 0 && (
        <section className="card mb-5 p-4" aria-label="API usage">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-bold">API usage tracked by SimplyApply</h2>
              <p className="mt-0.5 text-xs text-muted">
                Exact provider-reported tokens; cost is an estimate for recognized models.
              </p>
            </div>
            <span className="rounded-full bg-brand-tint px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-brand">
              Local metrics
            </span>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <UsageMetric
              label="Total tokens"
              value={formatTokens(usageTotals.input + usageTotals.output)}
            />
            <UsageMetric label="Input" value={formatTokens(usageTotals.input)} />
            <UsageMetric label="Output" value={formatTokens(usageTotals.output)} />
            <UsageMetric
              label="Estimated spend"
              value={usageTotals.priced ? formatUsd(usageTotals.cost) : "Unavailable"}
            />
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-muted">
            Remaining provider credit cannot be read with the normal inference API key.
            Check your provider billing dashboard for the authoritative balance and spend.
          </p>
        </section>
      )}

      {!loading && rows.length > 0 && (
        <section className="card mb-5 p-4" aria-label="Application filters">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <label className="relative block w-full sm:max-w-xs">
              <span className="sr-only">Search applications</span>
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
              >
                <circle cx="11" cy="11" r="7" />
                <path d="m20 20-3.5-3.5" />
              </svg>
              <input
                className="field pl-9"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search company, role, or notes"
              />
            </label>
            <p className="shrink-0 text-xs font-semibold text-muted">
              Showing {filteredRows.length} of {rows.length}
            </p>
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              aria-pressed={statusFilter === "all"}
              onClick={() => setStatusFilter("all")}
              className={`rounded-full border px-3 py-1.5 text-xs font-bold transition ${
                statusFilter === "all"
                  ? "border-solid bg-solid text-on-solid"
                  : "border-line bg-surface text-muted hover:border-ink"
              }`}
            >
              All <span className="ml-1 opacity-70">{rows.length}</span>
            </button>
            {STATUSES.map((status) => {
              const active = statusFilter === status.value;
              return (
                <button
                  key={status.value}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setStatusFilter(status.value)}
                  className={`rounded-full border px-3 py-1.5 text-xs font-bold transition ${
                    status.control
                  } ${active ? "ring-2 ring-current ring-offset-2" : "opacity-75 hover:opacity-100"}`}
                >
                  {status.label}
                  <span className="ml-1 opacity-70">{statusCounts[status.value] ?? 0}</span>
                </button>
              );
            })}
          </div>
        </section>
      )}

      {!loading && rows.length === 0 && (
        <div className="card p-10 text-center">
          <p className="font-bold">Nothing yet</p>
          <p className="mt-1 text-sm text-muted">
            Applications appear here once you tailor a resume for a posting.
          </p>
        </div>
      )}

      {!loading && rows.length > 0 && filteredRows.length === 0 && (
        <div className="card p-10 text-center">
          <p className="font-bold">No matching applications</p>
          <p className="mt-1 text-sm text-muted">
            Try another stage or clear your search.
          </p>
          <button
            type="button"
            className="btn-ghost mt-4 !py-2 !text-sm"
            onClick={() => {
              setQuery("");
              setStatusFilter("all");
            }}
          >
            Clear filters
          </button>
        </div>
      )}

      <ul className="flex flex-col gap-3">
        {filteredRows.map((row) => {
          const status = statusDisplay(row.status);
          const fit = fitDisplay(row);
          const processing =
            row.workflow_status === "queued" || row.workflow_status === "running";
          return (
            <li key={row.id} className={`card relative border-l-4 p-4 ${status.card}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-bold leading-snug">{row.title || row.job_id}</p>
                    <span
                      className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-bold ${fit.style}`}
                      title={row.fit_summary || fit.label}
                    >
                      {fit.label}
                    </span>
                  </div>
                  <p className="text-sm text-muted">
                    {row.company}
                    {" · "}
                    {new Date(row.applied_at).toLocaleDateString()}
                  </p>
                  {row.fit_summary && (
                    <p className="mt-1 max-w-3xl text-xs leading-relaxed text-muted">
                      {row.fit_summary}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <label>
                    <span className="sr-only">Application stage</span>
                    <select
                      className={`field w-auto min-w-32 font-bold capitalize ${status.control}`}
                      value={row.status}
                      onChange={(e) => update(row.id, { status: e.target.value })}
                    >
                      {STATUSES.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    aria-label={`Show tailoring details for ${row.title || row.company || "application"}`}
                    title="Show tailoring details"
                    onClick={() => {
                      setDetail(null);
                      setDetailId(row.id);
                    }}
                    className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-surface text-lg text-muted transition hover:border-brand hover:text-brand"
                  >
                    <svg
                      aria-hidden="true"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      className="h-4 w-4"
                    >
                      <path d="m6 9 6 6 6-6" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    aria-label={`Remove ${row.title || row.company || "application"}`}
                    title="Remove application"
                    disabled={deletingId === row.id}
                    onClick={() => remove(row)}
                    className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-surface text-xl leading-none text-muted transition hover:border-rose-300 hover:bg-rose-50 hover:text-rose-700 dark:hover:bg-rose-950 dark:hover:text-rose-300 disabled:cursor-wait disabled:opacity-50"
                  >
                    <span aria-hidden="true">×</span>
                  </button>
                </div>
              </div>

              <div
                className={`mt-3 rounded-xl border p-3 ${
                  row.workflow_status === "failed"
                    ? "border-rose-200 bg-rose-50 dark:border-rose-800 dark:bg-rose-950/55"
                    : processing
                      ? "border-brand/25 bg-surface/70"
                      : "border-emerald-200 bg-emerald-50/70 dark:border-emerald-800 dark:bg-emerald-950/45"
                }`}
              >
                <div className="flex items-center justify-between gap-3 text-xs">
                  <span className="flex items-center gap-2 font-bold">
                    {processing && (
                      <span className="h-2 w-2 animate-pulse rounded-full bg-brand" />
                    )}
                    {row.workflow_status === "failed"
                      ? "Tailoring failed"
                      : row.workflow_status === "completed"
                        ? "Resume ready"
                        : workflowLabel(row.workflow_step)}
                  </span>
                  <span className="font-semibold text-muted">{row.workflow_progress}%</span>
                </div>
                <p className="mt-1 text-xs text-muted">
                  {row.workflow_error || row.workflow_detail}
                </p>
                {applicationTokens(row) > 0 && (
                  <p className="mt-1 text-[11px] font-semibold text-muted">
                    {formatTokens(applicationTokens(row))} tokens
                    {row.estimated_cost_usd !== null
                      ? ` · ${formatUsd(row.estimated_cost_usd)} estimated`
                      : ""}
                  </p>
                )}
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      row.workflow_status === "failed" ? "bg-rose-500" : "bg-brand"
                    }`}
                    style={{ width: `${Math.max(2, row.workflow_progress)}%` }}
                  />
                </div>
              </div>

              <div className="mt-3 flex flex-wrap gap-2 text-sm">
                {row.docx_url && (
                  <a className="btn-ghost !py-1.5 !text-xs" href={row.docx_url} download>
                    .docx
                  </a>
                )}
                {row.pdf_url && (
                  <a className="btn-ghost !py-1.5 !text-xs" href={row.pdf_url} download>
                    PDF
                  </a>
                )}
                {row.apply_url && (
                  <a
                    className="btn-ghost !py-1.5 !text-xs"
                    href={row.apply_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Posting ↗
                  </a>
                )}
              </div>

              <textarea
                className="field mt-3 min-h-[52px] resize-y"
                placeholder="Notes — recruiter name, follow-up date, interview prep…"
                defaultValue={row.notes}
                onBlur={(e) => {
                  if (e.target.value !== row.notes) {
                    update(row.id, { notes: e.target.value });
                  }
                }}
              />
            </li>
          );
        })}
      </ul>

      {detailId !== null && (
        <ApplicationDetailsModal
          detail={detail}
          loading={detailLoading}
          onClose={() => {
            setDetailId(null);
            setDetail(null);
          }}
        />
      )}
    </div>
  );
}

function workflowLabel(step: string) {
  const labels: Record<string, string> = {
    queued: "Queued",
    scraping: "Scraping job description",
    description_ready: "Job description ready",
    tailoring: "Tailoring resume",
    verifying: "Verifying resume facts",
    ats_review: "Running ATS review",
    rendering: "Rendering resume files",
    completed: "Resume ready",
    failed: "Tailoring failed",
  };
  return labels[step] ?? step.replaceAll("_", " ");
}

function applicationTokens(application: ApplicationOut) {
  return (
    application.input_tokens +
    application.cached_input_tokens +
    application.cache_write_input_tokens +
    application.output_tokens
  );
}

function formatTokens(value: number) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value);
}

function formatUsd(value: number) {
  if (value > 0 && value < 0.01) return `<$0.01`;
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(value);
}

function UsageMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-line bg-page px-3 py-3">
      <p className="text-[10px] font-bold uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 text-lg font-bold tabular-nums">{value}</p>
    </div>
  );
}

function ApplicationDetailsModal({
  detail,
  loading,
  onClose,
}: {
  detail: ApplicationDetail | null;
  loading: boolean;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-scrim/60 p-0 backdrop-blur-md sm:items-center sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label="Tailoring details"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) onClose();
      }}
    >
      <div className="max-h-[90vh] w-full max-w-3xl overflow-hidden rounded-t-[20px] border border-ink/10 bg-surface/90 backdrop-blur-2xl sm:rounded-[20px]">
        <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-bold">
              {detail?.title || "Tailoring details"}
            </h2>
            {detail && <p className="truncate text-sm text-muted">{detail.company}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-line text-lg text-muted hover:border-brand hover:text-brand"
            aria-label="Close tailoring details"
          >
            ×
          </button>
        </header>

        <div className="max-h-[calc(90vh-78px)] overflow-y-auto px-6 py-5">
          {loading && !detail && <p className="text-sm text-muted">Loading details…</p>}
          {detail && (
            <>
              <section>
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-bold">Live tailoring progress</h3>
                  <span className="rounded-full bg-brand-tint px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-brand">
                    {detail.workflow_progress}%
                  </span>
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-page">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      detail.workflow_status === "failed" ? "bg-rose-500" : "bg-brand"
                    }`}
                    style={{ width: `${Math.max(2, detail.workflow_progress)}%` }}
                  />
                </div>
                <ol className="mt-4 space-y-3">
                  {detail.progress_events.map((event, index) => (
                    <li key={`${event.at}-${index}`} className="flex gap-3 text-sm">
                      <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand" />
                      <div>
                        <p className="font-bold">{workflowLabel(event.step)}</p>
                        <p className="text-muted">{event.detail}</p>
                        <time className="text-[11px] text-muted">
                          {new Date(event.at).toLocaleTimeString()}
                        </time>
                      </div>
                    </li>
                  ))}
                </ol>
                {detail.workflow_error && (
                  <p className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950/55 dark:text-rose-200">
                    {detail.workflow_error}
                  </p>
                )}
              </section>

              <section className="mt-6 border-t border-line pt-5">
                <h3 className="text-sm font-bold">Scraped job description</h3>
                <div className="mt-3 max-h-72 overflow-y-auto whitespace-pre-wrap rounded-xl border border-line bg-page p-4 text-xs leading-relaxed text-muted">
                  {detail.description ||
                    (detail.workflow_step === "scraping"
                      ? "The employer page is being read now…"
                      : "No job description has been extracted yet.")}
                </div>
              </section>

              <section className="mt-6 border-t border-line pt-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-bold">API usage for this resume</h3>
                  {(detail.llm_provider || detail.llm_model) && (
                    <span className="rounded-full border border-line bg-page px-2.5 py-1 text-[10px] font-bold text-muted">
                      {[detail.llm_provider, detail.llm_model].filter(Boolean).join(" · ")}
                    </span>
                  )}
                </div>
                {applicationTokens(detail) > 0 ? (
                  <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <UsageMetric
                      label="Input"
                      value={formatTokens(
                        detail.input_tokens +
                          detail.cached_input_tokens +
                          detail.cache_write_input_tokens,
                      )}
                    />
                    <UsageMetric label="Output" value={formatTokens(detail.output_tokens)} />
                    <UsageMetric label="Requests" value={formatTokens(detail.llm_requests)} />
                    <UsageMetric
                      label="Estimated cost"
                      value={
                        detail.estimated_cost_usd === null
                          ? "Unavailable"
                          : formatUsd(detail.estimated_cost_usd)
                      }
                    />
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-muted">
                    {detail.workflow_status === "queued" || detail.workflow_status === "running"
                      ? "Token totals will appear as model calls finish."
                      : "No token metrics were recorded for this older application."}
                  </p>
                )}
                {(detail.cached_input_tokens > 0 ||
                  detail.cache_write_input_tokens > 0 ||
                  detail.reasoning_tokens > 0) && (
                  <p className="mt-2 text-[11px] text-muted">
                    Cached input: {formatTokens(detail.cached_input_tokens)} · Cache writes:{" "}
                    {formatTokens(detail.cache_write_input_tokens)} · Reasoning output:{" "}
                    {formatTokens(detail.reasoning_tokens)}
                  </p>
                )}
              </section>

              {detail.tailoring?.ats_review && (
                <section className="mt-6 border-t border-line pt-5">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-sm font-bold">ATS review</h3>
                    <span className="rounded-full border border-brand/30 bg-brand-tint px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-brand">
                      {detail.tailoring.ats_review.match_level} match
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-muted">
                    {detail.tailoring.ats_review.summary}
                  </p>
                  {detail.tailoring.ats_review.suggested_changes.length > 0 && (
                    <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">
                      {detail.tailoring.ats_review.suggested_changes.map((change, index) => (
                        <li key={index}>{change}</li>
                      ))}
                    </ul>
                  )}
                </section>
              )}

              {detail.workflow_status === "completed" && (
                <div className="mt-6 flex flex-wrap gap-2 border-t border-line pt-5">
                  {detail.pdf_url && (
                    <a className="btn-primary" href={detail.pdf_url} download>
                      Download PDF
                    </a>
                  )}
                  {detail.docx_url && (
                    <a className="btn-ghost" href={detail.docx_url} download>
                      Download .docx
                    </a>
                  )}
                  {detail.apply_url && (
                    <a
                      className="btn-ghost"
                      href={detail.apply_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Open posting ↗
                    </a>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
