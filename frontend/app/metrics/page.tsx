"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  buildApplicationMetrics,
  type DailyApplicationMetric,
  type MetricStatus,
  type MetricsRange,
} from "@/lib/applicationMetrics";
import { api, type ApplicationOut } from "@/lib/api";

const RANGES: MetricsRange[] = [7, 30, 90];

const STATUS_STYLES: Array<{
  value: MetricStatus;
  label: string;
  color: string;
  dot: string;
}> = [
  { value: "prepared", label: "Prepared", color: "bg-slate-400", dot: "bg-slate-400" },
  { value: "applied", label: "Applied", color: "bg-sky-500", dot: "bg-sky-500" },
  {
    value: "interviewing",
    label: "Interviewing",
    color: "bg-amber-500",
    dot: "bg-amber-500",
  },
  { value: "offer", label: "Offer", color: "bg-emerald-500", dot: "bg-emerald-500" },
  { value: "rejected", label: "Rejected", color: "bg-rose-500", dot: "bg-rose-500" },
  { value: "withdrawn", label: "Withdrawn", color: "bg-zinc-500", dot: "bg-zinc-500" },
];

export default function MetricsPage() {
  const [applications, setApplications] = useState<ApplicationOut[]>([]);
  const [range, setRange] = useState<MetricsRange>(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .applications()
      .then(setApplications)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load metrics."),
      )
      .finally(() => setLoading(false));
  }, []);

  const metrics = useMemo(
    () => buildApplicationMetrics(applications, range),
    [applications, range],
  );

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-6 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-muted">
            Application intelligence
          </p>
          <h1>Metrics</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
            See your daily application pace and the current outcomes of the roles you
            created during each period.
          </p>
        </div>
        <div
          className="flex w-fit rounded-full border border-line bg-surface/70 p-1 backdrop-blur-xl"
          aria-label="Metrics date range"
        >
          {RANGES.map((days) => (
            <button
              key={days}
              type="button"
              aria-pressed={range === days}
              onClick={() => setRange(days)}
              className={`rounded-full px-3.5 py-2 text-xs font-bold transition ${
                range === days ? "bg-solid text-on-solid" : "text-muted hover:text-ink"
              }`}
            >
              {days} days
            </button>
          ))}
        </div>
      </header>

      {loading && <MetricsSkeleton />}
      {error && (
        <div className="card border-gold/60 bg-gold/10 p-5 text-sm" role="alert">
          <p className="font-bold">Metrics could not be loaded</p>
          <p className="mt-1 text-muted">{error}</p>
        </div>
      )}

      {!loading && !error && applications.length === 0 && <EmptyMetrics />}

      {!loading && !error && applications.length > 0 && (
        <>
          <section
            className="grid grid-cols-2 gap-3 lg:grid-cols-5"
            aria-label="Application metric summary"
          >
            <MetricCard
              eyebrow={`Last ${range} days`}
              label="Applications"
              value={formatNumber(metrics.total)}
              detail={`${metrics.dailyAverage.toFixed(1)} per day`}
              accent="bg-sky-500"
            />
            <MetricCard
              eyebrow="Current stage"
              label="Applied"
              value={formatNumber(metrics.statuses.applied)}
              detail={`${percentage(metrics.statuses.applied, metrics.total)} of cohort`}
              accent="bg-sky-500"
            />
            <MetricCard
              eyebrow="Current stage"
              label="Interviewing"
              value={formatNumber(metrics.statuses.interviewing)}
              detail={`${percentage(metrics.statuses.interviewing, metrics.total)} of cohort`}
              accent="bg-amber-500"
            />
            <MetricCard
              eyebrow="Current outcome"
              label="Offers"
              value={formatNumber(metrics.statuses.offer)}
              detail={`${percentage(metrics.statuses.offer, metrics.total)} of cohort`}
              accent="bg-emerald-500"
            />
            <MetricCard
              eyebrow="Current outcome"
              label="Rejections"
              value={formatNumber(metrics.statuses.rejected)}
              detail={`${percentage(metrics.statuses.rejected, metrics.total)} of cohort`}
              accent="bg-rose-500"
              className="col-span-2 sm:col-span-1"
            />
          </section>

          <section className="card mt-5 overflow-hidden p-5 sm:p-6" aria-labelledby="pace-title">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h2 id="pace-title" className="text-lg font-bold">
                  Daily application pace
                </h2>
                <p className="mt-1 text-xs leading-relaxed text-muted">
                  Each bar is grouped by application date and colored by its current stage.
                </p>
              </div>
              <div className="flex flex-wrap gap-x-3 gap-y-2" aria-label="Status legend">
                {STATUS_STYLES.map((status) => (
                  <span key={status.value} className="flex items-center gap-1.5 text-[11px] text-muted">
                    <span className={`h-2 w-2 rounded-full ${status.dot}`} aria-hidden="true" />
                    {status.label}
                  </span>
                ))}
              </div>
            </div>

            <DailyChart days={metrics.days} />

            <div className="mt-5 grid gap-3 border-t border-line pt-5 sm:grid-cols-3">
              <Insight
                label="Busiest day"
                value={
                  metrics.busiestDay
                    ? `${shortDate(metrics.busiestDay.date)} · ${pluralize(metrics.busiestDay.total, "application")}`
                    : "No activity yet"
                }
              />
              <Insight
                label="Active pipeline"
                value={`${pluralize(metrics.activePipeline, "application")} applied or interviewing`}
              />
              <Insight
                label="Rejection rate"
                value={
                  metrics.rejectionRate === null
                    ? "Not enough data"
                    : `${metrics.rejectionRate.toFixed(0)}% of decided outcomes`
                }
              />
            </div>
          </section>

          <section className="mt-5 grid gap-5 lg:grid-cols-[0.8fr_1.2fr]">
            <StatusBreakdown metrics={metrics.statuses} total={metrics.total} />
            <DailyDetail days={metrics.days} />
          </section>

          <p className="mt-5 text-xs leading-relaxed text-muted">
            Statuses are a current snapshot, not a status-change timeline. For example, a
            rejection appears on the date the application was created because SimplyApply
            does not yet store the day that status changed.
          </p>
        </>
      )}
    </div>
  );
}

