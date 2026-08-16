import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type SettingsOut } from "@/lib/api";
import SettingsPage from "./page";

vi.mock("@/components/ProviderSetup", () => ({
  default: () => <section>Model provider settings</section>,
}));

vi.mock("@/lib/api", () => ({
  api: {
    settings: vi.fn(),
    capabilities: vi.fn(),
    greenhouseCompanies: vi.fn(),
    ashbyBoards: vi.fn(),
    saveSettings: vi.fn(),
  },
}));

const DEFAULT_PROMPT = "Default truthful resume tailoring prompt.";

function settings(overrides: Partial<SettingsOut> = {}): SettingsOut {
  return {
    llm_provider: "ollama",
    model: "qwen2.5:7b",
    has_key: false,
    ollama_host: "http://localhost:11434",
    openai_base_url: "https://api.openai.com/v1",
    tailor_system_prompt: DEFAULT_PROMPT,
    tailor_system_prompt_is_custom: false,
    ...overrides,
  };
}

function mockPageLoad(value = settings()) {
  vi.mocked(api.settings).mockResolvedValue(value);
  vi.mocked(api.capabilities).mockResolvedValue({ pdf: true, pdf_detail: "Available" });
  vi.mocked(api.greenhouseCompanies).mockResolvedValue([]);
  vi.mocked(api.ashbyBoards).mockResolvedValue([]);
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe("SettingsPage system prompt", () => {
  it("shows and saves the resume tailoring system prompt", async () => {
    mockPageLoad();
    const customPrompt = "Use my custom evidence-first instructions.";
    vi.mocked(api.saveSettings).mockResolvedValue(
      settings({
        tailor_system_prompt: customPrompt,
        tailor_system_prompt_is_custom: true,
      }),
    );

    render(<SettingsPage />);

    const editor = await screen.findByRole("textbox", {
      name: "Resume tailoring system prompt",
    });
    expect(editor).toHaveValue(DEFAULT_PROMPT);
    fireEvent.change(editor, { target: { value: customPrompt } });
    fireEvent.click(screen.getByRole("button", { name: "Save system prompt" }));

    await waitFor(() =>
      expect(api.saveSettings).toHaveBeenCalledWith({
        tailor_system_prompt: customPrompt,
      }),
    );
    expect(await screen.findByText("Customized")).toBeInTheDocument();
  });

  it("resets a customized prompt after confirmation", async () => {
    mockPageLoad(
      settings({
        tailor_system_prompt: "Custom prompt",
        tailor_system_prompt_is_custom: true,
      }),
    );
    vi.mocked(api.saveSettings).mockResolvedValue(settings());
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Reset to default" }));

    await waitFor(() =>
      expect(api.saveSettings).toHaveBeenCalledWith({ tailor_system_prompt: "" }),
    );
    expect(await screen.findByText("Default")).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: "Resume tailoring system prompt" }),
    ).toHaveValue(DEFAULT_PROMPT);
  });
});
