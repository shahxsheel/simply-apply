import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type ApplicationOut } from "@/lib/api";
import MetricsPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/lib/api", () => ({
  api: { applications: vi.fn() },
}));

function application(id: number, status: string): ApplicationOut {
  return {
    id,
    job_id: `job-${id}`,
    resume_id: id,
    applied_at: new Date().toISOString(),
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

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("MetricsPage", () => {
  it("shows daily pace, outcome summaries, and range controls", async () => {
    vi.mocked(api.applications).mockResolvedValue([
      application(1, "applied"),
      application(2, "interviewing"),
      application(3, "rejected"),
    ]);

    render(<MetricsPage />);

    expect(await screen.findByText("Daily application pace")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Application metric summary" })).toBeInTheDocument();
    expect(screen.getByText("Status mix")).toBeInTheDocument();
    expect(screen.getByText("Daily detail")).toBeInTheDocument();
    expect(screen.getByText("100% of decided outcomes")).toBeInTheDocument();

    const sevenDays = screen.getByRole("button", { name: "7 days" });
    fireEvent.click(sevenDays);
    expect(sevenDays).toHaveAttribute("aria-pressed", "true");
  });

  it("guides a new user when the tracker is empty", async () => {
    vi.mocked(api.applications).mockResolvedValue([]);

    render(<MetricsPage />);

    expect(
      await screen.findByText("Your metrics will grow with your tracker"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start an application" })).toHaveAttribute(
      "href",
      "/quick-apply",
    );
  });
});