function DailyChart({ days }: { days: DailyApplicationMetric[] }) {
  const max = Math.max(1, ...days.map((day) => day.total));
  const labelInterval = Math.max(1, Math.ceil(days.length / 7));

  return (
    <div className="mt-6">
      <div
        className="grid h-56 items-end gap-1 border-b border-line sm:gap-1.5"
        style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}
        role="img"
        aria-label={`Daily applications over ${days.length} days. Highest daily total is ${max}.`}
      >
        {days.map((day) => (
          <div
            key={day.key}
            className="group relative flex h-full items-end"
            title={`${longDate(day.date)}: ${pluralize(day.total, "application")}`}
          >
            <div
              className="flex w-full min-w-[2px] flex-col-reverse overflow-hidden rounded-t-sm bg-surface-soft transition-opacity group-hover:opacity-80"
              style={{ height: day.total === 0 ? "2px" : `${Math.max(4, (day.total / max) * 100)}%` }}
            >
              {STATUS_STYLES.map((status) =>
                day.statuses[status.value] > 0 ? (
                  <span
                    key={status.value}
                    className={`block w-full ${status.color}`}
                    style={{ flex: day.statuses[status.value] }}
                  />
                ) : null,
              )}
            </div>
          </div>
        ))}
      </div>
      <div
        className="mt-2 grid gap-1 text-[9px] font-semibold text-muted"
        style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}
        aria-hidden="true"
      >
        {days.map((day, index) => (
          <span key={day.key} className="truncate text-center">
            {index % labelInterval === 0 || index === days.length - 1
              ? day.date.toLocaleDateString(undefined, { month: "short", day: "numeric" })
              : ""}
          </span>
        ))}
      </div>
    </div>
  );
}

