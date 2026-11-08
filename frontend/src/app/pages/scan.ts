import { HttpContext, HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { ClrModalModule } from '@clr/angular';

import {
  Api,
  addVaultEntry,
  getCard,
  scanCard,
  type CandidateDto,
  type CardDetail,
  type ScanResponse,
} from '../api';
import { CameraError, CameraService, type CameraFailure } from '../core/camera/camera.service';
import { HANDLES_OWN_ERRORS } from '../core/http/error.interceptor';
import { describeFailure } from '../core/http/problem';
import { EmptyState } from '../shared/states/empty-state';
import { EntryForm, type EntryValues } from '../shared/vault/entry-form';

type Phase = 'idle' | 'live' | 'scanning' | 'results';

/**
 * Scan a card with the camera (US-020..US-024, UC-04). The frame is sent once, the answer lists the
 * likeliest printings, and nothing is added to the vault until the person confirms one and its
 * quantity, condition and finish. Typing a name in the catalogue is always one click away.
 */
@Component({
  selector: 'app-scan-page',
  imports: [ClrModalModule, EmptyState, EntryForm, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    .stage {
      position: relative;
      width: min(100%, 36rem);
      aspect-ratio: 4 / 3;
      background: #000;
      border-radius: 3px;
      overflow: hidden;
    }
    video {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .guide {
      position: absolute;
      inset: 4% 0;
      margin: 0 auto;
      height: 92%;
      aspect-ratio: 63 / 88;
      border: 3px dashed #fff;
      border-radius: 12px;
      box-shadow: 0 0 0 100vmax rgb(0 0 0 / 35%);
      pointer-events: none;
    }
    .actions {
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
      margin: 1rem 0;
    }
    .candidates {
      list-style: none;
      padding: 0;
      margin: 1rem 0;
      display: grid;
      gap: 0.75rem;
    }
    .candidates li {
      display: flex;
      gap: 1rem;
      align-items: center;
      padding: 0.75rem;
      border: 1px solid var(--clr-global-borders-color, #b3b3b3);
      border-radius: 3px;
    }
    .candidates img {
      width: 4rem;
      aspect-ratio: 488 / 680;
      object-fit: contain;
    }
    .candidates .meta {
      flex: 1;
      min-width: 0;
    }
    .error {
      color: var(--clr-forms-invalid-color, #c92100);
    }
  `,
  template: `
    <h1 i18n="@@page.scan.title">Scan</h1>
    <p i18n="@@page.scan.intro">
      Hold the card inside the outline, with the title and the bottom line in view and good light.
      The picture is sent for reading and then discarded; nothing is saved until you confirm.
    </p>

    @if (problem(); as message) {
      <p class="error" role="alert" data-testid="scan-problem">{{ message }}</p>
    }

    @if (added(); as message) {
      <p class="alert alert-success" role="status" data-testid="scan-added">{{ message }}</p>
    }

    @if (phase() === 'idle') {
      <div class="actions">
        <button
          type="button"
          class="btn btn-primary"
          data-testid="start-camera"
          (click)="start()"
          i18n="@@scan.start"
        >
          Start camera
        </button>
        <a class="btn btn-outline" routerLink="/catalogue" i18n="@@scan.search">Search by name</a>
      </div>
    }

    @if (phase() === 'live' || phase() === 'scanning') {
      <div class="stage">
        <video #video autoplay playsinline muted data-testid="camera-preview"></video>
        <div class="guide" aria-hidden="true"></div>
      </div>
      <div class="actions">
        <button
          type="button"
          class="btn btn-primary"
          data-testid="capture"
          [disabled]="phase() === 'scanning'"
          (click)="capture()"
        >
          @if (phase() === 'scanning') {
            <ng-container i18n="@@scan.reading">Reading the card...</ng-container>
          } @else {
            <ng-container i18n="@@scan.capture">Scan this card</ng-container>
          }
        </button>
        <button
          type="button"
          class="btn btn-outline"
          data-testid="stop-camera"
          (click)="stop()"
          i18n="@@scan.stop"
        >
          Stop camera
        </button>
      </div>
    }

    @if (phase() === 'results' && result(); as r) {
      @if (r.candidates.length > 0) {
        <h2 i18n="@@scan.candidates">Is it one of these?</h2>
        <p data-testid="scan-read">
          <ng-container i18n="@@scan.read">We read:</ng-container> {{ r.text.title }}
          @if (r.text.collector) {
            ({{ r.text.collector }})
          }
        </p>
        <ul class="candidates" data-testid="candidates">
          @for (c of r.candidates; track c.card.id) {
            <li data-testid="candidate">
              @if (c.card.image_small; as src) {
                <img [src]="src" alt="" loading="lazy" />
              }
              <div class="meta">
                <strong>{{ c.card.name }}</strong
                ><br />
                {{ c.card.set_name }} ({{ c.card.set_code.toUpperCase() }})
                {{ c.card.collector_number }}
                @if (c.exact) {
                  <span class="label label-success" i18n="@@scan.exact">Exact match</span>
                }
                <br />
                <small>{{ percent(c) }}%</small>
              </div>
              <button
                type="button"
                class="btn btn-primary btn-sm"
                data-testid="choose"
                (click)="choose(c)"
                i18n="@@scan.choose"
              >
                This one
              </button>
            </li>
          }
        </ul>
      } @else {
        <app-empty-state [heading]="noMatchHeading(r)" icon="camera">
          <ng-container i18n="@@scan.noMatch.text"
            >Try again with more light and the whole card in the outline, or search for it by
            name.</ng-container
          >
        </app-empty-state>
      }
      <div class="actions">
        <button
          type="button"
          class="btn btn-outline"
          data-testid="scan-again"
          (click)="again()"
          i18n="@@scan.again"
        >
          Scan again
        </button>
        <a
          class="btn btn-outline"
          routerLink="/catalogue"
          [queryParams]="searchParams(r)"
          data-testid="manual-search"
          i18n="@@scan.manual"
          >Search by name</a
        >
      </div>
    }

    @if (chosen(); as c) {
      <clr-modal
        [clrModalOpen]="true"
        (clrModalOpenChange)="cancelChoice()"
        [clrModalClosable]="true"
        data-testid="confirm-dialog"
      >
        <h3 class="modal-title" i18n="@@scan.confirmTitle">Add to vault</h3>
        <div class="modal-body">
          <p>
            {{ c.name }} - {{ c.set_name }} ({{ c.set_code.toUpperCase() }})
            {{ c.collector_number }}
          </p>
          <app-entry-form
            [finishes]="c.finishes"
            [errors]="addErrors()"
            [busy]="busy()"
            [submitLabel]="addLabel"
            (submitted)="save($event)"
            (cancelled)="cancelChoice()"
          />
        </div>
      </clr-modal>
    }
  `,
})
export class ScanPage {
  private readonly api = inject(Api);
  private readonly camera = inject(CameraService);
  private readonly video = viewChild<ElementRef<HTMLVideoElement>>('video');
  private stream: MediaStream | null = null;

  protected readonly phase = signal<Phase>('idle');
  protected readonly problem = signal<string | null>(null);
  protected readonly result = signal<ScanResponse | null>(null);
  protected readonly chosen = signal<CardDetail | null>(null);
  protected readonly addErrors = signal<Record<string, string>>({});
  protected readonly added = signal<string | null>(null);
  protected readonly busy = signal(false);
  protected readonly addLabel = $localize`:@@scan.addSubmit:Add`;

  constructor() {
    // The camera light must go off as soon as the page is left.
    inject(DestroyRef).onDestroy(() => this.release());
  }

  protected async start(): Promise<void> {
    this.problem.set(null);
    this.added.set(null);
    try {
      this.stream = await this.camera.open();
    } catch (error) {
      this.problem.set(this.cameraMessage(error));
      return;
    }
    this.phase.set('live');
    // The <video> exists after the next render; attach the stream then.
    queueMicrotask(() => this.attach());
  }

  private attach(): void {
    const element = this.video()?.nativeElement;
    if (element && this.stream) {
      element.srcObject = this.stream;
    }
  }

  protected stop(): void {
    this.release();
    this.phase.set('idle');
  }

  protected again(): void {
    this.result.set(null);
    this.added.set(null);
    void this.start();
  }

  private release(): void {
    this.camera.close(this.stream);
    this.stream = null;
  }

  protected async capture(): Promise<void> {
    const element = this.video()?.nativeElement;
    if (!element || this.phase() !== 'live') {
      return;
    }
    this.problem.set(null);
    this.phase.set('scanning');
    try {
      const image = await this.camera.capture(element);
      const answer = await this.api.invoke(scanCard, { body: { image } }, this.own());
      this.release();
      this.result.set(answer);
      this.phase.set('results');
    } catch (error) {
      this.problem.set(this.scanMessage(error));
      this.phase.set('live');
    }
  }

  protected async choose(candidate: CandidateDto): Promise<void> {
    this.problem.set(null);
    this.addErrors.set({});
    try {
      this.chosen.set(await this.api.invoke(getCard, { card_id: candidate.card.id }, this.own()));
    } catch {
      this.problem.set($localize`:@@scan.loadFailed:That card could not be loaded. Try again.`);
    }
  }

  protected cancelChoice(): void {
    this.chosen.set(null);
    this.addErrors.set({});
  }

  protected async save(values: EntryValues): Promise<void> {
    const card = this.chosen();
    if (!card) {
      return;
    }
    this.busy.set(true);
    try {
      const entry = await this.api.invoke(
        addVaultEntry,
        { body: { card_id: card.id, ...values } },
        this.own(),
      );
      this.chosen.set(null);
      this.result.set(null);
      this.phase.set('idle');
      this.added.set(
        $localize`:@@scan.added:Added ${card.name}:name:. You now own ${entry.quantity}:quantity: of this printing.`,
      );
    } catch (error) {
      this.addErrors.set(this.fieldMessages(error));
    } finally {
      this.busy.set(false);
    }
  }

  protected percent(candidate: CandidateDto): number {
    return Math.round(candidate.confidence * 100);
  }

  protected noMatchHeading(result: ScanResponse): string {
    return result.reason === 'unreadable'
      ? $localize`:@@scan.unreadable:We could not read the card`
      : $localize`:@@scan.noMatchHeading:We did not find a matching card`;
  }

  protected searchParams(result: ScanResponse): Record<string, string> {
    return result.text.title ? { q: result.text.title } : {};
  }

  private fieldMessages(error: unknown): Record<string, string> {
    if (!(error instanceof HttpErrorResponse)) {
      return { _: $localize`:@@scan.addFailed:The card could not be added. Try again.` };
    }
    const failure = describeFailure(error);
    const byField: Record<string, string> = {};
    for (const problem of failure.fields) {
      byField[problem.field] = problem.message;
    }
    return Object.keys(byField).length > 0 ? byField : { _: failure.message };
  }

  private cameraMessage(error: unknown): string {
    const reason: CameraFailure = error instanceof CameraError ? error.reason : 'failed';
    switch (reason) {
      case 'denied':
        return $localize`:@@scan.denied:The camera is blocked. Allow it for this site in your browser, or search by name instead.`;
      case 'missing':
        return $localize`:@@scan.missing:No camera was found on this device. You can search by name instead.`;
      case 'unsupported':
        return $localize`:@@scan.unsupported:This browser cannot use the camera here. You can search by name instead.`;
      default:
        return $localize`:@@scan.cameraFailed:The camera could not be started. Try again.`;
    }
  }

  private scanMessage(error: unknown): string {
    const status = error instanceof HttpErrorResponse ? error.status : 0;
    switch (status) {
      case 413:
      case 415:
      case 422:
        return $localize`:@@scan.badImage:That picture could not be used. Try again.`;
      case 429:
        return $localize`:@@scan.rate:You are scanning very fast. Wait a moment and try again.`;
      case 503:
        return $localize`:@@scan.unavailable:The scanner is temporarily unavailable. You can search by name instead.`;
      default:
        return $localize`:@@scan.failed:The card could not be scanned. Try again.`;
    }
  }

  private own(): HttpContext {
    return new HttpContext().set(HANDLES_OWN_ERRORS, true);
  }
}
