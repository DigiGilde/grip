import { act, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi, texts } from '@/features/team/ui/testing';
import { AUTHENTICATED, renderApp } from '@/test/utils';
import type { Organisation } from './api';
import { OrganisationPicker } from './OrganisationPicker';
import { OrganisationsAdminPage } from './OrganisationsAdminPage';
import { organisationDetails, organisationPlace, organisationText, syncSummary } from './text';

const MINISTRY: Organisation = {
  id: 'o-1',
  name: 'Voorbeeldzaken',
  label: 'Ministerie van Voorbeeldzaken',
  abbreviation: 'VZ',
  abbreviations: ['VZ'],
  organisation_types: ['Ministerie'],
  main_type: 'Ministerie',
  source: 'registry',
  parent_id: null,
  path: ['Ministerie van Voorbeeldzaken'],
  path_label: 'Ministerie van Voorbeeldzaken',
  tooi_uri: 'https://identifier.overheid.nl/tooi/id/ministerie/mnre9001',
  unit_key: null,
  instance_uri: null,
  source_url: null,
  end_date: null,
};
const DIRECTIE: Organisation = {
  ...MINISTRY,
  id: 'o-2',
  name: 'Directie Communicatie',
  label: 'Directie Communicatie',
  abbreviation: null,
  abbreviations: [],
  organisation_types: ['Organisatieonderdeel'],
  main_type: 'Organisatieonderdeel',
  parent_id: 'o-1',
  path: ['Ministerie van Voorbeeldzaken', 'Directie Communicatie'],
  path_label: 'Ministerie van Voorbeeldzaken > Directie Communicatie',
  tooi_uri: null,
};
const GUILD: Organisation = {
  ...DIRECTIE,
  id: 'o-3',
  name: 'Voorbeeldgilde',
  label: 'Voorbeeldgilde',
  source: 'manual',
  organisation_types: [],
  main_type: null,
  path: ['Ministerie van Voorbeeldzaken', 'Voorbeeldgilde'],
  path_label: 'Ministerie van Voorbeeldzaken > Voorbeeldgilde',
  unit_key: 'voorbeeldgilde',
};

function page(items: Organisation[]) {
  return { items, total: items.length, page: 1, page_size: 12 };
}

/** Fires an nldd custom event the way the element does: on itself, with a detail. */
function fire(el: Element, type: string, value: string) {
  act(() => {
    el.dispatchEvent(new CustomEvent(type, { detail: { value } }));
  });
}

afterEach(() => vi.unstubAllGlobals());

describe('text helpers', () => {
  it('shows the abbreviation with the label and the place above it', () => {
    expect(organisationText(MINISTRY)).toBe('Ministerie van Voorbeeldzaken (VZ)');
    expect(organisationText(DIRECTIE)).toBe('Directie Communicatie');
    expect(organisationPlace(DIRECTIE)).toBe('Ministerie van Voorbeeldzaken');
    expect(organisationPlace(MINISTRY)).toBe('');
  });

  it('says where an organisation sits, or what kind it is at the top', () => {
    expect(organisationDetails(DIRECTIE)).toBe('Ministerie van Voorbeeldzaken');
    expect(organisationDetails(MINISTRY)).toBe('Ministerie');
    expect(organisationDetails(GUILD)).toBe('Ministerie van Voorbeeldzaken · zelf toegevoegd');
  });

  it('sums up a sync run without the zero counts', () => {
    expect(syncSummary({ created: 3, updated: 0, unchanged: 10, closed: 1 })).toBe(
      '3 toegevoegd, 10 ongewijzigd, 1 afgesloten',
    );
    expect(syncSummary({})).toBe('Niets gewijzigd');
  });
});

