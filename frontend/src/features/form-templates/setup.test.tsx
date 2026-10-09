import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { VacancySetupPage } from './VacancySetupPage';

function stubApi(routes: Record<string, { status?: number; body: unknown }>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input).split('?')[0] ?? '';
      const route = routes[path] ?? { status: 404, body: { title: 'Niet gevonden', status: 404 } };
      const status = route.status ?? 200;
      return new Response(JSON.stringify(route.body), {
        status,
        headers: {
          'Content-Type': status < 400 ? 'application/json' : 'application/problem+json',
        },
      });
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('VacancySetupPage', () => {
  it('tells a viewer who is not the beheerder that this is not theirs', async () => {
    stubApi({
      '/api/form-templates': {
        status: 403,
        body: { title: 'Geen toegang', status: 403, detail: 'Je hebt hier geen toegang toe' },
      },
    });
    const { container } = renderApp(<VacancySetupPage />);
    await waitFor(() =>
      expect(container.querySelector('[data-state="no-access"]')?.textContent).toContain(
        'Beheer is voor beheerders',
      ),
    );
    expect(container.querySelector('nldd-button')).toBeNull();
  });

  it('shows the templates and which one is in use, and nothing about the model', async () => {
    stubApi({
      '/api/form-templates': {
        body: [
          {
            id: 'f-1',
            name: 'Aanvraagformulier vacature',
            file_name: 'formulier.pdf',
            is_active: true,
            created_at: '2026-10-01T09:00:00Z',
            uploaded_by_name: 'Fictieve Beheerder',
            mapped_fields: 27,
            unverified_fields: 0,
          },
          {
            id: 'f-0',
            name: 'Oud formulier',
            file_name: 'oud.pdf',
            is_active: false,
            created_at: '2026-09-01T09:00:00Z',
            mapped_fields: 20,
            unverified_fields: 2,
          },
        ],
      },
      '/api/form-templates/bundled-mappings': { body: [] },
    });
    const { container } = renderApp(<VacancySetupPage />);
    await waitFor(() =>
      expect(container.querySelector('nldd-tag[text="In gebruik"]')).not.toBeNull(),
    );
    // The form in use comes first; each row opens the form, the rest is in its menu.
    const links = [...container.querySelectorAll('nldd-table nldd-link')];
    expect(links.map((link) => link.getAttribute('text'))).toEqual([
      'Aanvraagformulier vacature',
      'Oud formulier',
    ]);
    const menus = [...container.querySelectorAll('nldd-table nldd-menu-item')].map((item) =>
      item.getAttribute('text'),
    );
    expect(menus).toEqual(['Vervang het formulier', 'Neem weer in gebruik']);
    expect(container.textContent).toContain('2 koppelingen niet gecontroleerd');
    // With a form in use, delivering a new one is not the main thing to do here.
    expect(container.querySelector('nldd-button[text="Lever een leeg formulier aan"]')).toBeNull();
    // The language model is a connection with its own page under Beheer.
    expect(container.textContent).not.toContain('Taalmodel');
    // The upload sheet stays in the document while closed.
    expect(document.body.querySelector('nldd-sheet')).not.toBeNull();
  });
});
