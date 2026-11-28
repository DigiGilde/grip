import { act, screen, waitFor } from '@testing-library/react';
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AppRoutes } from '@/AppRoutes';
import { PAGE_HEADING_ID } from '@/pages/PageHeading';
import { renderApp } from '@/test/utils';
import { useRouteFocus } from './useRouteFocus';
import { internalHref } from './useRouterLinks';

let navigateTo: (path: string) => void = () => {};

function NavigateProbe() {
  const navigate = useNavigate();
  useEffect(() => {
    navigateTo = navigate;
  }, [navigate]);
  return null;
}

describe('focus after navigation', () => {
  it('leaves focus alone on first render and moves it to the heading after a route change', async () => {
    renderApp(
      <>
        <NavigateProbe />
        <AppRoutes />
      </>,
    );
    expect(document.body).toHaveFocus();

    act(() => navigateTo('/beheer/tarieven'));

    // The page is a file of its own; focus moves when it is shown.
    const heading = await screen.findByRole('heading', { level: 1, name: 'Tarieven' });
    // The text inside the heading takes the focus, so no ring is drawn.
    await waitFor(() => expect(heading.firstElementChild).toHaveFocus());
  });

  describe('when the heading comes after the route change', () => {
    function FocusProbe() {
      useRouteFocus();
      return null;
    }

    function addHeading(): HTMLElement {
      const heading = document.createElement('h1');
      heading.id = PAGE_HEADING_ID;
      heading.tabIndex = -1;
      document.body.append(heading);
      return heading;
    }

    it('waits for it', async () => {
      renderApp(
        <>
          <NavigateProbe />
          <FocusProbe />
        </>,
      );
      act(() => navigateTo('/later'));
      expect(document.body).toHaveFocus();

      const heading = addHeading();
      await waitFor(() => expect(heading).toHaveFocus());
      heading.remove();
    });

    it('follows a heading that is replaced by the real one', async () => {
      renderApp(
        <>
          <NavigateProbe />
          <FocusProbe />
        </>,
      );
      act(() => navigateTo('/later'));
      const loading = addHeading();
      await waitFor(() => expect(loading).toHaveFocus());

      loading.remove();
      const real = addHeading();
      await waitFor(() => expect(real).toHaveFocus());
      real.remove();
    });

    it('leaves a reader who went on after the heading took focus', async () => {
      renderApp(
        <>
          <NavigateProbe />
          <FocusProbe />
        </>,
      );
      act(() => navigateTo('/later'));
      const loading = addHeading();
      await waitFor(() => expect(loading).toHaveFocus());
      const field = document.createElement('input');
      document.body.append(field);
      field.focus();

      loading.remove();
      field.focus();
      const real = addHeading();
      await new Promise((resolve) => setTimeout(resolve, 250));
      expect(field).toHaveFocus();
      real.remove();
      field.remove();
    });

    it('stops looking for the previous route when the route changes again', () => {
      vi.useFakeTimers();
      try {
        renderApp(
          <>
            <NavigateProbe />
            <FocusProbe />
          </>,
        );
        act(() => navigateTo('/one'));
        const one = vi.getTimerCount();
        act(() => navigateTo('/two'));
        expect(vi.getTimerCount()).toBe(one);
      } finally {
        vi.useRealTimers();
      }
    });

    it('leaves the reader who moved on where they are', async () => {
      renderApp(
        <>
          <NavigateProbe />
          <FocusProbe />
        </>,
      );
      act(() => navigateTo('/later'));
      const field = document.createElement('input');
      document.body.append(field);
      field.focus();

      const heading = addHeading();
      await act(async () => {
        await Promise.resolve();
      });
      expect(field).toHaveFocus();
      heading.remove();
      field.remove();
    });
  });
});

describe('internalHref', () => {
  function clickOn(html: string, selector: string): string | null {
    const host = document.createElement('div');
    host.innerHTML = html;
    document.body.append(host);
    let result: string | null = 'unset';
    host.addEventListener('click', (event) => {
      result = internalHref(event);
      // jsdom does not implement following a link.
      event.preventDefault();
    });
    host
      .querySelector(selector)
      ?.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true, cancelable: true }));
    host.remove();
    return result;
  }

  it('returns the path of an in-app link', () => {
    expect(
      clickOn('<nldd-tab-bar-item href="/mensen/bord"><span>x</span></nldd-tab-bar-item>', 'span'),
    ).toBe('/mensen/bord');
  });

  it('leaves API and external links to the browser', () => {
    expect(clickOn('<a href="/api/auth/logout">x</a>', 'a')).toBeNull();
    expect(clickOn('<a href="https://example.org/">x</a>', 'a')).toBeNull();
    expect(clickOn('<a href="//example.org/">x</a>', 'a')).toBeNull();
  });

  it('returns null when nothing in the path is a link', () => {
    expect(clickOn('<button>x</button>', 'button')).toBeNull();
  });
});
