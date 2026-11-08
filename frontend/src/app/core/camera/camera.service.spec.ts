import { CameraError, CameraService, MAX_FRAME_SIDE } from './camera.service';

function withMedia(getUserMedia: unknown): void {
  Object.defineProperty(navigator, 'mediaDevices', {
    value: getUserMedia ? { getUserMedia } : undefined,
    configurable: true,
  });
}

describe('CameraService', () => {
  const service = new CameraService();

  it('reports unsupported browsers', async () => {
    withMedia(undefined);
    expect(service.supported).toBe(false);
    await expect(service.open()).rejects.toMatchObject({ reason: 'unsupported' });
  });

  it.each([
    ['NotAllowedError', 'denied'],
    ['SecurityError', 'denied'],
    ['NotFoundError', 'missing'],
    ['OverconstrainedError', 'missing'],
    ['AbortError', 'failed'],
  ])('maps %s to %s', async (name, reason) => {
    withMedia(() => Promise.reject(new DOMException('x', name)));
    await expect(service.open()).rejects.toMatchObject({ reason });
  });

  it('opens the rear camera without audio', async () => {
    const stream = {} as MediaStream;
    const getUserMedia = vi.fn().mockResolvedValue(stream);
    withMedia(getUserMedia);
    expect(await service.open()).toBe(stream);
    const constraints = getUserMedia.mock.calls[0][0];
    expect(constraints.audio).toBe(false);
    expect(constraints.video.facingMode).toEqual({ ideal: 'environment' });
  });

  it.each(['NotFoundError', 'OverconstrainedError'])(
    'falls back to any camera when the preferences fail with %s',
    async (name) => {
      const stream = {} as MediaStream;
      const getUserMedia = vi
        .fn()
        .mockRejectedValueOnce(new DOMException('x', name))
        .mockResolvedValueOnce(stream);
      withMedia(getUserMedia);
      expect(await service.open()).toBe(stream);
      expect(getUserMedia.mock.calls[1][0]).toEqual({ audio: false, video: true });
    },
  );

  it('does not retry a refused permission', async () => {
    const getUserMedia = vi.fn().mockRejectedValue(new DOMException('x', 'NotAllowedError'));
    withMedia(getUserMedia);
    await expect(service.open()).rejects.toMatchObject({ reason: 'denied' });
    expect(getUserMedia).toHaveBeenCalledTimes(1);
  });

  it('stops every track on close and tolerates no stream', () => {
    const stop = vi.fn();
    service.close({ getTracks: () => [{ stop }, { stop }] } as unknown as MediaStream);
    service.close(null);
    expect(stop).toHaveBeenCalledTimes(2);
  });

  it('refuses to capture before the video has a size', async () => {
    const video = { videoWidth: 0, videoHeight: 0 } as HTMLVideoElement;
    await expect(service.capture(video)).rejects.toBeInstanceOf(CameraError);
  });

  it('downscales the frame to the limit', async () => {
    const canvas = {
      width: 0,
      height: 0,
      getContext: () => ({ drawImage: vi.fn() }),
      toBlob: vi.fn(),
    };
    canvas.toBlob.mockImplementation((cb: (b: Blob | null) => void) => cb(new Blob(['x'])));
    vi.spyOn(document, 'createElement').mockReturnValue(canvas as unknown as HTMLElement);
    const video = { videoWidth: 2560, videoHeight: 1440 } as HTMLVideoElement;
    await service.capture(video);
    expect(canvas.width).toBe(MAX_FRAME_SIDE);
    expect(canvas.height).toBe(720);
    vi.restoreAllMocks();
  });
});
