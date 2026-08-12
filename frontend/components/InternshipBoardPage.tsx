"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, type InternshipBoardResponse, type JobRecord } from "@/lib/api";

type Board = "ashby" | "greenhouse";

type Props = {
  board: Board;
  heading: string;
  description: string;
};

export default function InternshipBoardPage({ board, heading, description }: Props) {
  const [keywords, setKeywords] = useState("");
  const [location, setLocation] = useState("");
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [data, setData] = useState<InternshipBoardResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasResume, setHasResume] = useState<boolean | null>(null);
  const [trackedJobIds, setTrackedJobIds] = useState<Set<string>>(new Set());
  const [tailoringId, setTailoringId] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.baseResume(), api.applications()])
      .then(([resume, applications]) => {
        setHasResume(Boolean(resume));
        setTrackedJobIds(
          new Set(applications.map((application) => application.job_id)),
        );
      })
      .catch(() => setHasResume(false));

    api
      .internshipBoard(board)
      .then((response) => {
        setData(response);
        setSelectedId(response.jobs[0]?.id ?? null);
      })
      .catch((reason) =>
        setError(
          reason instanceof Error ? reason.message : `${heading} could not be loaded.`,
        ),
      )
      .finally(() => setLoading(false));
  }, [board, heading]);

  const jobs = useMemo(() => {
    const terms = keywords.toLowerCase().trim().split(/\s+/).filter(Boolean);
    const locationNeedle = location.toLowerCase().trim();
    return (data?.jobs ?? []).filter((job) => {
      if (remoteOnly && !job.remote) return false;
      if (locationNeedle && !job.location.toLowerCase().includes(locationNeedle)) {
        return false;
      }
      const haystack = `${job.title} ${job.company} ${job.description}`.toLowerCase();
      return terms.every((term) => haystack.includes(term));
    });
  }, [data, keywords, location, remoteOnly]);

  const selected =
    jobs.find((job) => job.id === selectedId) ?? jobs[0] ?? null;

  async function tailor(job: JobRecord) {
    setTailoringId(job.id);
    setError(null);
    try {
      await api.startTailoring({
        job_id: job.id,
        source: job.source,
        title: job.title,
        company: job.company,
        location: job.location,
        remote: job.remote,
        apply_url: job.apply_url,
      });
      setTrackedJobIds((current) => new Set(current).add(job.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start tailoring.");
    } finally {
      setTailoringId(null);
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">{heading}</h1>
        <p className="mt-1 text-sm text-muted">{description}</p>
      </header>

      {hasResume === false && (
        <div className="card mb-5 flex flex-wrap items-center justify-between gap-3 p-4">
          <p className="text-sm">Add a base resume before tailoring an internship.</p>
          <Link href="/resume" className="btn-primary">
            Add resume
          </Link>
        </div>
      )}

      <section className="card mb-5 p-4" aria-label="Filter internships">
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            className="field flex-1"
            placeholder="Filter by keywords (e.g. software, product, finance)"
            value={keywords}
            onChange={(event) => setKeywords(event.target.value)}
          />
          <input
            className="field sm:max-w-[220px]"
            placeholder="Filter by location"
            value={location}
            onChange={(event) => setLocation(event.target.value)}
          />
        </div>
        <label className="mt-3 flex w-fit cursor-pointer items-center gap-2 text-sm text-muted">
          <input
            type="checkbox"
            className="h-4 w-4 accent-ink"
            checked={remoteOnly}
            onChange={(event) => setRemoteOnly(event.target.checked)}
          />
          Remote only
        </label>
      </section>

      {loading && <p className="text-sm text-muted">Loading internships…</p>}
      {error && (
        <p className="card mb-5 border-gold/60 bg-gold/10 p-4 text-sm">{error}</p>
      )}
      {data?.warning && (
        <p className="card mb-5 border-gold/60 bg-gold/10 p-4 text-sm">
          {data.warning}
        </p>
      )}

      {data && (
        <>
          <div className="mb-3 flex items-center gap-2 text-xs text-muted">
            <span>
              {jobs.length} internship{jobs.length === 1 ? "" : "s"}
            </span>
            <span className="rounded-full bg-brand-tint px-2 py-0.5 font-semibold text-brand">
              {heading} only
            </span>
          </div>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
            <ul className="flex max-h-[70vh] flex-col gap-2 overflow-y-auto pr-1">
              {jobs.map((job) => (
                <li key={job.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(job.id)}
                    className={`card w-full p-4 text-left transition-colors ${
                      selected?.id === job.id
                        ? "border-brand bg-brand-tint"
                        : "hover:border-brand/40"
                    }`}
                  >
                    <p className="font-bold leading-snug">{job.title}</p>
                    <p className="mt-0.5 text-sm text-muted">{job.company}</p>
                    <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
                      {job.location && <span>{job.location}</span>}
                      {job.remote && (
                        <span className="rounded-full bg-brand-teal/30 px-2 py-0.5 font-semibold text-ink">
                          Remote
                        </span>
                      )}
                    </div>
                  </button>
                </li>
              ))}
              {jobs.length === 0 && (
                <li className="card p-6 text-center text-sm text-muted">
                  No internships match these filters. Add more employer boards in
                  Settings to expand coverage.
                </li>
              )}
            </ul>

            {selected && (
              <section className="card flex max-h-[70vh] flex-col p-5">
                <header className="border-b border-line pb-4">
                  <h2 className="text-lg font-bold leading-snug">{selected.title}</h2>
                  <p className="mt-0.5 text-sm text-muted">
                    {selected.company}
                    {selected.location ? ` · ${selected.location}` : ""}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {trackedJobIds.has(selected.id) ? (
                      <Link href="/applications" className="btn-primary">
                        Track progress →
                      </Link>
                    ) : (
                      <button
                        type="button"
                        className="btn-primary"
                        disabled={!hasResume || tailoringId === selected.id}
                        onClick={() => tailor(selected)}
                      >
                        {tailoringId === selected.id
                          ? "Adding to tracker…"
                          : "Tailor resume & apply"}
                      </button>
                    )}
                    <a
                      className="btn-ghost"
                      href={selected.apply_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      View posting ↗
                    </a>
                  </div>
                </header>
                <div className="mt-4 overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed text-muted">
                  {selected.description || "No description supplied by this board."}
                </div>
              </section>
            )}
          </div>
        </>
      )}
    </div>
  );
}
