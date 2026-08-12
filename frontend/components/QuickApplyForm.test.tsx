import type { AnchorHTMLAttributes, ReactNode } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import QuickApplyForm from "./QuickApplyForm";

const mocks = vi.hoisted(() => ({
  baseResume: vi.fn(),
  importJob: vi.fn(),
  startTailoring: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: mocks,
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: AnchorHTMLAttributes<HTMLAnchorElement> & {
    href: string;
    children: ReactNode;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

afterEach(() => cleanup());

beforeEach(() => {
  vi.clearAllMocks();
  mocks.baseResume.mockResolvedValue({ id: 1 });
});

describe("QuickApplyForm", () => {
  it("accepts a posting from any job site and starts tailoring", async () => {
    mocks.importJob.mockResolvedValue({
      id: "manual_import:abc",
      source: "manual_import",
      title: "Platform Engineer",
      company: "Example Labs",
      location: "Remote",
      remote: true,
      apply_url: "https://jobs.example.com/platform",
      description: "A complete description",
    });
    mocks.startTailoring.mockResolvedValue({ id: 42 });
    render(<QuickApplyForm />);

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Tailor resume & quick apply" }),
      ).toBeEnabled(),
    );

    fireEvent.change(screen.getByLabelText("Job posting URL"), {
      target: { value: "jobs.example.com/platform" },
    });
    fireEvent.change(screen.getByLabelText("Job title"), {
      target: { value: "Platform Engineer" },
    });
    fireEvent.change(screen.getByLabelText("Company"), {
      target: { value: "Example Labs" },
    });
    fireEvent.change(screen.getByLabelText("Location"), {
      target: { value: "Remote" },
    });
    fireEvent.click(screen.getByLabelText("Remote role"));
    fireEvent.change(screen.getByLabelText("Complete job description"), {
      target: {
        value:
          "Build and operate reliable production systems with a collaborative team.",
      },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Tailor resume & quick apply" }),
    );

    await waitFor(() =>
      expect(mocks.importJob).toHaveBeenCalledWith({
        url: "jobs.example.com/platform",
        title: "Platform Engineer",
        company: "Example Labs",
        location: "Remote",
        remote: true,
        description:
          "Build and operate reliable production systems with a collaborative team.",
      }),
    );
    expect(mocks.startTailoring).toHaveBeenCalledWith({
      job_id: "manual_import:abc",
      source: "manual_import",
      title: "Platform Engineer",
      company: "Example Labs",
      location: "Remote",
      remote: true,
      apply_url: "https://jobs.example.com/platform",
    });
    expect(await screen.findByRole("link", { name: "Track progress →" })).toHaveAttribute(
      "href",
      "/applications",
    );
    expect(screen.getByRole("link", { name: "Open application ↗" })).toHaveAttribute(
      "href",
      "https://jobs.example.com/platform",
    );
  });

  it("directs users without a base resume to add one", async () => {
    mocks.baseResume.mockResolvedValue(null);
    render(<QuickApplyForm />);

    expect(await screen.findByRole("link", { name: "Add resume" })).toHaveAttribute(
      "href",
      "/resume",
    );
    expect(
      screen.getByRole("button", { name: "Tailor resume & quick apply" }),
    ).toBeDisabled();
  });
});
