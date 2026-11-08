import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

/**
 * Fake camera for Chromium (US-015, NFR-CMP-01). Chromium can replace the webcam with a video file:
 *   --use-fake-device-for-media-stream --use-fake-ui-for-media-stream
 *   --use-file-for-fake-video-capture=<file.y4m>
 * The fixture is generated, not committed (a few seconds of raw video would be megabytes):
 * a dark scene with a bright card-shaped rectangle (63 x 88 mm ratio, filling the scanner's guide)
 * carrying the title "LIGHTNING BOLT" in a blocky font that Tesseract reads, and a small marker that
 * moves every frame, so a test can tell that successive frames really arrive.
 */
export const CAMERA_WIDTH = 1280;
export const CAMERA_HEIGHT = 960;
const FRAMES = 8;
export const CARD_TITLE = 'LIGHTNING BOLT';

export const CAMERA_FILE = join(__dirname, '..', '..', 'test-results', 'fake-camera', 'card.y4m');

/** Where the card and the marker are, so tests know which pixels to probe. */
const CARD_HEIGHT = Math.round(CAMERA_HEIGHT * 0.92);
const CARD_WIDTH = Math.round((CARD_HEIGHT * 63) / 88);
export const CARD = {
  x: Math.round((CAMERA_WIDTH - CARD_WIDTH) / 2),
  y: Math.round((CAMERA_HEIGHT - CARD_HEIGHT) / 2),
  width: CARD_WIDTH,
  height: CARD_HEIGHT,
} as const;
const INK_LUMA = 30;
const PIXEL = 4; // size of one font dot

/** 5 x 7 dots per letter, only the letters of the title. */
const GLYPHS: Record<string, readonly string[]> = {
  L: ['10000', '10000', '10000', '10000', '10000', '10000', '11111'],
  I: ['11111', '00100', '00100', '00100', '00100', '00100', '11111'],
  G: ['01110', '10001', '10000', '10111', '10001', '10001', '01111'],
  H: ['10001', '10001', '10001', '11111', '10001', '10001', '10001'],
  T: ['11111', '00100', '00100', '00100', '00100', '00100', '00100'],
  N: ['10001', '11001', '10101', '10011', '10001', '10001', '10001'],
  B: ['11110', '10001', '10001', '11110', '10001', '10001', '11110'],
  O: ['01110', '10001', '10001', '10001', '10001', '10001', '01110'],
  ' ': ['00000', '00000', '00000', '00000', '00000', '00000', '00000'],
};

function drawTitle(luma: Uint8Array): void {
  const left = CARD.x + Math.round(CARD.width * 0.07);
  const top = CARD.y + Math.round(CARD.height * 0.055);
  [...CARD_TITLE].forEach((letter, index) => {
    GLYPHS[letter].forEach((row, r) => {
      [...row].forEach((dot, c) => {
        if (dot !== '1') {
          return;
        }
        for (let dy = 0; dy < PIXEL; dy++) {
          const start = (top + r * PIXEL + dy) * CAMERA_WIDTH + left + (index * 6 + c) * PIXEL;
          luma.fill(INK_LUMA, start, start + PIXEL);
        }
      });
    });
  });
}
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
    drawTitle(luma);
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
