import { HttpErrorResponse, HttpHeaders } from '@angular/common/http';

import { describeFailure, plainMessage } from './problem';

const failure = (status: number, error: unknown, headers: Record<string, string> = {}) =>
  new HttpErrorResponse({ status, error, headers: new HttpHeaders(headers), statusText: 'Status' });

describe('plainMessage', () => {
  it.each([
    [0, 'cannot be reached'],
    [401, 'session has ended'],
    [403, 'do not have access'],
    [404, 'could not find'],
    [409, 'conflicts'],
    [422, 'not valid'],
    [503, 'not available'],
    [500, 'on our side'],
    [418, 'could not be completed'],
  ])('describes status %i in plain language', (status, fragment) => {
    expect(plainMessage(status, null)).toContain(fragment);
  });

  it('mentions the wait time when the server gave one', () => {
    expect(plainMessage(429, 7)).toContain('7 seconds');
    expect(plainMessage(429, null)).toContain('Wait a moment');
  });
});

describe('describeFailure', () => {
  it('reads a problem document, including the correlation id and the offending fields', () => {
    const result = describeFailure(
      failure(422, {
        type: 'urn:mtgvault:problem:validation-failed',
        title: 'Unprocessable Content',
        status: 422,
        detail: 'The request is invalid.',
        correlation_id: 'abc-123',
        errors: [{ field: 'quantity', message: 'must be positive' }],
      }),
    );
    expect(result.correlationId).toBe('abc-123');
    expect(result.fields).toEqual([{ field: 'quantity', message: 'must be positive' }]);
    expect(result.message).toContain('not valid');
    expect(result.technical).toBe('Unprocessable Content: The request is invalid.');
  });

  it('falls back to the X-Request-ID header when the body is not a problem document', () => {
    const result = describeFailure(failure(500, 'boom', { 'X-Request-ID': 'from-header' }));
    expect(result.correlationId).toBe('from-header');
    expect(result.fields).toEqual([]);
  });

  it('reports Retry-After seconds and ignores nonsense values', () => {
    expect(describeFailure(failure(429, null, { 'Retry-After': '9' })).retryAfterSeconds).toBe(9);
    expect(
      describeFailure(failure(429, null, { 'Retry-After': 'soon' })).retryAfterSeconds,
    ).toBeNull();
  });

  it('handles a failure with no response at all', () => {
    const result = describeFailure(
      new HttpErrorResponse({ status: 0, error: new ProgressEvent('error') }),
    );
    expect(result.status).toBe(0);
    expect(result.correlationId).toBeNull();
    expect(result.message).toContain('cannot be reached');
  });
});
