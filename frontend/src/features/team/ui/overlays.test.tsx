import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ConfirmDialog } from './overlays';

function buttons() {
  return [...document.body.querySelectorAll('nldd-modal-dialog nldd-button')].map((button) => [
    button.getAttribute('text'),
    button.getAttribute('appearance'),
  ]);
}

describe('ConfirmDialog', () => {
  it('makes the way back the primary button beside an irreversible action', () => {
    const { unmount } = render(
      <ConfirmDialog
        open
        text="Rol samenvoegen?"
        supportingText="Dit is niet terug te draaien."
        confirmText="Voeg samen"
        destructive
        onConfirm={() => undefined}
        onClose={() => undefined}
      />,
    );
    expect(buttons()).toEqual([
      ['Annuleer', 'primary'],
      ['Voeg samen', 'destructive'],
    ]);
    unmount();
  });

  it('leaves the confirmation as the primary button when nothing is lost', () => {
    const { unmount } = render(
      <ConfirmDialog
        open
        text="Versturen?"
        supportingText="Het verzoek gaat naar de financiële administratie."
        confirmText="Verstuur"
        onConfirm={() => undefined}
        onClose={() => undefined}
      />,
    );
    const [back, confirm] = buttons();
    expect(back?.[1]).not.toBe('primary');
    expect(confirm).toEqual(['Verstuur', 'primary']);
    unmount();
  });
});
