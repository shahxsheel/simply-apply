"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type JobImport } from "@/lib/api";

const EMPTY_FORM: JobImport = {
  url: "",
  title: "",
  company: "",
  location: "",
  remote: false,
  description: "",
};

export default function QuickApplyForm() {
  const [form, setForm] = useState<JobImport>(EMPTY_FORM);
  const [hasResume, setHasResume] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [application, setApplication] = useState<{ url: string } | null>(null);

  useEffect(() => {
    api
      .baseResume()
      .then((resume) => setHasResume(Boolean(resume)))
      .catch(() => setHasResume(false));
  }, []);

  function update<K extends keyof JobImport>(key: K, value: JobImport[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setApplication(null);
    try {
      const job = await api.importJob(form);
      await api.startTailoring({
        job_id: job.id,
        source: job.source,
        title: job.title,
        company: job.company,
        location: job.location,
        remote: job.remote,
        apply_url: job.apply_url,
      });
      setApplication({ url: job.apply_url });
      setForm(EMPTY_FORM);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not import this job.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <header className="mb-6">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted">
          Any job site
        </p>
        <h1>Quick apply</h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">
          Bring a role from LinkedIn, Indeed, a company careers page, or almost any
          other job site. SimplyApply will create a truthful, targeted resume and add
          it to your application tracker.
        </p>
      </header>

      <div className="card mb-5 border-brand/30 bg-brand-tint p-4 text-sm leading-relaxed">
        Paste the complete description for the strongest result. SimplyApply saves the
        posting locally and never submits an application on your behalf—you review the
        resume, then finish on the employer&apos;s site.
      </div>

      {hasResume === false && (
        <div className="card mb-5 flex flex-wrap items-center justify-between gap-3 p-4">
          <p className="text-sm">Save a base resume before tailoring a job.</p>
          <Link href="/resume" className="btn-primary">
            Add resume
          </Link>
        </div>
      )}

      {error && (
        <p role="alert" className="card mb-5 border-gold/60 bg-gold/10 p-4 text-sm">
          {error}
        </p>
      )}

      {application && (
        <div
          role="status"
          className="card mb-5 border-brand/30 bg-brand-tint p-4"
        >
          <p className="text-sm font-semibold">
            Added to Applications. Tailoring is running in the background.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link href="/applications" className="btn-primary">
              Track progress →
            </Link>
            <a
              href={application.url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-ghost"
            >
              Open application ↗
            </a>
          </div>
        </div>
      )}

      <form onSubmit={submit} className="card p-5 sm:p-7">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-semibold sm:col-span-2">
            Job posting URL
            <input
              className="field mt-1.5 font-normal"
              type="text"
              inputMode="url"
              autoComplete="url"
              required
              placeholder="https://company.com/careers/job…"
              value={form.url}
              onChange={(event) => update("url", event.target.value)}
            />
          </label>
          <label className="text-sm font-semibold">
            Job title
            <input
              className="field mt-1.5 font-normal"
              required
              placeholder="Software Engineer"
              value={form.title}
              onChange={(event) => update("title", event.target.value)}
            />
          </label>
          <label className="text-sm font-semibold">
            Company
            <input
              className="field mt-1.5 font-normal"
              required
              placeholder="Company name"
              value={form.company}
              onChange={(event) => update("company", event.target.value)}
            />
          </label>
          <label className="text-sm font-semibold sm:col-span-2">
            Location
            <input
              className="field mt-1.5 font-normal"
              placeholder="Seattle, WA"
              value={form.location}
              onChange={(event) => update("location", event.target.value)}
            />
          </label>
          <label className="flex w-fit cursor-pointer items-center gap-2 text-sm text-muted sm:col-span-2">
            <input
              type="checkbox"
              checked={form.remote}
              onChange={(event) => update("remote", event.target.checked)}
              className="h-4 w-4 accent-ink"
            />
            Remote role
          </label>
          <label className="text-sm font-semibold sm:col-span-2">
            Complete job description
            <textarea
              className="field mt-1.5 min-h-[320px] resize-y font-normal leading-relaxed"
              required
              minLength={40}
              placeholder="Paste the role overview, responsibilities, qualifications, and requirements…"
              value={form.description}
              onChange={(event) => update("description", event.target.value)}
            />
          </label>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button
            type="submit"
            className="btn-primary"
            disabled={busy || hasResume !== true}
          >
            {busy ? "Adding to Applications…" : "Tailor resume & quick apply"}
          </button>
          <p className="text-xs text-muted">Usually ready in about a minute.</p>
        </div>
      </form>
    </div>
  );
}
