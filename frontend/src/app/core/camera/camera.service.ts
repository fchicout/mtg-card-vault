import { Injectable } from '@angular/core';

/** Why the camera could not be used; the page maps each one to a message. */
export type CameraFailure = 'denied' | 'missing' | 'unsupported' | 'failed';

/** Longest side of an uploaded frame; keeps a photo well under the server's 2 MB limit. */
export const MAX_FRAME_SIDE = 1280;
const JPEG_QUALITY = 0.85;

/**
 * Camera access for the scanner (US-015). The stream is opened on request, never kept after the
 * page is left, and frames are captured in memory only (nothing is stored in the browser).
 */
@Injectable({ providedIn: 'root' })
export class CameraService {
  get supported(): boolean {
    return typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia;
  }

  async open(): Promise<MediaStream> {
    if (!this.supported) {
      throw new CameraError('unsupported');
    }
    const media = navigator.mediaDevices;
    try {
      return await media.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 } },
      });
    } catch (error) {
      // Some devices reject the preferences (rear camera, size): any camera is better than none.
      if (!isUnsatisfiable(error)) {
        throw new CameraError(classify(error));
      }
    }
    try {
      return await media.getUserMedia({ audio: false, video: true });
    } catch (error) {
      throw new CameraError(classify(error));
    }
  }

  close(stream: MediaStream | null): void {
    stream?.getTracks().forEach((track) => track.stop());
  }

  /** The current video frame as a JPEG, downscaled so its longest side is at most MAX_FRAME_SIDE. */
  async capture(video: HTMLVideoElement): Promise<Blob> {
    const { videoWidth: width, videoHeight: height } = video;
    if (!width || !height) {
      throw new CameraError('failed');
    }
    const scale = Math.min(1, MAX_FRAME_SIDE / Math.max(width, height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height);
    return new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new CameraError('failed'))),
        'image/jpeg',
        JPEG_QUALITY,
      );
    });
  }
}

export class CameraError extends Error {
  constructor(readonly reason: CameraFailure) {
    super(reason);
  }
}

function isUnsatisfiable(error: unknown): boolean {
  const name = error instanceof DOMException ? error.name : '';
  return name === 'NotFoundError' || name === 'OverconstrainedError';
}

function classify(error: unknown): CameraFailure {
  const name = error instanceof DOMException ? error.name : '';
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'denied';
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError') {
    return 'missing';
  }
  return 'failed';
}
