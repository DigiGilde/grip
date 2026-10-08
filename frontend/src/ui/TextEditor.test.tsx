import { act, render } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { QUOTE_SECTION_MARKS, VACANCY_TEXT_MARKS, type TextMarks } from './text/marks';
import { TextEditor } from './TextEditor';

type Editor = HTMLElement & { value?: string };

function Harness({ start, marks, places }: { start: string; marks: TextMarks; places?: boolean }) {
  const [text, setText] = useState(start);
  return (
    <>
      <TextEditor
        label="Tekst"
        value={text}
        onChange={setText}
        marks={marks}
        showOpenPlaces={places}
      />
      <output data-stored>{text}</output>
      <button onClick={() => setText('Van buiten vervangen.')}>vervang</button>
    </>
  );
}

const editorOf = (container: HTMLElement) => container.querySelector('nldd-text-editor') as Editor;
const type = (container: HTMLElement, value: string) =>
  act(() => {
    editorOf(container).value = value;
    editorOf(container).dispatchEvent(new CustomEvent('input', { detail: { value } }));
  });
const tools = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-toggle-button')].map((el) => el.getAttribute('text'));

describe('TextEditor', () => {
  it('offers exactly the formats the text can hold', () => {
    const vacancy = render(<Harness start="" marks={VACANCY_TEXT_MARKS} />);
    expect(tools(vacancy.container)).toEqual(['Kop', 'Lijst', 'Cursief']);
    vacancy.unmount();
    const quote = render(<Harness start="" marks={QUOTE_SECTION_MARKS} />);
    expect(tools(quote.container)).toEqual(['Kop', 'Lijst', 'Genummerd', 'Vet', 'Cursief']);
  });

  it('shows the stored text and hands up what is typed in the stored form', () => {
    const { container } = render(<Harness start="Begin." marks={VACANCY_TEXT_MARKS} />);
    expect(editorOf(container).value).toBe('Begin.');
    type(container, '# Kop\n\n* een\n1. twee\n\n**vet**');
    expect(container.querySelector('[data-stored]')?.textContent).toBe(
      '## Kop\n\n- een\n- twee\n\n*vet*',
    );
    // While typing the editor keeps what the person wrote; it is not rewritten under the caret.
    expect(editorOf(container).value).toBe('# Kop\n\n* een\n1. twee\n\n**vet**');
    // On leaving the field it shows what is stored.
    act(() => {
      editorOf(container).dispatchEvent(new CustomEvent('change'));
    });
    expect(editorOf(container).value).toBe('## Kop\n\n- een\n- twee\n\n*vet*');
  });

  it('takes a text that changed outside it, such as the version of a colleague', () => {
    const { container, getByText } = render(
      <Harness start="Mijn tekst" marks={VACANCY_TEXT_MARKS} />,
    );
    type(container, 'Mijn tekst, verder');
    act(() => getByText('vervang').click());
    expect(editorOf(container).value).toBe('Van buiten vervangen.');
  });

  it('counts the passages still to fill and offers the next one, only where asked', () => {
    const text = 'Wij zijn [vul aan: het team] en doen [vul aan: het werk].';
    const without = render(<Harness start={text} marks={VACANCY_TEXT_MARKS} />);
    expect(without.container.textContent).not.toContain('in te vullen');
    without.unmount();
    const { container } = render(<Harness start={text} marks={VACANCY_TEXT_MARKS} places />);
    expect(container.textContent).toContain('Nog 2 plekken in te vullen');
    expect(container.querySelector('nldd-button[text="Ga naar de volgende"]')).not.toBeNull();
    type(container, 'Wij zijn een klein team en doen [vul aan: het werk].');
    expect(container.textContent).toContain('Nog 1 plek in te vullen');
    type(container, 'Wij zijn een klein team en doen het werk.');
    expect(container.textContent).not.toContain('in te vullen');
    expect(container.querySelector('nldd-button[text="Ga naar de volgende"]')).toBeNull();
  });
});
