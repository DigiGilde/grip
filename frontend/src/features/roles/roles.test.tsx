import { act, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi, texts } from '@/features/team/ui/testing';
import { AUTHENTICATED, renderApp } from '@/test/utils';
import type { CatalogueRole } from './api';
import { RolePicker } from './RolePicker';
import { RolesAdminPage } from './RolesAdminPage';
import { foldName, hasExactRole, matchRoles, roleSyncSummary, usageText } from './text';

function role(name: string, extra: Partial<CatalogueRole> = {}): CatalogueRole {
  return {
    id: `r-${name}`,
    name,
    description: null,
    source: 'manual',
    is_active: true,
    needs_review: false,
    usage_count: 0,
    ...extra,
  };
}

const DEVELOPER = role('Developer', { source: 'wies', usage_count: 3 });
const OWNER = role('Product owner', {
  source: 'wies',
  description: 'Bepaalt wat er gebouwd wordt',
});
const MANAGER = role('Productmanager');
const ANALYST = role('Data-analist', { needs_review: true, usage_count: 1 });
const ROLES = [ANALYST, DEVELOPER, OWNER, MANAGER];

function list(items: CatalogueRole[], canAdd = true, canManage = false) {
  return { items, can_add: canAdd, can_manage: canManage };
}

/** Fires an nldd custom event the way the element does: on itself, with a detail. */
function fire(el: Element, type: string, value: string) {
  act(() => {
    el.dispatchEvent(new CustomEvent(type, { detail: { value } }));
  });
}

function itemTexts(container: ParentNode): string[] {
  return texts(container, 'nldd-menu-item');
}

afterEach(() => vi.unstubAllGlobals());

describe('text helpers', () => {
  it('compares names without capitals, accents or extra spaces', () => {
    expect(foldName('  Product   Ówner ')).toBe('product owner');
    expect(hasExactRole(ROLES, 'developer')).toBe(true);
    expect(hasExactRole(ROLES, 'develop')).toBe(false);
  });

  it('finds roles on every word and puts a name that starts with the query first', () => {
    expect(matchRoles(ROLES, 'product').map((r) => r.name)).toEqual([
      'Product owner',
      'Productmanager',
    ]);
    expect(matchRoles(ROLES, 'owner product').map((r) => r.name)).toEqual(['Product owner']);
    expect(matchRoles(ROLES, 'analist').map((r) => r.name)).toEqual(['Data-analist']);
    expect(matchRoles(ROLES, '')).toHaveLength(4);
  });

  it('says how often a role is used and what a sync changed', () => {
    expect(usageText(0)).toBe('Nergens in gebruik');
    expect(usageText(1)).toBe('1 begrotingsregel');
    expect(usageText(3)).toBe('3 begrotingsregels');
    expect(roleSyncSummary({ created: 4, adopted: 2, unchanged: 0 })).toBe(
      '4 toegevoegd, 2 gekoppeld aan een bestaande rol',
    );
  });
});

