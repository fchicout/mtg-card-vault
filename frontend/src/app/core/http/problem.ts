import { HttpErrorResponse } from '@angular/common/http';

import type { FieldProblem, Problem } from '../../api/models';

/** What the interface needs to show about a failed request (FR-API-02). */
export interface FailureDetails {
  readonly status: number;
  readonly message: string;
  readonly technical: string;
  readonly correlationId: string | null;
  readonly fields: readonly FieldProblem[];
  readonly retryAfterSeconds: number | null;
}

const isProblem = (body: unknown): body is Problem =>
  typeof body === 'object' &&
  body !== null &&
  typeof (body as Problem).status === 'number' &&
  typeof (body as Problem).title === 'string';

/** Plain-language text per status. The server's own wording is only shown as a technical detail. */
export function plainMessage(status: number, retryAfterSeconds: number | null): string {
  switch (true) {
    case status === 0:
      return $localize`:@@error.unreachable:The server cannot be reached. Check your connection and try again.`;
    case status === 401:
      return $localize`:@@error.unauthorized:Your session has ended. Sign in again to continue.`;
    case status === 403:
      return $localize`:@@error.forbidden:You do not have access to this.`;
    case status === 404:
      return $localize`:@@error.notFound:We could not find what you asked for.`;
    case status === 409:
      return $localize`:@@error.conflict:This conflicts with the current state. Reload and try again.`;
    case status === 422:
      return $localize`:@@error.invalid:Some of the information is not valid.`;
    case status === 429:
      return retryAfterSeconds === null
        ? $localize`:@@error.rateLimited:Too many requests. Wait a moment and try again.`
        : $localize`:@@error.rateLimitedSeconds:Too many requests. Try again in ${retryAfterSeconds}:seconds: seconds.`;
    case status === 503:
      return $localize`:@@error.unavailable:A service this page depends on is not available. Try again in a moment.`;
    case status >= 500:
      return $localize`:@@error.server:Something went wrong on our side. Try again; if it keeps happening, give the support details to the operator.`;
    default:
      return $localize`:@@error.generic:The request could not be completed.`;
  }
}

export function describeFailure(error: HttpErrorResponse): FailureDetails {
  const problem = isProblem(error.error) ? error.error : null;
  const retryHeader = Number(error.headers?.get('Retry-After'));
  const retryAfterSeconds = Number.isFinite(retryHeader) && retryHeader > 0 ? retryHeader : null;
  const correlationId = problem?.correlation_id ?? error.headers?.get('X-Request-ID') ?? null;
  return {
    status: error.status,
    message: plainMessage(error.status, retryAfterSeconds),
    technical: problem ? `${problem.title}: ${problem.detail}` : error.statusText || 'No response',
    correlationId,
    fields: problem?.errors ?? [],
    retryAfterSeconds,
  };
}
