import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import type { Person } from './api';
import { PersonSheet } from './PersonSheet';

const PERSON = {
  id: 'p-1',
  name: 'Rik Medewerker',
  email: 'rik@example.org',
  is_active: true,
  manager_id: null,
  manager_name: null,
} as Person;

afterEach(() => vi.unstubAllGlobals());

function mockLogin(bound: boolean) {
  const calls: { method: string; url: string }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      calls.push({ method, url: String(input) });
      const body = method === 'DELETE' ? { bound: false } : { bound };
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }),
  );
  return calls;
}

function renderSheet(mayManage: boolean) {
  renderApp(
    <PersonSheet person={PERSON} people={[PERSON]} mayManage={mayManage} day="2026-06-01" onClose={() => {}} />,
  );
}

const button = () => document.querySelector('nldd-button[text="Ontkoppel login"]');

describe('the login of a person', () => {
  it('lets the beheerder unbind a login that is bound', async () => {
    const calls = mockLogin(true);
    renderSheet(true);
    await waitFor(() => expect(button()).not.toBeNull());
    expect(button()).toHaveAttribute('accessible-label', 'Ontkoppel de login van Rik Medewerker');

    button()?.dispatchEvent(new Event('click'));
    await waitFor(() =>
      expect(calls).toContainEqual({ method: 'DELETE', url: '/api/people/p-1/login' }),
    );
  });

  it('offers nothing to unbind for someone who never logged in', async () => {
    mockLogin(false);
    renderSheet(true);
    await waitFor(() =>
      expect(document.querySelector('nldd-title[text="Inloggen"]')).toHaveAttribute(
        'supporting-text',
        'Nog niet ingelogd; de eerste keer inloggen koppelt het account',
      ),
    );
    expect(button()).toBeNull();
  });

  it('does not ask about the login for someone who does not manage persons', async () => {
    const calls = mockLogin(true);
    renderSheet(false);
    await waitFor(() => expect(document.querySelector('nldd-sheet')).not.toBeNull());
    expect(calls.filter((call) => call.url.endsWith('/login'))).toEqual([]);
    expect(button()).toBeNull();
  });
});
