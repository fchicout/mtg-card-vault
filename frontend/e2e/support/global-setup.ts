import { writeCardVideo } from './fake-camera';

/** Runs once before the browsers start: Chromium needs the fake camera file to exist at launch. */
export default function globalSetup(): void {
  writeCardVideo();
}
