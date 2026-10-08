import { act, screen } from '@testing-library/react';
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AppRoutes } from '@/AppRoutes';
import { renderApp } from '@/test/utils';
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
  it('leaves focus alone on first render and moves it to the heading after a route change', () => {
    renderApp(
      <>
        <NavigateProbe />
        <AppRoutes />
      </>,
    );
    expect(document.body).toHaveFocus();

    act(() => navigateTo('/tarieven'));

    const heading = screen.getByRole('heading', { level: 1, name: 'Tarieven' });
    expect(heading).toHaveFocus();
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
    host.querySelector(selector)?.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true, cancelable: true }));
    host.remove();
    return result;
  }

  it('returns the path of an in-app link', () => {
    expect(clickOn('<nldd-tab-bar-item href="/inzet"><span>x</span></nldd-tab-bar-item>', 'span')).toBe('/inzet');
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
