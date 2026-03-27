import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the Recorder component — it requires WebAudio + Socket.IO
vi.mock("../components/recorder", () => ({
  default: () => <div data-testid="recorder-mock" />,
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
