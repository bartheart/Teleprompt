import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import Prompter from "../app/prompter";

describe("Prompter", () => {
  // ------------------------------------------------------------------
  // Placeholder states
  // ------------------------------------------------------------------

  it("shows start speaking placeholder when transcript is empty", () => {
    render(<Prompter transcript="" prediction="" />);
    expect(screen.getByText("Start speaking…")).toBeInTheDocument();
  });

  it("shows dash placeholder when prediction is empty", () => {
    render(<Prompter transcript="" prediction="" />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  // ------------------------------------------------------------------
  // Transcript words
  // ------------------------------------------------------------------

  it("renders the last word of the transcript", () => {
    render(<Prompter transcript="hello world" prediction="" />);
    expect(screen.getByText("world")).toBeInTheDocument();
  });

  it("renders up to 3 words", () => {
    render(<Prompter transcript="one two three four five" prediction="" />);
    // Only last 3: three, four, five
    expect(screen.getByText("three")).toBeInTheDocument();
    expect(screen.getByText("four")).toBeInTheDocument();
    expect(screen.getByText("five")).toBeInTheDocument();
    expect(screen.queryByText("one")).not.toBeInTheDocument();
    expect(screen.queryByText("two")).not.toBeInTheDocument();
  });

  it("renders a single word transcript without error", () => {
    render(<Prompter transcript="hello" prediction="" />);
    expect(screen.getByText("hello")).toBeInTheDocument();
  });

  it("hides placeholder when transcript has words", () => {
    render(<Prompter transcript="speaking now" prediction="" />);
    expect(screen.queryByText("Start speaking…")).not.toBeInTheDocument();
  });

  // ------------------------------------------------------------------
  // Prediction word
  // ------------------------------------------------------------------

  it("renders the prediction word", () => {
    render(<Prompter transcript="hello" prediction="world" />);
    expect(screen.getByText("world")).toBeInTheDocument();
  });

  it("hides dash placeholder when prediction is present", () => {
    render(<Prompter transcript="hello" prediction="world" />);
    expect(screen.queryByText("—")).not.toBeInTheDocument();
  });

  // ------------------------------------------------------------------
  // Opacity gradient
  // ------------------------------------------------------------------

  it("last transcript word has full opacity", () => {
    render(<Prompter transcript="one two three" prediction="" />);
    const words = document.querySelectorAll(".transcript-word");
    const lastWord = words[words.length - 1] as HTMLElement;
    expect(lastWord.style.opacity).toBe("1");
  });

  it("first of three words has lowest opacity", () => {
    render(<Prompter transcript="one two three" prediction="" />);
    const words = document.querySelectorAll(".transcript-word");
    const firstWord = words[0] as HTMLElement;
    expect(parseFloat(firstWord.style.opacity)).toBeLessThan(1);
  });

  it("with two words the first word has medium opacity", () => {
    render(<Prompter transcript="hello world" prediction="" />);
    const words = document.querySelectorAll(".transcript-word");
    expect(words.length).toBe(2);
    const first = words[0] as HTMLElement;
    const last = words[1] as HTMLElement;
    expect(parseFloat(first.style.opacity)).toBeLessThan(parseFloat(last.style.opacity));
  });
});
