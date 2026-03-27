import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the Recorder component — it requires WebAudio + Socket.IO
// Expose onPredictionModel so tests can invoke it directly
let capturedOnPredictionModel: ((model: string) => void) | undefined;
vi.mock("../components/recorder", () => ({
  default: (props: { onPredictionModel?: (model: string) => void }) => {
    capturedOnPredictionModel = props.onPredictionModel;
    return <div data-testid="recorder-mock" />;
  },
}));

import Home from "../app/page";

// ---------------------------------------------------------------------------
// localStorage stub (jsdom has it but let's ensure clean state)
// ---------------------------------------------------------------------------
beforeEach(() => {
  localStorage.clear();
});

describe("Home — setup screen", () => {
  it("renders the Teleprompt logo", () => {
    render(<Home />);
    expect(screen.getByText("Teleprompt")).toBeInTheDocument();
  });

  it("renders the context textarea", () => {
    render(<Home />);
    expect(screen.getByPlaceholderText("Audience, topic, and tone")).toBeInTheDocument();
  });

  it("renders the Start Teleprompter button", () => {
    render(<Home />);
    expect(screen.getByRole("button", { name: /start teleprompter/i })).toBeInTheDocument();
  });

  it("Advanced Settings button is disabled", () => {
    render(<Home />);
    const btn = screen.getByRole("button", { name: /advanced settings/i });
    expect(btn).toBeDisabled();
  });

  it("context textarea accepts input", () => {
    render(<Home />);
    const textarea = screen.getByPlaceholderText("Audience, topic, and tone") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "developer conference talk" } });
    expect(textarea.value).toBe("developer conference talk");
  });
});

describe("Home — theme toggle", () => {
  it("renders the theme toggle button", () => {
    render(<Home />);
    expect(screen.getByRole("button", { name: /toggle theme/i })).toBeInTheDocument();
  });

  it("toggles theme on click and persists to localStorage", () => {
    render(<Home />);
    const toggle = screen.getByRole("button", { name: /toggle theme/i });
    fireEvent.click(toggle);
    expect(localStorage.getItem("tp-theme")).toBe("dark");
    fireEvent.click(toggle);
    expect(localStorage.getItem("tp-theme")).toBe("light");
  });

  it("restores dark theme from localStorage on mount", () => {
    localStorage.setItem("tp-theme", "dark");
    render(<Home />);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});

describe("Home — active screen", () => {
  it("switches to active screen when Start is clicked", () => {
    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /start teleprompter/i }));
    expect(screen.getByRole("button", { name: /stop listening/i })).toBeInTheDocument();
  });

  it("setup screen is gone after starting", () => {
    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /start teleprompter/i }));
    expect(screen.queryByRole("button", { name: /start teleprompter/i })).not.toBeInTheDocument();
  });

  it("mounts the Recorder component when active", () => {
    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /start teleprompter/i }));
    expect(screen.getByTestId("recorder-mock")).toBeInTheDocument();
  });

  it("returns to setup screen after Stop is clicked", () => {
    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /start teleprompter/i }));
    fireEvent.click(screen.getByRole("button", { name: /stop listening/i }));
    expect(screen.getByRole("button", { name: /start teleprompter/i })).toBeInTheDocument();
  });
});

describe("Home — prediction model pill", () => {
  it("does not show a pill before model is known", () => {
    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /start teleprompter/i }));
    expect(screen.queryByText("Powered by Claude")).not.toBeInTheDocument();
    expect(screen.queryByText("Basic predictions")).not.toBeInTheDocument();
  });

  it("shows 'Powered by Claude' when model is claude-haiku", () => {
    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /start teleprompter/i }));
    act(() => { capturedOnPredictionModel?.("claude-haiku"); });
    expect(screen.getByText("Powered by Claude")).toBeInTheDocument();
  });

  it("shows 'Basic predictions' when model is basic", () => {
    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /start teleprompter/i }));
    act(() => { capturedOnPredictionModel?.("basic"); });
    expect(screen.getByText("Basic predictions")).toBeInTheDocument();
  });
});
