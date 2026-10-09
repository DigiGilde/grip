import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { LanguageModelPage } from './LanguageModelPage';

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

const STATUS = {
  provider: 'vlam',
  provider_text: 'VLAM',
  available: true,
  development: false,
  note: null,
  calls_per_person_per_hour: 40,
  calls_per_instance_per_hour: 400,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('LanguageModelPage', () => {
  it('says which model is connected, where it is used, the limits and what goes to it', async () => {
    stubApi({
      '/api/vacancy-texts/model': { body: STATUS },
      '/api/vacancies/language-model': {
        body: { configured: true, model_id: 'voorbeeldmodel-1', missing_settings: [] },
      },
    });
    const { container } = renderApp(<LanguageModelPage />);
    await waitFor(() =>
      expect(container.querySelector('nldd-button[text="Test de verbinding"]')).not.toBeNull(),
    );
    const cells = () =>
      [...container.querySelectorAll('nldd-list nldd-text-cell')].map((cell) =>
        cell.getAttribute('text'),
      );
    expect(cells()).toContain('VLAM');
    expect(cells()).toContain('40 verzoeken per uur');
    expect(cells()).toContain('400 verzoeken per uur');
    expect(cells().join(' ')).toContain('een voorstel bij een open plek');
    await waitFor(() => expect(cells()).toContain('voorbeeldmodel-1'));
    expect(container.textContent).toContain('Namen van collega’s en kandidaten');
    // What the organisation says about itself is content, not a setting here.
    expect(cells()).not.toContain('Niet ingesteld');
  });

  it('without a model says so and what is missing, and offers no test', async () => {
    stubApi({
      '/api/vacancy-texts/model': {
        body: {
          ...STATUS,
          provider: 'none',
          provider_text: 'Geen taalmodel ingesteld',
          available: false,
        },
      },
      '/api/vacancies/language-model': {
        body: { configured: false, missing_settings: ['VLAM_API_KEY', 'VLAM_MODEL_ID'] },
      },
    });
    const { container } = renderApp(<LanguageModelPage />);
    await waitFor(() =>
      expect(container.textContent).toContain(
        'Ontbreekt in de omgeving: VLAM_API_KEY, VLAM_MODEL_ID',
      ),
    );
    expect(container.textContent).toContain('Er is geen taalmodel verbonden');
    expect(container.querySelector('nldd-button[text="Test de verbinding"]')).toBeNull();
    expect(container.textContent).not.toContain('Wat ernaartoe gaat');
    expect(container.innerHTML).not.toContain('verzoeken per uur');
  });

  it('tells a viewer who is not the beheerder that this is not theirs', async () => {
    const denied = {
      status: 403,
      body: { title: 'Geen toegang', status: 403, detail: 'Je hebt hier geen toegang toe' },
    };
    stubApi({ '/api/vacancy-texts/model': denied, '/api/vacancies/language-model': denied });
    const { container } = renderApp(<LanguageModelPage />);
    await waitFor(() =>
      expect(container.querySelector('[data-state="no-access"]')?.textContent).toContain(
        'Beheer is voor beheerders',
      ),
    );
    expect(container.querySelector('nldd-button')).toBeNull();
  });
});
