import { describe, expect, it } from 'vitest';
import { renderApp } from '@/test/utils';
import { Page } from './primitives';

const READING = '720px';

describe('Page', () => {
  it('lets a worksheet use the full width', () => {
    const { container } = renderApp(
      <Page title="Begroting" kind="worksheet">
        <div data-testid="body" />
      </Page>,
    );
    expect(container.querySelector('nldd-simple-section')).toHaveAttribute('width', 'full');
    expect(container.querySelector(`nldd-container[max-width="${READING}"]`)).toBeNull();
  });

  it.each(['list', 'document'] as const)(
    'puts a %s in a reading column, the head and the body alike',
    (kind) => {
      const { container } = renderApp(
        <Page title="Opdrachten" kind={kind}>
          <div data-testid="body" />
        </Page>,
      );
      expect(container.querySelector('nldd-simple-section')).toHaveAttribute('width', 'full');
      const head = container.querySelector('[slot="header"]');
      expect(head).toHaveAttribute('max-width', READING);
      expect(head?.querySelector('h1')).toHaveTextContent('Opdrachten');
      const body = container.querySelector(`nldd-container[max-width="${READING}"]:not([slot])`);
      expect(body?.querySelector('[data-testid="body"]')).not.toBeNull();
    },
  );

  it('puts the back link above the title and the action on the title line', () => {
    const { container } = renderApp(
      <Page
        title="Begroting"
        kind="worksheet"
        back={{ href: '/a', text: 'Terug naar Alfa' }}
        action={<nldd-button appearance="primary" text="Nieuwe regel" />}
      >
        <div />
      </Page>,
    );
    const head = container.querySelector('[slot="header"]');
    expect(head?.querySelector('nldd-link')).toHaveAttribute('text', 'Terug naar Alfa');
    const line = head?.querySelector('.thing-title-line');
    expect(line?.querySelector('h1')).toHaveTextContent('Begroting');
    expect(line?.querySelector('nldd-button')).toHaveAttribute('text', 'Nieuwe regel');
  });

  it('puts the tabs in the head, with the title', () => {
    const { container } = renderApp(
      <Page
        title="Begroting"
        kind="worksheet"
        tabs={{
          label: 'Onderdelen van Alfa',
          current: 'budget',
          narrow: 'hide',
          items: [{ key: 'budget', text: 'Begroting', href: '/a/begroting' }],
        }}
      >
        <div />
      </Page>,
    );
    const head = container.querySelector('[slot="header"]');
    expect(head?.querySelector('nldd-menu-bar')).toHaveAttribute(
      'accessible-label',
      'Onderdelen van Alfa',
    );
    expect(head?.querySelector('h1')).not.toBeNull();
  });

  it('sets the document title', () => {
    renderApp(
      <Page title="Opdrachten" kind="list">
        <div />
      </Page>,
    );
    expect(document.title).toContain('Opdrachten');
  });
});
