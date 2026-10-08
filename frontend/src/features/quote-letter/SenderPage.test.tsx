import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi, texts } from '@/features/team/ui/testing';
import { renderApp } from '@/test/utils';
import type { QuoteSender } from './api';
import { SenderPage } from './SenderPage';

const DATA: QuoteSender = {
  sender: {
    organisation: 'Voorbeeldorganisatie',
    part_of: ['Voorbeeldministerie'],
    unit: 'VO | Voorbeeldgilde',
    visiting_address: ['Voorbeeldlaan 1', '1234 AB Voorbeeldstad'],
    postal_address: [],
    orders_email: 'opdrachten@voorbeeld.example',
    website: '',
    contact: { name: 'Vera Voorbeeld', role: 'Businessmanager', email: '', phone: '' },
    signatory: { on_behalf_of: 'het Voorbeeldgilde', name: '', title: '', organisation: '' },
  },
  text_blocks: [
    {
      key: 'inleiding',
      heading: 'Inleiding',
      body: '',
      hint: 'De aanleiding.',
      included: true,
      with_costs: false,
      numbered: true,
      draftable: true,
      required: false,
    },
    {
      key: 'kosten',
      heading: 'Kosten',
      body: '',
      hint: '',
      included: true,
      with_costs: true,
      numbered: true,
      draftable: false,
      required: false,
    },
    {
      key: 'scope',
      heading: 'Scope',
      body: 'Standaard.',
      hint: '',
      included: false,
      with_costs: false,
      numbered: true,
      draftable: false,
      required: false,
    },
  ],
  letter: { opening: 'Hierbij de offerte.', closing: '', billing_annex: true },
  ai_disclosure: false,
  drafting_available: false,
  profiles: ['digigilde'],
  placeholders: ['contactpersoon', 'opdrachtenadres'],
};

afterEach(() => vi.unstubAllGlobals());

async function renderPage(data: QuoteSender = DATA) {
  mockApi({ '/api/quote-sender': data });
  const view = renderApp(<SenderPage />, { path: '/beheer/afzender' });
  await waitFor(() => expect(view.container.querySelector('nldd-table')).not.toBeNull());
  return view.container;
}

describe('SenderPage', () => {
  it('shows the organisation, the people and the sections in order', async () => {
    const container = await renderPage();
    const cells = [...container.querySelectorAll('nldd-list nldd-text-cell')].map((cell) =>
      cell.getAttribute('text'),
    );
    expect(cells).toContain('Voorbeeldorganisatie');
    expect(cells).toContain('Voorbeeldlaan 1, 1234 AB Voorbeeldstad');
    expect(cells).toContain('Vera Voorbeeld (Businessmanager)');
    // A field nobody filled in says so instead of being left out.
    expect(cells).toContain('Nog niet ingevuld');
    expect(texts(container, 'nldd-table nldd-link')).toEqual(['Inleiding', 'Kosten', 'Scope']);
    const kinds = [...container.querySelectorAll('nldd-table nldd-text-cell')].map((cell) =>
      cell.getAttribute('text'),
    );
    expect(kinds).toContain('Schrijf je per offerte, concept mogelijk');
    expect(kinds).toContain('Bedragen uit de begroting');
    expect(kinds).toContain('Op verzoek');
  });

  it('offers a profile only while the organisation has no name', async () => {
    const named = await renderPage();
    expect(texts(named, 'nldd-button')).not.toContain('Neem de gegevens van digigilde over');
    vi.unstubAllGlobals();
    const fresh = await renderPage({
      ...DATA,
      sender: { ...DATA.sender, organisation: '' },
    });
    expect(texts(fresh, 'nldd-button')).toContain('Neem de gegevens van digigilde over');
  });

  it('says nothing about the language model when none is configured', async () => {
    const container = await renderPage();
    expect(texts(container, 'nldd-title')).not.toContain('Taalmodel');
  });
});
