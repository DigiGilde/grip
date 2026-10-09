import { act, screen } from '@testing-library/react';
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { renderApp } from '@/test/utils';
import { PageRange, Pager } from './Pager';
import { pageOf, usePaging } from './paging';

let navigateTo: (path: string) => void = () => {};

function List({ total }: { total: number | undefined }) {
  const navigate = useNavigate();
  useEffect(() => {
    navigateTo = navigate;
  }, [navigate]);
  const paging = usePaging(total, 50);
  return (
    <>
      <PageRange paging={paging} noun="opdrachten" />
      <Pager paging={paging} label="Pagina's van de opdrachten" />
      <output>{`${paging.page}/${paging.pages}`}</output>
    </>
  );
}

describe('a list in pages', () => {
  it('reads the page from the address and takes anything else for the first', () => {
    expect(pageOf(new URLSearchParams('pagina=3'))).toBe(3);
    for (const bad of ['pagina=0', 'pagina=-1', 'pagina=abc', 'pagina=1.5', ''])
      expect(pageOf(new URLSearchParams(bad))).toBe(1);
  });

  it('says which rows are shown and links to the other pages, keeping the filters', () => {
    const { container } = renderApp(<List total={320} />, {
      path: '/opdrachten?weergave=afgesloten&pagina=2',
    });
    expect(container.querySelector('[data-page-range]')).toHaveTextContent(
      '51 tot en met 100 van 320 opdrachten',
    );
    const pager = container.querySelector('nldd-pagination');
    expect(pager).toHaveAttribute('current', '2');
    expect(pager).toHaveAttribute('total', '7');
    expect(pager).toHaveAttribute('href-pattern', '/opdrachten?weergave=afgesloten&pagina={page}');
  });

  it('shows nothing of pages for a list that fits on one', () => {
    const { container } = renderApp(<List total={50} />, { path: '/opdrachten' });
    expect(container.querySelector('[data-page-range]')).toBeNull();
    expect(container.querySelector('nldd-pagination')).toBeNull();
  });

  it('falls back to the last page when the address asks past the end', () => {
    renderApp(<List total={120} />, { path: '/opdrachten?pagina=9' });
    expect(screen.getByRole('status')).toHaveTextContent('3/3');
  });

  it('keeps the page of the address while the first answer is on its way', () => {
    renderApp(<List total={undefined} />, { path: '/opdrachten?pagina=4' });
    expect(screen.getByRole('status')).toHaveTextContent('4/4');
  });

  it('follows the pager without a reload and moves focus to the line above the rows', () => {
    const { container } = renderApp(<List total={320} />, { path: '/opdrachten' });
    const pager = container.querySelector('nldd-pagination')!;
    const change = new CustomEvent('page-change', { detail: { page: 3 }, cancelable: true });
    act(() => {
      pager.dispatchEvent(change);
    });
    // Handled by the router: the component must not follow the link itself.
    expect(change.defaultPrevented).toBe(true);
    const range = container.querySelector('[data-page-range]');
    expect(range).toHaveTextContent('101 tot en met 150 van 320 opdrachten');
    expect(range).toHaveFocus();

    // The back button returns to the page the reader came from.
    act(() => navigateTo('/opdrachten?pagina=3'));
    act(() => navigateTo('/opdrachten'));
    expect(container.querySelector('[data-page-range]')).toHaveTextContent(
      '1 tot en met 50 van 320',
    );
  });
});