describe('OrganisationPicker', () => {
  async function renderPicker(
    onChange = vi.fn(),
    props: Partial<Parameters<typeof OrganisationPicker>[0]> = {},
  ) {
    const api = mockApi({ '/api/organisations': page([MINISTRY, DIRECTIE]) });
    const view = renderApp(
      <OrganisationPicker label="Opdrachtgever" value={null} onChange={onChange} {...props} />,
    );
    await waitFor(() =>
      expect(view.container.querySelectorAll('nldd-menu-item').length).toBeGreaterThan(1),
    );
    return { ...view, api, onChange };
  }

  it('is one labelled combo box that leaves filtering to the server', async () => {
    const { container } = await renderPicker();
    const field = container.querySelector('nldd-form-field');
    const combo = container.querySelector('nldd-combo-box');
    expect(field?.getAttribute('label')).toBe('Opdrachtgever');
    expect(combo?.hasAttribute('no-filter')).toBe(true);
    expect(combo?.getAttribute('accessible-label')).toBe('Opdrachtgever');
    // No free-text field for a new organisation next to the selector.
    expect(container.querySelectorAll('nldd-text-field')).toHaveLength(0);
  });

  it('shows each result with its abbreviation and its place', async () => {
    const { container } = await renderPicker();
    const items = [...container.querySelectorAll('nldd-menu-item')];
    expect(items[0]?.getAttribute('text')).toBe('Ministerie van Voorbeeldzaken (VZ)');
    expect(items[1]?.getAttribute('text')).toBe('Directie Communicatie');
    expect(items[1]?.getAttribute('details')).toBe('Ministerie van Voorbeeldzaken');
  });

  it('ends with exactly one action to add an organisation', async () => {
    const { container } = await renderPicker();
    expect(texts(container, 'nldd-menu-item').filter((t) => t.startsWith('Staat er niet'))).toEqual(
      ['Staat er niet tussen? Voeg een organisatie toe'],
    );
    const last = [...container.querySelectorAll('nldd-menu-item')].at(-1);
    expect(last?.getAttribute('text')).toBe('Staat er niet tussen? Voeg een organisatie toe');
  });

  it('asks the server for what was typed', async () => {
    const { container, api } = await renderPicker();
    const combo = container.querySelector('nldd-combo-box')!;
    fire(combo, 'input', 'communicatie');
    await waitFor(() => expect(api.calls.some((url) => url.includes('q=communicatie'))).toBe(true));
  });

  it('ignores the native input event that passes through the element', async () => {
    const { container, api } = await renderPicker();
    const combo = container.querySelector('nldd-combo-box')!;
    fire(combo, 'input', 'communicatie');
    act(() => {
      combo.dispatchEvent(new Event('input'));
    });
    await waitFor(() => expect(api.calls.some((url) => url.includes('q=communicatie'))).toBe(true));
  });

  it('hands the chosen organisation to the form', async () => {
    const { container, onChange } = await renderPicker();
    fire(container.querySelector('nldd-combo-box')!, 'change', 'o-2');
    expect(onChange).toHaveBeenCalledWith(DIRECTIE);
  });

  it('opens the small form for the add action and picks what was added', async () => {
    const onChange = vi.fn();
    const { container } = await renderPicker(onChange);
    const combo = container.querySelector('nldd-combo-box')!;
    fire(combo, 'input', 'Voorbeeldgilde');
    fire(combo, 'change', '__add__');

    expect(onChange).not.toHaveBeenCalled();
    const name = container.querySelector('nldd-text-field');
    expect(name?.getAttribute('value')).toBe('Voorbeeldgilde');
    expect(texts(container, 'nldd-title')).toContain('Organisatie toevoegen');
    // The parent is chosen with the same search, without a second add action.
    const parent = container.querySelectorAll('nldd-combo-box')[1];
    expect(parent?.getAttribute('accessible-label')).toBe('Hoort bij');

    vi.stubGlobal(
      'fetch',
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === 'POST') {
          expect(JSON.parse(String(init.body))).toEqual({
            name: 'Voorbeeldgilde',
            parent_id: null,
          });
          return new Response(JSON.stringify(GUILD), {
            status: 201,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return new Response(JSON.stringify(page([MINISTRY, DIRECTIE, GUILD])), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }),
    );
    const add = container.querySelector('nldd-button[text="Voeg toe"]')!;
    act(() => {
      add.dispatchEvent(new Event('click'));
    });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(GUILD));
    expect(container.querySelector('nldd-text-field')).toBeNull();
  });

  it('can leave the add action out', async () => {
    const { container } = await renderPicker(vi.fn(), { allowAdd: false });
    expect(texts(container, 'nldd-menu-item').some((t) => t.startsWith('Staat er niet'))).toBe(
      false,
    );
  });

  it('clears the choice when the field is emptied', async () => {
    mockApi({
      '/api/organisations': page([MINISTRY]),
      '/api/organisations/o-1': MINISTRY,
    });
    const onChange = vi.fn();
    const view = renderApp(
      <OrganisationPicker label="Opdrachtgever" value="o-1" onChange={onChange} />,
    );
    await waitFor(() =>
      expect(view.container.querySelectorAll('nldd-menu-item').length).toBeGreaterThan(0),
    );
    // Give the fetch of the chosen organisation time to land.
    await waitFor(() =>
      expect(
        (view.container.querySelector('nldd-combo-box') as HTMLElement & { text?: string }).text,
      ).toBe('Ministerie van Voorbeeldzaken (VZ)'),
    );
    fire(view.container.querySelector('nldd-combo-box')!, 'change', '');
    expect(onChange).toHaveBeenCalledWith(null);
  });
});

