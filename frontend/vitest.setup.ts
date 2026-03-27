import "@testing-library/jest-dom";

// jsdom's localStorage can be unreliable across vitest versions — provide a clean implementation
const store: Record<string, string> = {};
const localStorageMock = {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, value: string) => { store[key] = value; },
  removeItem: (key: string) => { delete store[key]; },
  clear: () => { Object.keys(store).forEach((k) => delete store[k]); },
};
Object.defineProperty(window, "localStorage", { value: localStorageMock, writable: true });