function StatusBreakdown({
  metrics,
  total,
}: {
  metrics: Record<MetricStatus, number>;
  total: number;
}) {
  return (
    <section className="card p-5 sm:p-6" aria-labelledby="status-title">
      <h2 id="status-title" className="text-lg font-bold">
        Status mix
      </h2>
      <p className="mt-1 text-xs text-muted">Current stage of applications in this cohort.</p>
      <div className="mt-5 space-y-4">
        {STATUS_STYLES.map((status) => {
          const count = metrics[status.value];
          return (
            <div key={status.value}>
              <div className="mb-1.5 flex items-center justify-between gap-3 text-xs">
                <span className="flex items-center gap-2 font-semibold">
                  <span className={`h-2 w-2 rounded-full ${status.dot}`} aria-hidden="true" />
                  {status.label}
                </span>
                <span className="tabular-nums text-muted">
                  {count} · {percentage(count, total)}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-surface-soft">
                <div
                  className={`h-full rounded-full ${status.color}`}
                  style={{ width: total === 0 ? 0 : `${(count / total) * 100}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function DailyDetail({ days }: { days: DailyApplicationMetric[] }) {
  const recent = days.slice(-7).reverse();
  return (
    <section className="card overflow-hidden" aria-labelledby="daily-detail-title">
      <div className="p-5 pb-4 sm:px-6">
        <h2 id="daily-detail-title" className="text-lg font-bold">
          Daily detail
        </h2>
        <p className="mt-1 text-xs text-muted">The most recent seven days in this view.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[40rem] border-collapse text-left text-xs">
          <thead className="border-y border-line bg-surface-soft/70 text-[10px] uppercase tracking-wide text-muted">
            <tr>
              <th className="px-5 py-3 font-bold sm:pl-6">Date</th>
              <th className="px-3 py-3 text-right font-bold">Applications</th>
              <th className="px-3 py-3 text-right font-bold">Applied</th>
              <th className="px-3 py-3 text-right font-bold">Interviewing</th>
              <th className="px-3 py-3 text-right font-bold">Offers</th>
              <th className="px-5 py-3 text-right font-bold sm:pr-6">Rejected</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {recent.map((day) => (
              <tr key={day.key}>
                <th className="px-5 py-3.5 font-semibold sm:pl-6">{longDate(day.date)}</th>
                <td className="px-3 py-3.5 text-right font-bold tabular-nums">{day.total}</td>
                <td className="px-3 py-3.5 text-right tabular-nums text-sky-700 dark:text-sky-300">
                  {day.statuses.applied}
                </td>
                <td className="px-3 py-3.5 text-right tabular-nums text-amber-700 dark:text-amber-300">
                  {day.statuses.interviewing}
                </td>
                <td className="px-3 py-3.5 text-right tabular-nums text-emerald-700 dark:text-emerald-300">
                  {day.statuses.offer}
                </td>
                <td className="px-5 py-3.5 text-right tabular-nums text-rose-700 dark:text-rose-300 sm:pr-6">
                  {day.statuses.rejected}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MetricCard({
  eyebrow,
  label,
  value,
  detail,
  accent,
  className = "",
}: {
  eyebrow: string;
  label: string;
  value: string;
  detail: string;
  accent: string;
  className?: string;
}) {
  return (
    <article className={`card relative overflow-hidden p-4 sm:p-5 ${className}`}>
      <span className={`absolute inset-x-0 top-0 h-1 ${accent}`} aria-hidden="true" />
      <p className="text-[9px] font-bold uppercase tracking-[0.14em] text-muted">{eyebrow}</p>
      <p className="mt-3 text-3xl font-semibold tracking-[-0.04em] tabular-nums">{value}</p>
      <h2 className="mt-1 text-sm font-bold">{label}</h2>
      <p className="mt-1 text-[11px] text-muted">{detail}</p>
    </article>
  );
}

function Insight({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[9px] font-bold uppercase tracking-[0.14em] text-muted">{label}</p>
      <p className="mt-1 text-sm font-semibold">{value}</p>
    </div>
  );
}

function EmptyMetrics() {
  return (
    <section className="card overflow-hidden p-8 text-center sm:p-12">
      <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-brand-tint text-brand">
        <ChartIcon />
      </div>
      <h2 className="mt-5 text-lg font-bold">Your metrics will grow with your tracker</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted">
        Tailor your first application, then update its stage from Applications to see daily
        pace, interviews, offers, and rejections here.
      </p>
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        <Link className="btn-primary" href="/quick-apply">
          Start an application
        </Link>
        <Link className="btn-ghost" href="/applications">
          View applications
        </Link>
      </div>
    </section>
  );
}

function MetricsSkeleton() {
  return (
    <div className="animate-pulse" aria-label="Loading metrics">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {Array.from({ length: 5 }, (_, index) => (
          <div key={index} className="card h-36 bg-surface/40" />
        ))}
      </div>
      <div className="card mt-5 h-80 bg-surface/40" />
    </div>
  );
}

function ChartIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className="h-7 w-7"
    >
      <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />
      <path d="m3 6 5-3 5 4 7-5" />
    </svg>
  );
}

function percentage(value: number, total: number) {
  return total === 0 ? "0%" : `${Math.round((value / total) * 100)}%`;
}

function pluralize(value: number, noun: string) {
  return `${formatNumber(value)} ${noun}${value === 1 ? "" : "s"}`;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat().format(value);
}

function shortDate(value: Date) {
  return value.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function longDate(value: Date) {
  return value.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}
