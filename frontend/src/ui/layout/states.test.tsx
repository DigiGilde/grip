import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ApiError, loadFailure, retryLoad } from '@/api/client';
import { LoadError, NoAccess } from './states';

const refused = (status: number) => new ApiError(status, 'x', null, null);

describe('what a failed request for data is', () => {
  it('tells an answer about the reader from a failure to answer', () => {
    expect(loadFailure(refused(403))).toBe('no-access');
    expect(loadFailure(refused(401))).toBe('no-access');
    expect(loadFailure(refused(404))).toBe('not-found');
    expect(loadFailure(refused(500))).toBe('failed');
    expect(loadFailure(refused(502))).toBe('unreachable');
    expect(loadFailure(new TypeError('Failed to fetch'))).toBe('unreachable');
  });

  it('never asks again for an answer about the reader, and once for a failure to answer', () => {
    for (const status of [401, 403, 404, 409, 422])
      expect(retryLoad(0, refused(status))).toBe(false);
    expect(retryLoad(0, refused(503))).toBe(true);
    expect(retryLoad(1, refused(503))).toBe(false);
    expect(retryLoad(0, new TypeError('Failed to fetch'))).toBe(true);
  });
});

describe('LoadError', () => {
  it('says no access and for whom it is, never what was refused', () => {
    const { container } = render(
      <LoadError error={refused(403)} who="De bedragen zijn voor de eigenaar." retry={() => {}} />,
    );
    const state = container.querySelector('[data-state="no-access"]');
    expect(state?.textContent).toContain('Je hebt hier geen toegang');
    expect(state?.textContent).toContain('De bedragen zijn voor de eigenaar.');
    // Asking again cannot help, so it is not offered.
    expect(container.querySelector('nldd-button')).toBeNull();
  });

  it('does not tell not found from not allowed', () => {
    const { container } = render(<LoadError error={refused(404)} what="Deze opdracht" />);
    const state = container.querySelector('[data-state="not-found"]');
    expect(state?.textContent).toContain('Deze opdracht is niet gevonden');
    expect(state?.textContent).toContain('Het bestaat niet, of je hebt er geen toegang toe.');
  });

  it('offers to try again only when the server did not answer', () => {
    const { container } = render(<LoadError error={new TypeError('x')} retry={() => {}} />);
    expect(container.querySelector('[data-state="unreachable"]')).not.toBeNull();
    expect(container.querySelector('nldd-button')?.getAttribute('text')).toBe('Probeer opnieuw');
  });

  it("has one shape for every page that is not the reader's", () => {
    const { container } = render(<NoAccess who="Beheer is voor beheerders." />);
    expect(container.querySelector('[data-state="no-access"]')?.getAttribute('role')).toBe(
      'status',
    );
  });
});
