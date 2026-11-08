import { HttpErrorResponse } from '@angular/common/http';
import { type ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { Api, addVaultEntry, getCard, scanCard } from '../api';
import { CameraError, CameraService } from '../core/camera/camera.service';
import { ScanPage } from './scan';

const card = (id: string, name: string) => ({
  id,
  name,
  set_code: 'm10',
  set_name: 'Magic 2010',
  collector_number: '146',
  rarity: 'common',
  image_small: null,
});
const found = {
  text: { title: 'Lightning Bolt', collector: '146/249 M10' },
  candidates: [{ card: card('c1', 'Lightning Bolt'), confidence: 0.97, exact: true }],
  reason: null,
};

describe('ScanPage', () => {
  let invoke: ReturnType<typeof vi.fn>;
  let camera: {
    open: ReturnType<typeof vi.fn>;
    close: ReturnType<typeof vi.fn>;
    capture: ReturnType<typeof vi.fn>;
  };
  let answers: { scan: unknown; added?: unknown };

  const q = (f: ComponentFixture<unknown>, s: string): HTMLElement | null =>
    (f.nativeElement as HTMLElement).querySelector(s);
  const click = async (f: ComponentFixture<unknown>, s: string): Promise<void> => {
    q(f, s)!.click();
    await f.whenStable();
    await new Promise<void>((resolve) => setTimeout(resolve));
    f.detectChanges();
  };

  /** Starts the camera and lets the preview report its size, as a browser does. */
  const startCamera = async (f: ComponentFixture<unknown>): Promise<void> => {
    await click(f, '[data-testid="start-camera"]');
    q(f, 'video')!.dispatchEvent(new Event('loadedmetadata'));
    f.detectChanges();
  };

  function render(): ComponentFixture<ScanPage> {
    invoke.mockImplementation((fn: unknown) => {
      const answer =
        fn === scanCard
          ? answers.scan
          : fn === getCard
            ? { ...card('c1', 'Lightning Bolt'), finishes: ['nonfoil'] }
            : fn === addVaultEntry
              ? answers.added
              : undefined;
      return answer instanceof HttpErrorResponse ? Promise.reject(answer) : Promise.resolve(answer);
    });
    TestBed.configureTestingModule({
      imports: [ScanPage],
      providers: [
        provideRouter([]),
        { provide: Api, useValue: { invoke } },
        { provide: CameraService, useValue: camera },
      ],
    });
    const fixture = TestBed.createComponent(ScanPage);
    fixture.detectChanges();
    return fixture;
  }

  beforeEach(() => {
    invoke = vi.fn();
    camera = {
      open: vi.fn().mockResolvedValue({}),
      close: vi.fn(),
      capture: vi.fn().mockResolvedValue(new Blob(['x'], { type: 'image/jpeg' })),
    };
    answers = { scan: found, added: { quantity: 1, condition: 'NM', finish: 'nonfoil' } };
  });

  it('shows the camera stream in the preview', async () => {
    const stream = { id: 'live' } as unknown as MediaStream;
    camera.open.mockResolvedValue(stream);
    const f = render();
    await click(f, '[data-testid="start-camera"]');
    expect((q(f, 'video') as HTMLVideoElement).srcObject).toBe(stream);
  });

  it('does not offer the capture before the preview has a size', async () => {
    const f = render();
    await click(f, '[data-testid="start-camera"]');
    expect(q(f, '[data-testid="capture"]')!.hasAttribute('disabled')).toBe(true);
    q(f, 'video')!.dispatchEvent(new Event('loadedmetadata'));
    f.detectChanges();
    expect(q(f, '[data-testid="capture"]')!.hasAttribute('disabled')).toBe(false);
  });

  it('starts idle with a way to search by name', () => {
    const f = render();
    expect(q(f, '[data-testid="start-camera"]')).not.toBeNull();
    expect(q(f, 'a[href="/catalogue"]')).not.toBeNull();
    expect(camera.open).not.toHaveBeenCalled();
  });

  it.each([
    ['denied', 'blocked'],
    ['missing', 'No camera'],
    ['unsupported', 'cannot use the camera'],
    ['failed', 'could not be started'],
  ] as const)('explains a %s camera', async (reason, text) => {
    camera.open.mockRejectedValue(new CameraError(reason));
    const f = render();
    await click(f, '[data-testid="start-camera"]');
    expect(q(f, '[data-testid="scan-problem"]')!.textContent).toContain(text);
    expect(q(f, '[data-testid="start-camera"]')).not.toBeNull();
  });

  it('scans a frame, lists candidates and releases the camera', async () => {
    const f = render();
    await startCamera(f);
    await click(f, '[data-testid="capture"]');
    expect(invoke).toHaveBeenCalledWith(
      scanCard,
      { body: { image: expect.any(Blob) } },
      expect.anything(),
    );
    expect(camera.close).toHaveBeenCalled();
    expect(q(f, '[data-testid="candidate"]')!.textContent).toContain('Lightning Bolt');
    expect(q(f, '[data-testid="candidate"]')!.textContent).toContain('97%');
    expect(invoke).not.toHaveBeenCalledWith(addVaultEntry, expect.anything(), expect.anything());
  });

  it('adds nothing until the person confirms the printing and its details', async () => {
    const f = render();
    await startCamera(f);
    await click(f, '[data-testid="capture"]');
    await click(f, '[data-testid="choose"]');
    expect(q(f, '[data-testid="confirm-dialog"]')).not.toBeNull();
    expect(invoke).not.toHaveBeenCalledWith(addVaultEntry, expect.anything(), expect.anything());
    q(f, '[data-testid="entry-form"]')!.dispatchEvent(new Event('submit', { cancelable: true }));
    await f.whenStable();
    await new Promise<void>((resolve) => setTimeout(resolve));
    f.detectChanges();
    expect(invoke).toHaveBeenCalledWith(
      addVaultEntry,
      { body: { card_id: 'c1', quantity: 1, condition: 'NM', finish: 'nonfoil' } },
      expect.anything(),
    );
    expect(q(f, '[data-testid="scan-added"]')!.textContent).toContain('Added Lightning Bolt');
  });

  it.each([
    ['unreadable', 'could not read'],
    ['no_match', 'did not find'],
  ])('offers manual search when the answer is %s', async (reason, text) => {
    answers.scan = { text: { title: 'Bolt', collector: '' }, candidates: [], reason };
    const f = render();
    await startCamera(f);
    await click(f, '[data-testid="capture"]');
    expect((f.nativeElement as HTMLElement).textContent).toContain(text);
    expect(q(f, '[data-testid="manual-search"]')!.getAttribute('href')).toBe('/catalogue?q=Bolt');
    expect(q(f, '[data-testid="scan-again"]')).not.toBeNull();
  });

  it.each([
    [429, 'very fast'],
    [415, 'could not be used'],
    [503, 'temporarily unavailable'],
    [500, 'could not be scanned'],
  ])('keeps the camera on a %s answer', async (status, text) => {
    answers.scan = new HttpErrorResponse({ status });
    const f = render();
    await startCamera(f);
    await click(f, '[data-testid="capture"]');
    expect(q(f, '[data-testid="scan-problem"]')!.textContent).toContain(text);
    expect(q(f, '[data-testid="capture"]')).not.toBeNull();
  });

  it('stops the camera on request and when the page is destroyed', async () => {
    const f = render();
    await startCamera(f);
    await click(f, '[data-testid="stop-camera"]');
    expect(camera.close).toHaveBeenCalledTimes(1);
    await click(f, '[data-testid="start-camera"]');
    f.destroy();
    expect(camera.close).toHaveBeenCalledTimes(2);
  });
});
