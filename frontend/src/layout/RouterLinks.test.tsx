import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { RouterLinks } from './RouterLinks';

describe('RouterLinks', () => {
  it('makes no box of its own and takes over the slot of what it wraps', () => {
    const { container } = render(
      <MemoryRouter>
        <RouterLinks slot="header">
          <span>Titel</span>
        </RouterLinks>
      </MemoryRouter>,
    );
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper).toHaveAttribute('slot', 'header');
    expect(wrapper.style.display).toBe('contents');
  });

  it('carries no slot unless asked', () => {
    const { container } = render(
      <MemoryRouter>
        <RouterLinks>
          <span>Inhoud</span>
        </RouterLinks>
      </MemoryRouter>,
    );
    expect(container.firstElementChild).not.toHaveAttribute('slot');
  });
});
