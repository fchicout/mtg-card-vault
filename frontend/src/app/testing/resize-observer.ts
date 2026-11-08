/** jsdom has no ResizeObserver; Clarity's modal needs one. Imported by specs that open modals. */
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

(globalThis as { ResizeObserver?: unknown }).ResizeObserver ??= StubResizeObserver;