describe('RolePicker', () => {
  async function renderPicker(
    props: Partial<Parameters<typeof RolePicker>[0]> = {},
    canAdd = true,
  ) {
    mockApi({ '/api/catalogue-roles': list(ROLES, canAdd) });
    const onChange = vi.fn();
    const view = renderApp(<RolePicker label="Rol" value={null} onChange={onChange} {...props} />);
    await waitFor(() =>
      expect(view.container.querySelectorAll('nldd-menu-item').length).toBeGreaterThan(0),
    );
    return { container: view.container, onChange };
  }

  it('is one labelled combo box with the roles of the catalogue', async () => {
    const { container } = await renderPicker();
    expect(container.querySelector('nldd-form-field')?.getAttribute('label')).toBe('Rol');
    expect(container.querySelector('nldd-combo-box')?.getAttribute('accessible-label')).toBe('Rol');
    expect(itemTexts(container)).toEqual([
      'Data-analist',
      'Developer',
      'Product owner',
      'Productmanager',
    ]);
    // No free-text role field next to the selector.
    expect(container.querySelectorAll('nldd-text-field')).toHaveLength(0);
    const owner = container.querySelector('nldd-menu-item[text="Product owner"]');
    expect(owner?.getAttribute('details')).toBe('Bepaalt wat er gebouwd wordt');
  });

  it('narrows the list while typing and offers no add action while a role fits', async () => {
    const { container } = await renderPicker();
    const combo = container.querySelector('nldd-combo-box')!;
    fire(combo, 'input', 'developer');
    expect(itemTexts(container)).toEqual(['Developer']);
  });

  it('offers to add the typed name only when no role has it', async () => {
    const { container } = await renderPicker();
    const combo = container.querySelector('nldd-combo-box')!;
    fire(combo, 'input', 'Product');
    expect(itemTexts(container)).toEqual([
      'Product owner',
      'Productmanager',
      'Staat er niet tussen? Voeg "Product" toe als rol',
    ]);
    fire(combo, 'input', 'Scrum master');
    expect(itemTexts(container)).toEqual(['Staat er niet tussen? Voeg "Scrum master" toe als rol']);
  });

  it('offers no add action to a reader who may not add, or when switched off', async () => {
    const reader = await renderPicker({}, false);
    fire(reader.container.querySelector('nldd-combo-box')!, 'input', 'Scrum master');
    expect(itemTexts(reader.container)).toEqual([]);
    vi.unstubAllGlobals();

    const off = await renderPicker({ allowAdd: false });
    fire(off.container.querySelector('nldd-combo-box')!, 'input', 'Scrum master');
    expect(itemTexts(off.container)).toEqual([]);
  });

  it('ignores the native input event that passes through the element', async () => {
    const { container } = await renderPicker();
    const combo = container.querySelector('nldd-combo-box')!;
    fire(combo, 'input', 'developer');
    act(() => {
      combo.dispatchEvent(new Event('input'));
    });
    expect(itemTexts(container)).toEqual(['Developer']);
  });

  it('hands the chosen role to the form', async () => {
    const { container, onChange } = await renderPicker();
    fire(container.querySelector('nldd-combo-box')!, 'change', 'Developer');
    expect(onChange).toHaveBeenCalledWith(DEVELOPER);
  });

  it('adds the typed role on the spot and says the beheerder will look at it', async () => {
    const { container, onChange } = await renderPicker();
    const combo = container.querySelector('nldd-combo-box')!;
    fire(combo, 'input', '  Scrum   master ');
    const created = role('Scrum master', { needs_review: true });
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === 'POST') {
          expect(JSON.parse(String(init.body))).toEqual({ name: 'Scrum master' });
          return new Response(JSON.stringify(created), {
            status: 201,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return new Response(JSON.stringify(list([...ROLES, created])), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }),
    );
    fire(combo, 'change', '__add__');
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(created));
    expect(container.querySelector('nldd-banner[variant="accent"]')?.getAttribute('text')).toBe(
      'De rol "Scrum master" is toegevoegd',
    );
  });

  it('shows the chosen role and clears it when the field is emptied', async () => {
    const { container, onChange } = await renderPicker({ value: 'Developer' });
    const combo = container.querySelector('nldd-combo-box') as HTMLElement & { text?: string };
    expect(combo.text).toBe('Developer');
    fire(combo, 'change', '');
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('leaves out the roles it is told to', async () => {
    const { container } = await renderPicker({ exclude: [DEVELOPER.id] });
    expect(itemTexts(container)).not.toContain('Developer');
  });
});

describe('RolesAdminPage', () => {
  const ADMIN = { ...AUTHENTICATED, functions: ['beheerder'] };

  async function renderAdmin(status: object, items = ROLES) {
    mockApi({
      '/api/catalogue-roles/sync': status,
      '/api/catalogue-roles': list(items, true, true),
    });
    const view = renderApp(<RolesAdminPage />, { path: '/beheer/rollen', auth: ADMIN });
    await waitFor(() => expect(view.container.querySelector('nldd-table')).not.toBeNull());
    await waitFor(() =>
      expect(view.container.querySelectorAll('nldd-table nldd-link').length).toBeGreaterThan(0),
    );
    return view.container;
  }

  it('lists the roles with origin, usage and status', async () => {
    const container = await renderAdmin({
      wies_configured: false,
      last_run: null,
      roles: 4,
      needs_review: 1,
    });
    const names = [...container.querySelectorAll('nldd-table nldd-link')].map((link) =>
      link.getAttribute('text'),
    );
    expect(names).toContain('Developer');
    const cells = texts(container, 'nldd-table nldd-text-cell');
    // The origin has a column because the roles come from two places.
    expect(cells).toContain('Wies');
    expect(cells).toContain('Zelf toegevoegd');
    expect(cells).toContain('3 begrotingsregels');
    expect(cells).toContain('Nergens in gebruik');
    // A label only for what differs: the role that still wants a look, first in the list.
    expect(container.querySelectorAll('nldd-tag[text="Te beoordelen"]')).toHaveLength(1);
    expect(
      container.querySelector('nldd-table-row:not([slot]) nldd-tag')?.getAttribute('text'),
    ).toBe('Te beoordelen');
    expect(container.querySelector('nldd-banner[variant="warning"]')).toBeNull();
    expect(container.textContent).toContain(
      'Eén rol is ter plekke toegevoegd en nog niet beoordeeld.',
    );
    // No text button in a row: the name opens the role.
    expect(container.querySelectorAll('nldd-table nldd-button')).toHaveLength(0);
  });

  it('says the list is kept by hand without the Wies link and hides the sync button', async () => {
    const container = await renderAdmin({
      wies_configured: false,
      last_run: null,
      roles: 4,
      needs_review: 0,
    });
    // Nothing is said about a link that is not there; the list is simply kept here.
    expect(container.textContent).not.toContain('Wies gaf');
    expect(container.querySelector('nldd-banner')).toBeNull();
    expect(container.querySelector('nldd-button[text="Haal rollen op uit Wies"]')).toBeNull();
    expect(
      container.querySelector('nldd-button[text="Nieuwe rol"]')?.getAttribute('appearance'),
    ).toBe('primary');
  });

  it('shows the last sync from Wies and offers to run it', async () => {
    const container = await renderAdmin({
      wies_configured: true,
      last_run: {
        id: 's-1',
        finished_at: '2026-10-08T10:00:00Z',
        status: 'completed',
        result: { seen: 14, created: 10, adopted: 2, unchanged: 2 },
        error: null,
      },
      roles: 14,
      needs_review: 0,
    });
    // A sync that went well is one quiet line, not a banner.
    expect(container.querySelector('nldd-banner')).toBeNull();
    expect(container.textContent).toContain(
      '10 toegevoegd, 2 gekoppeld aan een bestaande rol, 2 ongewijzigd',
    );
    expect(container.querySelector('nldd-button[text="Haal rollen op uit Wies"]')).not.toBeNull();
  });

  it('shows why a sync failed', async () => {
    const container = await renderAdmin({
      wies_configured: true,
      last_run: {
        id: 's-2',
        finished_at: '2026-10-08T10:00:00Z',
        status: 'failed',
        result: {},
        error: 'Wies is niet bereikbaar.',
      },
      roles: 4,
      needs_review: 0,
    });
    expect(
      container.querySelector('nldd-banner[variant="critical"]')?.getAttribute('supporting-text'),
    ).toBe('Wies is niet bereikbaar.');
  });

  it('opens a role to rename, switch off and merge', async () => {
    const container = await renderAdmin({
      wies_configured: false,
      last_run: null,
      roles: 4,
      needs_review: 1,
    });
    const edit = container.querySelector('nldd-link[accessible-label="Bewerk Data-analist"]')!;
    act(() => {
      edit.dispatchEvent(new Event('click'));
    });
    const sheet = document.body.querySelector('nldd-sheet')!;
    await waitFor(() => expect(sheet.querySelector('nldd-text-field')).not.toBeNull());
    expect(sheet.querySelector('nldd-text-field')?.getAttribute('value')).toBe('Data-analist');
    expect(sheet.querySelector('nldd-switch-field')?.getAttribute('label')).toBe(
      'Te kiezen op een begrotingsregel',
    );
    expect(texts(sheet, 'nldd-title')).toContain('Samenvoegen');
    // The role itself is not offered as what to merge it into.
    await waitFor(() =>
      expect(sheet.querySelectorAll('nldd-combo-box nldd-menu-item').length).toBeGreaterThan(0),
    );
    expect(texts(sheet, 'nldd-combo-box nldd-menu-item')).toEqual([
      'Developer',
      'Product owner',
      'Productmanager',
    ]);
    expect(sheet.querySelector('nldd-button[text="Voeg samen"]')?.hasAttribute('disabled')).toBe(
      true,
    );
  });
});
