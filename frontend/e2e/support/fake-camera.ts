import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

/**
 * Fake camera for Chromium (US-015, NFR-CMP-01). Chromium can replace the webcam with a video file:
 *   --use-fake-device-for-media-stream --use-fake-ui-for-media-stream
 *   --use-file-for-fake-video-capture=<file.y4m>
 * The fixture is generated, not committed (a few seconds of raw video would be megabytes):
 * a dark scene with a bright card-shaped rectangle (63 x 88 mm ratio) and a small marker that moves
 * every frame, so a test can tell that successive frames really arrive.
 */
export const CAMERA_WIDTH = 320;
export const CAMERA_HEIGHT = 240;
const FRAMES = 15;

export const CAMERA_FILE = join(__dirname, '..', '..', 'test-results', 'fake-camera', 'card.y4m');

/** Where the card and the marker are, so tests know which pixels to probe. */
export const CARD = { x: 90, y: 22, width: 140, height: 196 } as const;
export const BACKGROUND_LUMA = 40;
export const CARD_LUMA = 235;
export const MARKER_LUMA = 128;

export function buildCardVideo(): Buffer {
  const header = Buffer.from(
    `YUV4MPEG2 W${CAMERA_WIDTH} H${CAMERA_HEIGHT} F15:1 Ip A1:1 C420jpeg\n`,
  );
  const chroma = (CAMERA_WIDTH / 2) * (CAMERA_HEIGHT / 2);
  const parts: Buffer[] = [header];

  for (let frame = 0; frame < FRAMES; frame++) {
    const luma = new Uint8Array(CAMERA_WIDTH * CAMERA_HEIGHT).fill(BACKGROUND_LUMA);
    for (let y = CARD.y; y < CARD.y + CARD.height; y++) {
      luma.fill(CARD_LUMA, y * CAMERA_WIDTH + CARD.x, y * CAMERA_WIDTH + CARD.x + CARD.width);
    }
    // A marker block in the top-left corner that steps right every frame.
    const markerX = 4 + frame * 4;
    for (let y = 4; y < 20; y++) {
      luma.fill(MARKER_LUMA, y * CAMERA_WIDTH + markerX, y * CAMERA_WIDTH + markerX + 12);
    }
    parts.push(
      Buffer.from('FRAME\n'),
      Buffer.from(luma),
      Buffer.alloc(chroma, 128),
      Buffer.alloc(chroma, 128),
    );
  }
  return Buffer.concat(parts);
}

export function writeCardVideo(file: string = CAMERA_FILE): string {
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, buildCardVideo());
  return file;
}
