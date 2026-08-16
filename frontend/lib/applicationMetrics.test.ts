import { describe, expect, it } from "vitest";
import type { ApplicationOut } from "./api";
import { buildApplicationMetrics } from "./applicationMetrics";

function application(
  id: number,
  appliedAt: string,
  status: string,
): ApplicationOut {
  return {
    id,
    job_id: `job-${id}`,
    resume_id: id,
    applied_at: appliedAt,
    status,
    notes: "",
    title: "Software Intern",
    company: "Acme",
    apply_url: "",
    docx_url: null,
    pdf_url: null,
    workflow_status: "completed",
    workflow_step: "completed",
    workflow_progress: 100,
    workflow_detail: "Resume ready.",
    workflow_error: null,
    fit_match_level: "",
    fit_summary: "",
    llm_provider: "",
    llm_model: "",
    llm_requests: 0,
    input_tokens: 0,
    cached_input_tokens: 0,
    cache_write_input_tokens: 0,
    output_tokens: 0,
    reasoning_tokens: 0,
    estimated_cost_usd: null,
  };
}

describe("buildApplicationMetrics", () => {
  it("fills every day in the range and groups current outcomes by application day", () => {
    const metrics = buildApplicationMetrics(
      [
        application(1, "2026-08-14T18:00:00Z", "applied"),
        application(2, "2026-08-14T20:00:00Z", "rejected"),
        application(3, "2026-08-16T12:00:00Z", "interviewing"),
        application(4, "2026-08-01T12:00:00Z", "offer"),
      ],
      7,
      new Date("2026-08-16T17:00:00Z"),
    );

    expect(metrics.days).toHaveLength(7);
    expect(metrics.total).toBe(3);
    expect(metrics.statuses.applied).toBe(1);
    expect(metrics.statuses.rejected).toBe(1);
    expect(metrics.statuses.interviewing).toBe(1);
    expect(metrics.busiestDay?.total).toBe(2);
    expect(metrics.activePipeline).toBe(2);
    expect(metrics.rejectionRate).toBe(100);
  });

  it("returns an honest empty state when there are no applications in range", () => {
    const metrics = buildApplicationMetrics([], 30, new Date("2026-08-16T17:00:00Z"));

    expect(metrics.days).toHaveLength(30);
    expect(metrics.total).toBe(0);
    expect(metrics.dailyAverage).toBe(0);
    expect(metrics.busiestDay).toBeNull();
    expect(metrics.rejectionRate).toBeNull();
  });
});
