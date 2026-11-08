import { TestBed } from '@angular/core/testing';

import { HomePage } from './home';

describe('HomePage', () => {
  it('welcomes the visitor', async () => {
    await TestBed.configureTestingModule({ imports: [HomePage] }).compileComponents();
    const fixture = TestBed.createComponent(HomePage);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('h1')?.textContent).toContain('Welcome to MTG Card Vault');
    expect(element.querySelector('[data-testid="welcome"]')?.textContent).toContain('private');
  });

  it('makes no API call', async () => {
    await TestBed.configureTestingModule({ imports: [HomePage] }).compileComponents();
    expect(() => TestBed.createComponent(HomePage)).not.toThrow();
  });
});
