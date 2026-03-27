/**
 * Unit tests for PCM conversion and amplitude logic extracted from recorder.tsx.
 *
 * These test the pure math inline in the component without needing DOM/WebAudio mocks.
 */
import { describe, it, expect } from "vitest";

// ---------------------------------------------------------------------------
// PCM float32 → int16 conversion (mirrors recorder.tsx lines 314-318)
// ---------------------------------------------------------------------------

function floatToInt16(samples: Float32Array): Int16Array {
  const out = new Int16Array(samples.length);
  for (let j = 0; j < samples.length; j++) {
    const s = Math.max(-1, Math.min(1, samples[j]));
    out[j] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

// ---------------------------------------------------------------------------
// RMS amplitude (mirrors recorder.tsx lines 246-252)
// ---------------------------------------------------------------------------

function computeAmplitude(int16: Int16Array): number {
  let sum = 0;
  for (let k = 0; k < int16.length; k++) {
    const s = int16[k] / 32768;
    sum += s * s;
  }
  return Math.min(1, Math.sqrt(sum / int16.length) * 6);
}

// ===========================================================================
// PCM conversion tests
// ===========================================================================

describe("floatToInt16", () => {
  it("converts 0.0 to 0", () => {
    const result = floatToInt16(new Float32Array([0]));
    expect(result[0]).toBe(0);
  });

  it("converts 1.0 to max positive int16 (32767)", () => {
    const result = floatToInt16(new Float32Array([1.0]));
    expect(result[0]).toBe(0x7fff);
  });

  it("converts -1.0 to min int16 (-32768)", () => {
    const result = floatToInt16(new Float32Array([-1.0]));
    expect(result[0]).toBe(-0x8000);
  });

  it("clamps values above 1.0", () => {
    const result = floatToInt16(new Float32Array([2.0]));
    expect(result[0]).toBe(0x7fff);
  });

  it("clamps values below -1.0", () => {
    const result = floatToInt16(new Float32Array([-2.0]));
    expect(result[0]).toBe(-0x8000);
  });

  it("converts 0.5 to approximately 16383", () => {
    const result = floatToInt16(new Float32Array([0.5]));
    expect(result[0]).toBeCloseTo(0x3fff, -1);
  });

  it("preserves array length", () => {
    const input = new Float32Array([0.1, -0.2, 0.5, -0.9, 1.0]);
    const result = floatToInt16(input);
    expect(result.length).toBe(input.length);
  });
});

// ===========================================================================
// Amplitude tests
// ===========================================================================

describe("computeAmplitude", () => {
  it("returns 0 for silence (all zeros)", () => {
    const silence = new Int16Array(1024);
    expect(computeAmplitude(silence)).toBe(0);
  });

  it("returns a value between 0 and 1 for normal speech", () => {
    // Simulate ~50% amplitude sine
    const samples = new Int16Array(1024);
    for (let i = 0; i < 1024; i++) {
      samples[i] = Math.round(Math.sin(2 * Math.PI * i / 64) * 16383);
    }
    const amp = computeAmplitude(samples);
    expect(amp).toBeGreaterThan(0);
    expect(amp).toBeLessThanOrEqual(1);
  });

  it("clamps to 1 for very loud audio (full scale)", () => {
    // Full-scale signal: RMS = 1.0, ×6 → clamped to 1
    const full = new Int16Array(1024).fill(32767);
    expect(computeAmplitude(full)).toBe(1);
  });

  it("loud audio is louder than quiet audio", () => {
    const quiet = new Int16Array(1024).fill(1000);
    const loud = new Int16Array(1024).fill(20000);
    expect(computeAmplitude(loud)).toBeGreaterThan(computeAmplitude(quiet));
  });
});
