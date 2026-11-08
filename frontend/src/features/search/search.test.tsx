import { act, screen, waitFor } from '@testing-library/react';
import { Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi } from '@/features/assignments/testing';
import { renderApp } from '@/test/utils';
import type { SearchResults } from './api';
import { SearchField } from './SearchField';
import { SearchPage } from './SearchPage';

afterEach(() => vi.unstubAllGlobals());

const RESULTS: SearchResults = {
  q: 'voorbeeld',
  assignments: [
    { id: 'a1', name: 'Opdracht Alfa', client_name: 'Voorbeeldministerie', phase: 'active' },
  ],
  vacancies: [{ id: 'v1', title: 'Voorbeeld ontwikkelaar' }],
  people: [{ id: 'p1', name: 'Voorbeeld Een' }],
};

const NOTHING: SearchResults = { q: 'zzz', assignments: [], vacancies: [], people: [] };

function renderPage(path: string, results: SearchResults = RESULTS) {
  const fetchMock = mockApi({ '/api/search': results });
  const view = renderApp(<SearchPage />, { path });
  return { ...view, fetchMock };
}

const headings = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-title[heading-level="2"]')].map((t) =>
    t.getAttribute('text'),
  );

const hrefs = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-list-item')].map((item) => item.getAttribute('href'));

describe('the search page', () => {
  it('shows a list per kind, each with its heading and a link to the thing', async () => {
    const { container } = renderPage('/zoeken?q=voorbeeld');
    await waitFor(() => expect(headings(container)).toEqual(['Opdrachten', 'Vacatures', 'Mensen']));
    expect(hrefs(container)).toEqual(['/opdrachten/a1', '/vacatures/v1', '/mensen/p1']);
    const assignment = container.querySelector(
      'nldd-list-item[href="/opdrachten/a1"] nldd-text-cell',
    );
    expect(assignment?.getAttribute('text')).toBe('Opdracht Alfa');
    expect(assignment?.getAttribute('supporting-text')).toBe('Voorbeeldministerie');
  });

  it('leaves out a kind without results', async () => {
    const { container } = renderPage('/zoeken?q=voorbeeld', {
      ...RESULTS,
      vacancies: [],
      people: [],
    });
    await waitFor(() => expect(headings(container)).toEqual(['Opdrachten']));
  });

  it('says it in one line when nothing is found', async () => {
    const { container } = renderPage('/zoeken?q=zzz', NOTHING);
    await waitFor(() =>
      expect(container.querySelector('nldd-inline-dialog')?.getAttribute('text')).toBe(
        'Niets gevonden voor “zzz”',
      ),
    );
    expect(container.querySelector('nldd-list')).toBeNull();
  });

  it('asks nothing for one character, nothing at all or too long a text', () => {
    const short = renderPage('/zoeken?q=a');
    expect(short.container.querySelector('nldd-inline-dialog')?.getAttribute('text')).toBe(
      'Typ minstens 2 tekens.',
    );
    expect(short.fetchMock).not.toHaveBeenCalled();
    short.unmount();

    const none = renderPage('/zoeken');
    expect(none.container.querySelector('nldd-inline-dialog')?.getAttribute('text')).toBe(
      'Typ een woord of een naam om te zoeken.',
    );
    expect(none.fetchMock).not.toHaveBeenCalled();
    none.unmount();

    const long = renderPage(`/zoeken?q=${'x'.repeat(101)}`);
    expect(long.container.querySelector('nldd-inline-dialog')?.getAttribute('text')).toBe(
      'Gebruik hooguit 100 tekens.',
    );
    expect(long.fetchMock).not.toHaveBeenCalled();
  });

  it('sends the text without the spaces around it, whatever characters it holds', async () => {
    const { fetchMock } = renderPage(`/zoeken?q=${encodeURIComponent('  50% o_O "x"  ')}`);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const url = new URL(String(fetchMock.mock.calls[0]?.[0]), 'http://localhost');
    expect(url.searchParams.get('q')).toBe('50% o_O "x"');
  });

  it('puts focus on the heading when the results are there', async () => {
    renderPage('/zoeken?q=voorbeeld');
    const heading = await screen.findByRole('heading', { level: 1, name: 'Zoeken' });
    await waitFor(() => expect(heading.firstElementChild).toHaveFocus());
  });
});

function Where() {
  const { pathname, search } = useLocation();
  return <p data-testid="where">{pathname + search}</p>;
}

function renderField() {
  return renderApp(
    <>
      <SearchField />
      <Routes>
        <Route path="*" element={<Where />} />
      </Routes>
    </>,
    { path: '/' },
  );
}

const search = (container: HTMLElement, value: string) => {
  const field = container.querySelector('nldd-search-field') as HTMLElement;
  act(() => {
    field.dispatchEvent(new CustomEvent('search', { detail: { value } }));
  });
};

describe('the search field', () => {
  it('opens the search page with the text in the address on Enter', () => {
    const { container } = renderField();
    search(container, '  Zoë "x" 50%  ');
    expect(screen.getByTestId('where').textContent).toBe(
      `/zoeken?q=${new URLSearchParams({ q: 'Zoë "x" 50%' }).toString().slice(2)}`,
    );
  });

  it('stays where it is when nothing was typed', () => {
    const { container } = renderField();
    search(container, '   ');
    expect(screen.getByTestId('where').textContent).toBe('/');
  });

  it('shows the searched text on the search page and nothing elsewhere', () => {
    const a = renderApp(<SearchField />, { path: '/zoeken?q=alfa' });
    expect(a.container.querySelector('nldd-search-field')?.getAttribute('value')).toBe('alfa');
    a.unmount();
    const b = renderApp(<SearchField />, { path: '/' });
    expect(b.container.querySelector('nldd-search-field')?.getAttribute('value')).toBe('');
  });
});
