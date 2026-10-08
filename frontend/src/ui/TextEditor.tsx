/**
 * The one editor for text that is stored with marks and shown formatted: a
 * vacancy text, a section of a quote, a standard text.
 *
 * It is the design system's text editor (nldd-text-editor): the text stays
 * plain text with marks, the formatting shows while you write and the marks
 * themselves stand dimmed beside it. The editor has no toolbar of its own;
 * this component gives it one with exactly the formats the text can hold,
 * and brings whatever is typed or pasted back to those (see ./text/marks).
 * A person never has to type a mark.
 *
 * Passages a standard text leaves open, "[vul aan: ...]", are counted next to
 * the toolbar with a way to step to the next one.
 */
import { useEffect, useImperativeHandle, useRef, useState, type Ref } from 'react';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { openPlaces, toStored, type TextMarks } from './text/marks';

if (import.meta.env.MODE !== 'test') void import('./text/register');

interface ActiveFormats {
  bold: boolean;
  italic: boolean;
  bulletList: boolean;
  orderedList: boolean;
  heading: number;
}

const NOTHING: ActiveFormats = {
  bold: false,
  italic: false,
  bulletList: false,
  orderedList: false,
  heading: 0,
};

/** The part of nldd-text-editor this component talks to. */
interface EditorElement extends HTMLElement {
  value: string;
  annotatable?: boolean;
  annotations?: { id: string; start: number; end: number }[];
  toggleBold(): void;
  toggleItalic(): void;
  toggleHeading(level: number): void;
  setList(type: 'none' | 'bullet' | 'ordered'): void;
  focus(): void;
  getSelection?(): { start: number; end: number; quote: string; empty: boolean };
  view?: {
    state: { doc: { toString(): string } };
    dispatch(spec: { selection: { anchor: number; head: number }; scrollIntoView: boolean }): void;
  };
}

export interface TextEditorHandle {
  /** Puts the caret on the n-th passage still to fill (from 0), selected. */
  goToOpenPlace(index: number): void;
  /** What is selected now, in offsets of the text; null without a selection. */
  selection(): { start: number; end: number; text: string } | null;
  focus(): void;
}

interface TextEditorProps {
  label: string;
  /** The text in its stored form. */
  value: string;
  onChange: (stored: string) => void;
  /** What this text can hold; the toolbar offers exactly that. */
  marks: TextMarks;
  hint?: string;
  optional?: boolean;
  required?: boolean;
  invalid?: boolean;
  /** How high the editor opens; it grows with the text. */
  rows?: number;
  /** Not to be edited now, for instance while a proposal is being written. */
  disabled?: boolean;
  /** Count the passages "[vul aan: ...]" and offer to step through them. */
  showOpenPlaces?: boolean;
  ref?: Ref<TextEditorHandle>;
}

function ToolButton({
  text,
  label,
  active,
  onPress,
}: {
  text: string;
  label: string;
  active: boolean;
  onPress: () => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onPress);
  return (
    <nldd-toggle-button
      ref={ref}
      type="button"
      size="sm"
      text={text}
      accessible-label={label}
      selected={orUndef(active)}
    />
  );
}

const OPEN_PLACE = /\[vul aan:[^\]\n]*\]/g;

