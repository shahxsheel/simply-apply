"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  api,
  type SimplifyTrackerJob,
  type SimplifyTrackerResponse,
} from "@/lib/api";

const ALL_CATEGORIES = "All roles";

function ageWeight(age: string): number {
  const value = Number.parseInt(age, 10);
  if (!Number.isFinite(value)) return Number.MAX_SAFE_INTEGER;
  if (age.endsWith("h")) return value / 24;
  if (age.endsWith("d")) return value;
  if (age.endsWith("mo")) return value * 30;
  return value;
}

export default function SimplifyTrackerPage() {
  const [data, setData] = useState<SimplifyTrackerResponse | null>(null);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(ALL_CATEGORIES);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasResume, setHasResume] = useState<boolean | null>(null);
  const [applyingId, setApplyingId] = useState<string | null>(null);
  const [trackedJobIds, setTrackedJobIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    api
      .baseResume()
      .then((resume) => setHasResume(Boolean(resume)))
      .catch(() => setHasResume(false));
    api
      .applications()
      .then((applications) =>
        setTrackedJobIds(new Set(applications.map((application) => application.job_id))),
      )
      .catch(() => undefined);
    api
      .simplifyTracker()
      .then(setData)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load the tracker."),
      )
      .finally(() => setLoading(false));
  }, []);

  async function handleTailor(job: SimplifyTrackerJob) {
    setApplyingId(job.id);
    setError(null);
    try {
      await api.startTailoring({
        job_id: job.id,
        source: "simplify_tracker",
        title: job.role,
        company: job.company,
        location: job.location,
        remote: job.remote,
        apply_url: job.apply_url,
      });
      setTrackedJobIds((previous) => new Set(previous).add(job.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start tailoring this role.");
    } finally {
      setApplyingId(null);
    }
  }

  const categories = useMemo(() => {
    if (!data) return [];
    const counts = new Map<string, number>();
    for (const job of data.jobs) {
      counts.set(job.category, (counts.get(job.category) ?? 0) + 1);
    }
    return [...counts.entries()].sort(([left], [right]) => left.localeCompare(right));
  }, [data]);

  const jobs = useMemo(() => {
    if (!data) return [];
    const terms = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
    return data.jobs
      .filter((job) => category === ALL_CATEGORIES || job.category === category)
      .filter((job) => {
        if (!terms.length) return true;
        const text = `${job.company} ${job.role} ${job.location} ${job.category}`.toLocaleLowerCase();
        return terms.every((term) => text.includes(term));
      })
      .sort((left, right) => ageWeight(left.age) - ageWeight(right.age));
  }, [category, data, query]);

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <span className="rounded-full bg-brand-tint px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-brand">
              Summer 2027
            </span>
            <span className="text-xs text-muted">Updated from GitHub</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight">Simplify Job Tracker</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Fresh internship links from the public SimplifyJobs and Pitt CSC tracker,
            sorted with the newest openings first.
          </p>
        </div>
        {data && (
          <a
            href={data.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-ghost shrink-0"
          >
            View source ↗
          </a>
        )}
      </header>

      {error && (
        <div className="card mb-5 border-gold/60 bg-gold/10 p-4 text-sm">{error}</div>
      )}

      {hasResume === false && (
        <div className="card mb-5 flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm">
            <span className="font-bold">Upload a resume to tailor tracker roles.</span>{" "}
            <span className="text-muted">Direct application links still work without one.</span>
          </p>
          <Link href="/resume" className="btn-primary shrink-0">
            Upload resume
          </Link>
        </div>
      )}

      {loading && (
        <div className="card p-8 text-center text-sm text-muted">
          Loading the latest Summer 2027 openings…
        </div>
      )}

      {data && (
        <>
          {(data.warning || data.stale) && (
            <div className="card mb-5 border-gold/60 bg-gold/10 p-4 text-sm">
              {data.warning ?? "Showing a cached tracker snapshot."}
            </div>
          )}

          <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <input
              className="field max-w-xl"
              type="search"
              placeholder="Filter by company, role, technology, or location"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <p className="shrink-0 text-xs text-muted">
              {jobs.length} of {data.total} open role{data.total === 1 ? "" : "s"}
            </p>
          </div>

          <div className="grid items-start gap-5 lg:grid-cols-[230px_minmax(0,1fr)]">
            <aside className="card sticky top-5 hidden p-3 lg:block">
              <p className="px-3 pb-2 pt-1 text-xs font-bold uppercase tracking-wide text-muted">
                Categories
              </p>
              <CategoryButton
                label={ALL_CATEGORIES}
                count={data.total}
                active={category === ALL_CATEGORIES}
                onClick={() => setCategory(ALL_CATEGORIES)}
              />
              {categories.map(([label, count]) => (
                <CategoryButton
                  key={label}
                  label={label}
                  count={count}
                  active={category === label}
                  onClick={() => setCategory(label)}
                />
              ))}
              <p className="mt-3 border-t border-line px-3 pt-3 text-[11px] leading-relaxed text-muted">
                Direct application links are preferred. Listings are cached for 15
                minutes to avoid repeatedly hitting GitHub.
              </p>
            </aside>

            <div>
              <select
                className="field mb-4 lg:hidden"
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                aria-label="Filter by category"
              >
                <option>{ALL_CATEGORIES}</option>
                {categories.map(([label]) => (
                  <option key={label}>{label}</option>
                ))}
              </select>

              <ul className="grid gap-3 xl:grid-cols-2">
                {jobs.map((job) => (
                  <TrackerCard
                    key={job.id}
                    job={job}
                    hasResume={Boolean(hasResume)}
                    applying={applyingId === job.id}
                    tracked={trackedJobIds.has(job.id)}
                    onTailor={() => handleTailor(job)}
                  />
                ))}
              </ul>
              {jobs.length === 0 && (
                <div className="card p-8 text-center text-sm text-muted">
                  No tracker listings match those filters.
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function CategoryButton({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className={`flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm font-semibold transition-colors ${
        active ? "bg-brand-tint text-brand" : "text-muted hover:bg-page hover:text-ink"
      }`}
      onClick={onClick}
    >
      <span>{label}</span>
      <span className="text-xs font-normal">{count}</span>
    </button>
  );
}

function TrackerCard({
  job,
  hasResume,
  applying,
  tracked,
  onTailor,
}: {
  job: SimplifyTrackerJob;
  hasResume: boolean;
  applying: boolean;
  tracked: boolean;
  onTailor: () => void;
}) {
  return (
    <li className="card flex min-h-52 flex-col p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-bold text-brand">{job.company}</p>
          <h2 className="mt-1 font-bold leading-snug">{job.role}</h2>
        </div>
        {job.age && (
          <span className="shrink-0 rounded-full bg-brand-tint px-2 py-1 text-[10px] font-bold text-brand">
            {job.age} ago
          </span>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5 text-xs text-muted">
        {job.location && <span>{job.location}</span>}
        {job.remote && (
          <span className="rounded-full bg-brand-teal/30 px-2 py-0.5 font-semibold text-ink">
            Remote
          </span>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <span className="rounded-full border border-line px-2 py-0.5 text-[10px] text-muted">
          {job.category}
        </span>
        {job.flags.map((flag) => (
          <span
            key={flag}
            className="rounded-full border border-gold/50 bg-gold/10 px-2 py-0.5 text-[10px] text-ink"
          >
            {flag}
          </span>
        ))}
      </div>

      <div className="mt-auto flex flex-wrap gap-2 pt-5">
        {tracked ? (
          <Link className="btn-primary" href="/applications">
            Track progress →
          </Link>
        ) : (
          <button
            className="btn-primary"
            disabled={!hasResume || applying}
            title={hasResume ? undefined : "Upload a resume first"}
            onClick={onTailor}
          >
            {applying ? "Adding to tracker…" : "Tailor resume"}
          </button>
        )}
        <a
          className="btn-ghost"
          href={job.apply_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          View posting ↗
        </a>
      </div>
    </li>
  );
}
