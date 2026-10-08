import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { WiesProposalsPage } from './WiesProposalsPage';

const PROPOSALS = {
  configured: true,
  fetched_at: '2026-10-08T09:00:00Z',
  wies_colleagues: 12,
  proposals: [
    {
      action: 'deactivate',
      email: 'weg@voorbeeld.example',
      name: 'Wim Weg',
      person_id: 'p-2',
      reason: 'Niet bekend in Wies.',
    },
    {
      action: 'add',
      email: 'nieuw@voorbeeld.example',
      name: 'Nina Nieuw',
      reason: 'Actief in Wies, nog niet in grip.',
      suborganization: 'Digi Gilde',
      skills: ['Developer'],
    },
    {
      action: 'rename',
      email: 'naam@voorbeeld.example',
      name: 'Noor Nieuwenaam',
      current_name: 'Noor Oudenaam',
      person_id: 'p-3',
      reason: 'De naam in Wies is anders.',
    },
  ],
};

function mockApi(get: unknown, post?: unknown) {
  const calls: { method: string; body: unknown }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      calls.push({ method, body: init?.body ? JSON.parse(String(init.body)) : null });
      return Promise.resolve(
        new Response(JSON.stringify(method === 'GET' ? get : post), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }),
  );
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

const attrs = (container: HTMLElement, selector: string, name: string) =>
  [...container.querySelectorAll(selector)].map((el) => el.getAttribute(name));

function tick(container: HTMLElement, label: string) {
  const box = container.querySelector(`nldd-checkbox-field[label="${label}"]`);
  expect(box).not.toBeNull();
  box?.dispatchEvent(new CustomEvent('change', { detail: { checked: true } }));
}

function click(container: HTMLElement, text: string) {
  const button = container.querySelector(`nldd-button[text="${text}"]`);
  expect(button).not.toBeNull();
  button?.dispatchEvent(new Event('click'));
}

describe('WiesProposalsPage', () => {
  it('says so when the link is not set up, and proposes nothing', async () => {
    mockApi({ configured: false, note: 'De koppeling met Wies is niet ingesteld.' });
    const { container } = renderApp(<WiesProposalsPage />);
    await waitFor(() =>
      expect(attrs(container, 'nldd-inline-dialog', 'text')).toEqual([
        'De koppeling met Wies is niet ingesteld',
      ]),
    );
    expect(container.querySelector('nldd-checkbox-field')).toBeNull();
    expect(container.querySelector('nldd-button[appearance="primary"]')).toBeNull();
  });

  it('groups the proposals, who comes in first and who leaves last', async () => {
    mockApi(PROPOSALS);
    const { container } = renderApp(<WiesProposalsPage />);
    await waitFor(() => expect(container.querySelector('nldd-checkbox-field')).not.toBeNull());

    expect(attrs(container, 'nldd-checkbox-field', 'label')).toEqual([
      'Toevoegen: Nina Nieuw',
      'Naam wijzigen: Noor Nieuwenaam',
      'Deactiveren: Wim Weg',
    ]);
    expect(attrs(container, 'nldd-list-item nldd-text-cell', 'text')).toEqual([
      'nieuw@voorbeeld.example · Digi Gilde · Developer',
      'naam@voorbeeld.example · heet nu Noor Oudenaam',
      'weg@voorbeeld.example',
    ]);
    // Nothing is ticked beforehand, and nothing can be confirmed yet.
    expect(container.querySelectorAll('nldd-checkbox-field[checked]')).toHaveLength(0);
    expect(container.querySelector('nldd-button[text="Voer door"]')).toHaveAttribute('disabled');
  });

  it('confirms only what was ticked and shows what was not applied', async () => {
    const calls = mockApi(PROPOSALS, {
      applied: [
        { action: 'add', email: 'nieuw@voorbeeld.example', applied: true, person_id: 'p-9' },
        {
          action: 'deactivate',
          email: 'weg@voorbeeld.example',
          applied: false,
          reason: 'Wies kent deze collega weer.',
        },
      ],
    });
    const { container } = renderApp(<WiesProposalsPage />);
    await waitFor(() => expect(container.querySelector('nldd-checkbox-field')).not.toBeNull());

    tick(container, 'Toevoegen: Nina Nieuw');
    tick(container, 'Deactiveren: Wim Weg');
    await waitFor(() =>
      expect(container.querySelector('nldd-button[text="Voer 2 wijzigingen door"]')).not.toBeNull(),
    );
    click(container, 'Voer 2 wijzigingen door');

    await waitFor(() =>
      expect(attrs(container, 'nldd-banner', 'text')).toContain('1 van 2 wijzigingen doorgevoerd'),
    );
    const post = calls.find((call) => call.method === 'POST');
    expect(post?.body).toEqual({
      changes: [
        { action: 'deactivate', email: 'weg@voorbeeld.example' },
        { action: 'add', email: 'nieuw@voorbeeld.example' },
      ],
    });
    expect(
      container.querySelector('nldd-text-cell[overline="Deactiveren: niet doorgevoerd"]'),
    ).toHaveAttribute('supporting-text', 'Wies kent deze collega weer.');
  });

  it('has nothing to do when grip and Wies agree', async () => {
    mockApi({ configured: true, wies_colleagues: 12, proposals: [] });
    const { container } = renderApp(<WiesProposalsPage />);
    await waitFor(() =>
      expect(attrs(container, 'nldd-inline-dialog', 'text')).toEqual(['Geen voorstellen']),
    );
  });
});