export function TextEditor({
  label,
  value,
  onChange,
  marks,
  hint,
  optional,
  required,
  invalid,
  rows = 8,
  disabled,
  showOpenPlaces,
  ref,
}: TextEditorProps) {
  const editor = useRef<EditorElement>(null);
  const [active, setActive] = useState<ActiveFormats>(NOTHING);
  // What this component last handed up. A value that differs came from
  // outside (a reload, a conflict) and replaces what the editor holds.
  const handedUp = useRef(value);
  const nextPlace = useRef(0);

  useEffect(() => {
    const el = editor.current;
    if (!el) return;
    if (value !== handedUp.current || el.value === undefined || el.value === '') {
      if (el.value !== value) el.value = value;
      handedUp.current = value;
    }
  }, [value]);

  // The passages still to fill are tinted in the text. The editor carries a
  // mark along while the text around it changes, so the set is only handed
  // over again when a passage is filled in or a new one appears.
  const placesKey = showOpenPlaces
    ? openPlaces(value)
        .map((place) => place.what)
        .join('\u0000')
    : '';
  useEffect(() => {
    const el = editor.current;
    if (!el || !showOpenPlaces) return;
    el.annotatable = true;
    el.annotations = openPlaces(el.value ?? '').map((place, index) => ({
      id: `open-${index}`,
      start: place.start,
      end: place.end,
    }));
  }, [placesKey, showOpenPlaces]);

  useNlddEvent(editor, 'input', (event) => {
    const detail = (event as CustomEvent<{ value?: string }>).detail;
    const raw = typeof detail?.value === 'string' ? detail.value : (editor.current?.value ?? '');
    const stored = toStored(raw, marks);
    handedUp.current = stored;
    onChange(stored);
  });
  // On leaving the field the editor shows what is stored: a pasted mark the
  // text does not know has become the nearest one it does.
  useNlddEvent(editor, 'change', () => {
    const el = editor.current;
    if (!el) return;
    const stored = toStored(el.value ?? '', marks);
    if (stored !== el.value) el.value = stored;
  });
  useNlddEvent(editor, 'nldd-text-editor-state', (event) => {
    const formats = (event as CustomEvent<{ active?: ActiveFormats }>).detail?.active;
    if (formats) setActive(formats);
  });

  function goTo(index: number) {
    const el = editor.current;
    const view = el?.view;
    if (!el || !view) return;
    const matches = [...view.state.doc.toString().matchAll(OPEN_PLACE)];
    const match = matches[index % Math.max(matches.length, 1)];
    if (!match) return;
    view.dispatch({
      selection: { anchor: match.index, head: match.index + match[0].length },
      scrollIntoView: true,
    });
    el.focus();
  }

  useImperativeHandle(ref, () => ({
    goToOpenPlace: goTo,
    selection: () => {
      const picked = editor.current?.getSelection?.();
      if (!picked || picked.empty) return null;
      return { start: picked.start, end: picked.end, text: picked.quote };
    },
    focus: () => editor.current?.focus(),
  }));

  const open = showOpenPlaces ? openPlaces(value) : [];
  function press(command: (el: EditorElement) => void) {
    const el = editor.current;
    if (el && typeof el.toggleBold === 'function') command(el);
  }

  return (
    <nldd-form-field
      label={label}
      optional={orUndef(optional)}
      {...(hint ? { 'supporting-label': hint } : {})}
    >
      <nldd-container gap="8">
        <nldd-container layout="wrap" gap="4" vertical-alignment="center">
          {marks.heading ? (
            <ToolButton
              text="Kop"
              label="Maak van deze regel een kop"
              active={active.heading > 0}
              onPress={() => press((el) => el.toggleHeading(marks.heading ?? 2))}
            />
          ) : null}
          <ToolButton
            text="Lijst"
            label="Maak van deze regels een lijst"
            active={active.bulletList}
            onPress={() => press((el) => el.setList(active.bulletList ? 'none' : 'bullet'))}
          />
          {marks.numbered ? (
            <ToolButton
              text="Genummerd"
              label="Maak van deze regels een genummerde lijst"
              active={active.orderedList}
              onPress={() => press((el) => el.setList(active.orderedList ? 'none' : 'ordered'))}
            />
          ) : null}
          {marks.strong ? (
            <ToolButton
              text="Vet"
              label="Zet de selectie vet"
              active={active.bold}
              onPress={() => press((el) => el.toggleBold())}
            />
          ) : null}
          <ToolButton
            text="Cursief"
            label="Zet de selectie cursief"
            active={active.italic}
            onPress={() => press((el) => el.toggleItalic())}
          />
          {open.length > 0 ? (
            <>
              <nldd-spacer />
              <nldd-text size="sm" color="secondary">
                {open.length === 1
                  ? 'Nog 1 plek in te vullen'
                  : `Nog ${open.length} plekken in te vullen`}
              </nldd-text>
              <OpenPlaceButton
                onPress={() => {
                  goTo(nextPlace.current);
                  nextPlace.current = (nextPlace.current + 1) % open.length;
                }}
              />
            </>
          ) : null}
        </nldd-container>
        <nldd-text-editor
          ref={editor}
          appearance="input-field"
          accessible-label={label}
          rows={rows}
          required={orUndef(required)}
          invalid={orUndef(invalid)}
          disabled={orUndef(disabled)}
        />
      </nldd-container>
    </nldd-form-field>
  );
}

function OpenPlaceButton({ onPress }: { onPress: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onPress);
  return <nldd-button ref={ref} size="sm" appearance="secondary" text="Ga naar de volgende" />;
}
