// Runs before every spec (angular.json: test.setupFiles).
// 1) Clarity's core registers its global first: @clr/angular also creates window.CDS without a
//    version, and the core fails at import time when that happens before its own setup.
import '@cds/core/icon/register.js';

// 2) jsdom has no ResizeObserver, which Clarity's modal needs.
import { installResizeObserverStub } from './app/testing/resize-observer';

installResizeObserverStub();
