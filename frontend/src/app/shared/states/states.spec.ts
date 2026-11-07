import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { EmptyState } from './empty-state';
import { ErrorState } from './error-state';
import { LoadingState } from './loading-state';

@Component({
  imports: [EmptyState],
  template: `<app-empty-state heading="Nothing here" icon="library"
    >Add something. <button actions type="button">Add</button></app-empty-state
  >`,
})
class EmptyHost {}

describe('state patterns', () => {
  it('loading: an accessible spinner with a label', () => {
    const fixture = TestBed.createComponent(LoadingState);
    fixture.componentRef.setInput('label', 'Fetching cards');
    fixture.detectChanges();
    const spinner = (fixture.nativeElement as HTMLElement).querySelector('[role="status"]');
    expect(spinner?.textContent).toBe('Fetching cards');
  });

  it('empty: heading, explanation and actions are projected', () => {
    const fixture = TestBed.createComponent(EmptyHost);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('h2')?.textContent).toContain('Nothing here');
    expect(element.querySelector('.card-text')?.textContent).toContain('Add something.');
    expect(element.querySelector('.card-footer button')?.textContent).toBe('Add');
  });

  it('error: shows the message and emits retry', () => {
    const fixture = TestBed.createComponent(ErrorState);
    fixture.componentRef.setInput('message', 'It broke');
    const retried = vi.fn();
    fixture.componentInstance.retry.subscribe(retried);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('[data-testid="error"]')?.textContent).toBe('It broke');
    element.querySelector<HTMLButtonElement>('[data-testid="retry"]')!.click();
    expect(retried).toHaveBeenCalledOnce();
  });
});
