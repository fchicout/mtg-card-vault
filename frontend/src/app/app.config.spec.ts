import { HttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';

import { ApiConfiguration } from './api';
import { appConfig } from './app.config';

describe('appConfig', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: appConfig.providers }));

  it('calls the API on the same origin', () => {
    expect(TestBed.inject(ApiConfiguration).rootUrl).toBe('');
  });

  it('provides the HTTP client used by the generated API client', () => {
    expect(TestBed.inject(HttpClient)).toBeTruthy();
  });
});
