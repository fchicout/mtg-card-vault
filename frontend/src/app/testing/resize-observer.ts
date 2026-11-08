/** jsdom has no ResizeObserver; Clarity's modal needs one. Call from a spec's beforeAll. */
class StubResizeObserver {
  observe(): undefined {
    return undefined;
  }
  unobserve(): undefined {
    return undefined;
  }
  disconnect(): undefined {
    return undefined;
  }
}

export function installResizeObserverStub(): void {
  (globalThis as { ResizeObserver?: unknown }).ResizeObserver ??= StubResizeObserver;
}
