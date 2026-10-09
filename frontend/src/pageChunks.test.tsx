import { screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PageBoundary } from './PageBoundary';
import { lazyPage, loadChunk, page, preloadFor, reloadForNewBuild } from './pageChunks';
import { renderApp } from './test/utils';

describe('a file of the build that is gone after a deployment', () => {
  beforeEach(() => sessionStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('reloads the page once, and says so the second time', () => {
    const reload = vi.fn();
    expect(reloadForNewBuild(reload)).toBe(true);
    expect(reload).toHaveBeenCalledOnce();
    // Still missing right after the reload: reloading again cannot help.
    expect(reloadForNewBuild(reload)).toBe(false);
    expect(reload).toHaveBeenCalledOnce();
  });

  it('reloads again for a later deployment', () => {
    const reload = vi.fn();
    vi.spyOn(Date, 'now').mockReturnValue(1_000_000);
    expect(reloadForNewBuild(reload)).toBe(true);
    vi.spyOn(Date, 'now').mockReturnValue(1_000_000 + 60_000);
    expect(reloadForNewBuild(reload)).toBe(true);
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it('never loops when the browser keeps nothing', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const reload = vi.fn();
    expect(reloadForNewBuild(reload)).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });

  it('shows one failure with a way to load again when the file stays missing', async () => {
    // This tab reloaded a moment ago.
    sessionStorage.setItem('grip.chunk-reload', String(Date.now()));
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const Gone = lazyPage(
      () => Promise.reject<{ Gone: () => null }>(new TypeError('Failed to fetch')),
      'Gone',
    );
    const { container } = renderApp(
      <PageBoundary resetKey="/">
        <Gone />
      </PageBoundary>,
    );
    expect(await screen.findByText('Deze pagina laden is niet gelukt')).toBeInTheDocument();
    expect(container.querySelector('[data-state="unreachable"] nldd-button')).toHaveAttribute(
      'text',
      'Laad opnieuw',
    );
  });

  it('passes the failure on when reloading does not help', async () => {
    sessionStorage.setItem('grip.chunk-reload', String(Date.now()));
    await expect(loadChunk(() => Promise.reject(new TypeError('gone')))).rejects.toThrow('gone');
  });
});

describe('fetching a page ahead of the click', () => {
  it('fetches the files of the address, with or without a query', () => {
    const layout = vi.fn(async () => ({ Layout: () => null }));
    const tab = vi.fn(async () => ({ Tab: () => null }));
    const other = vi.fn(async () => ({ Other: () => null }));
    page(layout, 'Layout', '/proef/:id/*');
    page(tab, 'Tab', '/proef/:id/tab');
    page(other, 'Other', '/anders');

    preloadFor('/proef/1/tab?maand=2026-03');
    expect(layout).toHaveBeenCalledOnce();
    expect(tab).toHaveBeenCalledOnce();
    expect(other).not.toHaveBeenCalled();

    preloadFor('/proef/1');
    expect(layout).toHaveBeenCalledTimes(2);
    expect(tab).toHaveBeenCalledOnce();
  });

  it('leaves a file that is gone to the page that asks for it', () => {
    page(() => Promise.reject<{ Weg: () => null }>(new TypeError('gone')), 'Weg', '/weg');
    expect(() => preloadFor('/weg')).not.toThrow();
  });
});
