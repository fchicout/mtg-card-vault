import { TestBed } from '@angular/core/testing';

import { AuthService } from '../core/auth/auth.service';
import { SigninRequiredPage } from './signin-required';

describe('SigninRequiredPage', () => {
  function render(configured: boolean, inputs: Record<string, string> = {}) {
    const signIn = vi.fn(() => Promise.resolve());
    TestBed.configureTestingModule({
      imports: [SigninRequiredPage],
      providers: [{ provide: AuthService, useValue: { configured, signIn } }],
    });
    const fixture = TestBed.createComponent(SigninRequiredPage);
    for (const [name, value] of Object.entries(inputs)) {
      fixture.componentRef.setInput(name, value);
    }
    fixture.detectChanges();
    return { element: fixture.nativeElement as HTMLElement, signIn };
  }

  it('asks the visitor to sign in and signs in towards the saved route', () => {
    const { element, signIn } = render(true, { returnUrl: '/vault' });
    expect(element.textContent).toContain('You need to sign in');
    (element.querySelector('[data-testid="signin-retry"]') as HTMLButtonElement).click();
    expect(signIn).toHaveBeenCalledWith('/vault');
  });

  it('explains a failed sign-in and offers a retry', () => {
    const { element } = render(true, { failed: '1' });
    expect(element.textContent).toContain('cancelled or could not be completed');
    expect(element.querySelector('[data-testid="signin-retry"]')?.textContent).toContain(
      'Try again',
    );
  });

  it.each(['//evil.example', 'https://evil.example'])(
    'ignores the off-site target %s',
    (target) => {
      const { element, signIn } = render(true, { returnUrl: target });
      (element.querySelector('[data-testid="signin-retry"]') as HTMLButtonElement).click();
      expect(signIn).toHaveBeenCalledWith('/');
    },
  );

  it('says so when no provider is configured, with no button', () => {
    const { element } = render(false);
    expect(element.textContent).toContain('not available');
    expect(element.querySelector('[data-testid="signin-retry"]')).toBeNull();
  });
});
