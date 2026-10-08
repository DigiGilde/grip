import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi, texts } from '@/features/team/ui/testing';
import { renderApp } from '@/test/utils';
import { RequestFormSection } from './RequestFormSection';
import { changedText, type RequestForms } from './requestForms';

const FORM = {
  id: 'd-2',
  file_name: 'aanvraagformulier.pdf',
  sha256: 'ab'.repeat(32),
  size_bytes: 1000,
  made_at: '2026-10-08T09:00:00Z',
  made_by_name: 'Vera Voorbeeld',
};

const BASE: RequestForms = {
  available: true,
  may_make: true,
  current: null,
  earlier: [],
  changed: [],
  signed: [],
};

afterEach(() => vi.unstubAllGlobals());

async function renderSection(data: RequestForms) {
  mockApi({ '/api/vacancies/v-1/request-forms': data });
  const view = renderApp(<RequestFormSection vacancyId="v-1" />);
  return view.container;
}

describe('RequestFormSection', () => {
  it('offers to make the form while none is kept', async () => {
    const container = await renderSection(BASE);
    await waitFor(() =>
      expect(texts(container, 'nldd-button')).toEqual(['Maak aanvraagformulier']),
    );
    expect(container.querySelector('nldd-list')).toBeNull();
  });

  it('shows the kept form and, with it up to date, only recording a signed copy', async () => {
    const container = await renderSection({ ...BASE, current: FORM });
    await waitFor(() =>
      expect(texts(container, 'nldd-button')).toEqual(['Leg het getekende formulier vast']),
    );
    const link = container.querySelector('nldd-list nldd-link');
    expect(link?.getAttribute('href')).toBe('/api/vacancies/v-1/request-forms/d-2');
    expect(container.querySelector('nldd-banner')).toBeNull();
  });

  it('says the form is out of date and what changed', async () => {
    const container = await renderSection({
      ...BASE,
      current: FORM,
      earlier: [{ ...FORM, id: 'd-1' }],
      changed: ['Schaal', 'Advies van HR'],
    });
    await waitFor(() => expect(container.querySelector('nldd-banner')).not.toBeNull());
    expect(container.querySelector('nldd-banner')?.getAttribute('supporting-text')).toBe(
      'Veranderd sinds het is gemaakt: Schaal en advies van HR.',
    );
    expect(texts(container, 'nldd-button')).toEqual([
      'Maak opnieuw',
      'Leg het getekende formulier vast',
    ]);
    expect(texts(container, 'nldd-list nldd-link')).toEqual([
      'Bekijk het aanvraagformulier',
      'Eerdere versie 1',
    ]);
  });

  it('gives a reader the files without actions, and nothing without a blank form', async () => {
    const reader = await renderSection({ ...BASE, current: FORM, may_make: false });
    await waitFor(() => expect(reader.querySelector('nldd-list')).not.toBeNull());
    expect(texts(reader, 'nldd-button')).toEqual([]);
    vi.unstubAllGlobals();
    const none = await renderSection({ ...BASE, available: false });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(none.querySelector('nldd-button')).toBeNull();
  });

  it('joins what changed as a sentence part', () => {
    expect(changedText(['Schaal'])).toBe('Schaal');
    expect(changedText(['Schaal', 'Aantal fte', 'Het akkoord'])).toBe(
      'Schaal, aantal fte en het akkoord',
    );
  });
});
