/**
 * Layout primitives: the few shapes every screen is built from.
 *
 * A screen composed from these sits on one grid and one spacing scale without
 * anyone choosing a pixel value. They are thin wrappers around design-system
 * components and tokens; nothing here sets a size or a colour of its own.
 *
 * Spacing scale (steps of the design system's spacing tokens):
 *   tight    4   inside one item: a label and its value
 *   close    8   between items of one kind: lines in a list of notes
 *   related 16   between parts that belong together: a heading and its content
 *   group   24   between blocks on a page: a filter row, a table, a notice
 *   section 48   between sections, each with its own heading
 * Whitespace shows the grouping: generous around a group, tight inside it.
 * Do not add a border or a box to show that things belong together.
 *
 * Type scale (few steps, each with one job):
 *   page title     nldd-title size 2, the one h1 of the page
 *   section title  nldd-title size 4, h2
 *   block title    nldd-title size 5, h3, only inside a section
 *   body           the default text
 *   secondary      nldd-text color="secondary" size="sm": labels, hints, dates
 * A row in a list or table is never a heading. Numbers are right-aligned in
 * tabular figures; the table and cell components do that.
 */
import type { ReactNode } from 'react';
import { PageHeading } from '@/pages/PageHeading';

// Tests leave the nldd-* elements unregistered on purpose, so they read the
// light DOM this app is responsible for.
if (import.meta.env.MODE !== 'test') void import('./register');

export type Gap = 'tight' | 'close' | 'related' | 'group' | 'section';

const GAP = {
  tight: '4',
  close: '8',
  related: '16',
  group: '24',
  section: '48',
} as const satisfies Record<Gap, string>;

interface StackProps {
  /** Distance between the children; see the scale above. */
  gap?: Gap;
  children: ReactNode;
}

/** Children under each other at one distance from the scale. */
export function Stack({ gap = 'related', children }: StackProps) {
  return <nldd-container gap={GAP[gap]}>{children}</nldd-container>;
}

interface PageProps {
  /** The h1, the document title and the text a screen reader announces. */
  title: string;
  /** One sentence that says what the page is for. Leave out when the title says it. */
  lead?: string;
  instanceName?: string;
  /**
   * 'blocks' for a page that is one thing (a filter row and a table);
   * 'sections' for a page made of Section parts.
   */
  spacing?: 'blocks' | 'sections';
  /** Body width, for a page that reads better narrow (a form, a notice). */
  width?: string;
  children: ReactNode;
}

/**
 * A page inside the application shell: the title in the section's header,
 * then the content at one rhythm. One Page per route.
 */
export function Page({
  title,
  lead,
  instanceName,
  spacing = 'blocks',
  width,
  children,
}: PageProps) {
  return (
    <nldd-simple-section {...(width ? { width } : {})}>
      <PageHeading text={title} lead={lead} instanceName={instanceName} />
      <Stack gap={spacing === 'sections' ? 'section' : 'group'}>{children}</Stack>
    </nldd-simple-section>
  );
}

interface SectionProps {
  title: string;
  /** One line under the title. Not an explanation of the interface. */
  description?: string;
  /** 2 directly on a page, 3 inside another section. */
  level?: 2 | 3;
  children: ReactNode;
}

/** A part of a page with its own heading. Shows what is; at most one action. */
export function Section({ title, description, level = 2, children }: SectionProps) {
  return (
    <nldd-container gap={GAP.related}>
      <nldd-title
        size={level === 2 ? 4 : 5}
        heading-level={level}
        text={title}
        {...(description ? { 'supporting-text': description } : {})}
      />
      {children}
    </nldd-container>
  );
}

/** A section heading on its own, for a screen that lays out its section itself. */
export function SectionHeading({ text, level = 2 }: { text: string; level?: 2 | 3 }) {
  return <nldd-title size={level === 2 ? 4 : 5} text={text} heading-level={level} />;
}

export interface Fact {
  label: string;
  /** Absent or empty shows "Nog niet ingevuld", so a missing value is visible. */
  value?: ReactNode;
}

interface FactsProps {
  /** Accessible name of the list, e.g. "Gegevens van de vacature". */
  label: string;
  facts: readonly Fact[];
  /** Width of the label column; one value per page keeps the values on one line. */
  labelWidth?: string;
}

/**
 * "Label: value" facts with the labels in one column, so every value starts
 * at the same place. For reading; editing happens in a sheet.
 */
export function Facts({ label, facts, labelWidth = '220px' }: FactsProps) {
  return (
    <nldd-list accessible-label={label}>
      {facts.map((fact) => {
        const empty = fact.value === undefined || fact.value === null || fact.value === '';
        return (
          <nldd-list-item key={fact.label}>
            <nldd-text-cell width={labelWidth} color="secondary" text={fact.label} />
            {empty ? (
              <nldd-text-cell color="secondary" text="Nog niet ingevuld" />
            ) : typeof fact.value === 'string' || typeof fact.value === 'number' ? (
              <nldd-text-cell text={String(fact.value)} />
            ) : (
              <nldd-cell width="full">{fact.value}</nldd-cell>
            )}
          </nldd-list-item>
        );
      })}
    </nldd-list>
  );
}

interface CardGridProps {
  /** Minimum width of a card; the grid fits as many per row as there is room for. */
  itemWidth?: string;
  children: ReactNode;
}

/** Cards in rows of equal height. */
export function CardGrid({ itemWidth = '280px', children }: CardGridProps) {
  return (
    <nldd-collection layout="grid" item-width={itemWidth} gap={GAP.related}>
      {children}
    </nldd-collection>
  );
}

/** Secondary text: a hint, a date, the context of a figure. */
export function Quiet({ children }: { children: ReactNode }) {
  return (
    <nldd-text size="sm" color="secondary">
      {children}
    </nldd-text>
  );
}

/** What a screen shows while loading, on an error, or when there is nothing. */
export function Loading({ text = 'Bezig met laden' }: { text?: string }) {
  return <nldd-inline-dialog variant="loading" text={text} />;
}

export function ErrorNotice({ message }: { message: string }) {
  return <nldd-banner variant="critical" size="sm" text={message} />;
}

/** An empty state says what can be done here, not only that there is nothing. */
export function EmptyNotice({ text, supportingText }: { text: string; supportingText?: string }) {
  return (
    <nldd-inline-dialog
      text={text}
      {...(supportingText ? { 'supporting-text': supportingText } : {})}
    />
  );
}