describe('OrganisationsAdminPage', () => {
  const ADMIN = { ...AUTHENTICATED, functions: ['beheerder'] };

  async function renderAdmin(status: object, manual: Organisation[] = []) {
    mockApi({ '/api/organisations/sync': status, '/api/organisations': page(manual) });
    const view = renderApp(<OrganisationsAdminPage />, {
      path: '/beheer/organisaties',
      auth: ADMIN,
    });
    await waitFor(() =>
      expect(
        view.container.querySelector('nldd-button[text="Haal het register op"]'),
      ).not.toBeNull(),
    );
    return view.container;
  }

  it('says so when the register was never fetched', async () => {
    const container = await renderAdmin({
      running: false,
      running_since: null,
      last_run: null,
      registry_organisations: 0,
      manual_organisations: 0,
    });
    expect(container.querySelector('nldd-text')?.textContent).toContain(
      'Het register is nog niet opgehaald',
    );
  });

  it('shows when the register was last fetched and the manual organisations', async () => {
    const container = await renderAdmin(
      {
        running: false,
        running_since: null,
        last_run: {
          id: 'r-1',
          started_at: '2026-10-08T10:00:00Z',
          finished_at: '2026-10-08T10:04:00Z',
          status: 'completed',
          source_url: 'https://organisaties.overheid.nl/archive/exportOO.xml',
          result: { created: 12, unchanged: 3880, closed: 1 },
          error: null,
        },
        registry_organisations: 3893,
        manual_organisations: 1,
      },
      [GUILD],
    );
    // The state is one calm line; a result notice only right after fetching.
    expect(container.querySelector('nldd-banner')).toBeNull();
    const state = [...container.querySelectorAll('nldd-text')]
      .map((el) => el.textContent)
      .join(' ');
    expect(state).toContain('Laatst opgehaald op 8 okt 2026.');
    expect(state).toContain('3893 organisaties uit het register, 1 zelf toegevoegd.');
    await waitFor(() =>
      expect(texts(container, 'nldd-table nldd-text-cell')).toContain('Voorbeeldgilde'),
    );
    expect(texts(container, 'nldd-table nldd-text-cell')).toContain(
      'Ministerie van Voorbeeldzaken',
    );
  });

  it('shows why a run failed', async () => {
    const container = await renderAdmin({
      running: false,
      running_since: null,
      last_run: {
        id: 'r-2',
        started_at: '2026-10-08T10:00:00Z',
        finished_at: '2026-10-08T10:00:20Z',
        status: 'failed',
        source_url: 'https://organisaties.overheid.nl/archive/exportOO.xml',
        result: {},
        error: 'organisaties.overheid.nl is niet bereikbaar. Er is niets gewijzigd.',
      },
      registry_organisations: 3893,
      manual_organisations: 0,
    });
    expect(
      container.querySelector('nldd-banner[variant="critical"]')?.getAttribute('supporting-text'),
    ).toBe('organisaties.overheid.nl is niet bereikbaar. Er is niets gewijzigd.');
  });

  it('holds the button while a run is under way', async () => {
    const container = await renderAdmin({
      running: true,
      running_since: '2026-10-08T10:00:00Z',
      last_run: null,
      registry_organisations: 0,
      manual_organisations: 0,
    });
    expect(texts(container, 'nldd-inline-dialog')).toContain('Het register wordt opgehaald');
    expect(
      container.querySelector('nldd-button[text="Haal het register op"]')?.hasAttribute('disabled'),
    ).toBe(true);
  });
});
