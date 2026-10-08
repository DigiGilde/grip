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
import { RouterLinks } from '@/layout/RouterLinks';
import { BackLink } from '@/ui/Icon';
import { TabNav, type TabNavItem } from './TabNav';
import { useNarrow } from './useNarrow';

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

/** Where a page belongs: the one link above its title. */
export interface PageBack {
  href: string;
  /** "Terug naar <onderdeel>". */
  text: string;
}

interface TitleBlockProps {
  /** The h1, the document title and the text a screen reader announces. */
  title: string;
  /** One sentence that says what the page is for. Leave out when the title says it. */
  lead?: string;
  instanceName?: string;
  /** The page this one belongs to. Stands above the title, never under it. */
  back?: PageBack;
}

/**
 * The head of a page, in the header slot of the `nldd-simple-section` it sits
 * in: where the page belongs, then its title. `Page` uses it; a shell that
 * lays out its own section (a thing with tabs) uses it directly.
 */
export function TitleBlock({ title, lead, instanceName, back }: TitleBlockProps) {
  if (!back) return <PageHeading text={title} lead={lead} instanceName={instanceName} />;
  return (
    <nldd-container slot="header" gap={GAP.close}>
      <BackLink href={back.href} text={back.text} />
      <PageHeading text={title} lead={lead} instanceName={instanceName} inline />
    </nldd-container>
  );
}

interface PageProps extends TitleBlockProps {
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
  back,
  spacing = 'blocks',
  width,
  children,
}: PageProps) {
  return (
    <nldd-simple-section {...(width ? { width } : {})}>
      <TitleBlock title={title} lead={lead} instanceName={instanceName} back={back} />
      <Stack gap={spacing === 'sections' ? 'section' : 'group'}>{children}</Stack>
    </nldd-simple-section>
  );
}

interface ThingHeadProps extends TitleBlockProps {
  /**
   * What says what state the thing is in, right under its name: one line of
   * status and facts, its key figures.
   */
  children?: ReactNode;
  /**
   * The one next step on the thing, as its primary button. It stands on the
   * title line at the right (under the title on a narrow screen): part of
   * the head, never on top of the tabs.
   */
  action?: ReactNode;
  /** The course of the thing (a step bar), between the head and the tabs. */
  course?: ReactNode;
  /** The tabs of the thing; left out while it is loading or was not found. */
  tabs?: { label: string; items: readonly TabNavItem[]; current: string };
}

/** Spread as plain attributes; the package types do not list the padding overrides. */
const NO_BOTTOM_PADDING: object = { 'padding-bottom': '0' };

/**
 * The head of one open thing with tabs (an assignment, a vacancy): where it
 * belongs, its name with its one next step, what state it is in, its course,
 * and its tabs. Three kinds of thing stay apart: the action in the head, the
 * course, and the tabs after a clear distance. Each tab below is a section
 * of its own with its own top padding, so this section has none at the
 * bottom: the two would add up under the tabs.
 */
export function ThingHead({
  title,
  lead,
  instanceName,
  back,
  children,
  action,
  course,
  tabs,
}: ThingHeadProps) {
  return (
    <nldd-simple-section {...NO_BOTTOM_PADDING}>
      {/* The back link is an in-app link; the wrapper carries the header slot. */}
      <RouterLinks slot="header">
        <nldd-container gap={GAP.close}>
          {back && <BackLink href={back.href} text={back.text} />}
          <div className="thing-title-line">
            <PageHeading text={title} lead={lead} instanceName={instanceName} inline />
            {action ? <div className="thing-action">{action}</div> : null}
          </div>
        </nldd-container>
      </RouterLinks>
      <Stack gap="section">
        {children || course ? (
          <Stack gap="group">
            {children}
            {course}
          </Stack>
        ) : null}
        {tabs && <TabNav label={tabs.label} items={tabs.items} current={tabs.current} />}
      </Stack>
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
  /** Accessible name of the list. */
  label: string;
  facts: readonly Fact[];
  /** Width of the label column on a wide screen. */
  labelWidth?: string;
  /**
   * Leave out a fact without a value. By default it stays, as "Nog niet
   * ingevuld", so a missing value is visible; use this where a missing
   * value is no news (an optional field).
   */
  omitEmpty?: boolean;
}

function isEmpty(fact: Fact): boolean {
  return fact.value === undefined || fact.value === null || fact.value === '';
}

/**
 * Facts as "label: value" with the labels in one column. On a narrow screen
 * the label stands above its value, so a value keeps the full width and
 * wraps between words, never inside one.
 */
export function Facts({ label, facts, labelWidth = '220px', omitEmpty }: FactsProps) {
  const narrow = useNarrow();
  const shown = omitEmpty ? facts.filter((fact) => !isEmpty(fact)) : facts;
  return (
    <nldd-list accessible-label={label}>
      {shown.map((fact) => {
        const empty = isEmpty(fact);
        const plain = typeof fact.value === 'string' || typeof fact.value === 'number';
        if (narrow) {
          return (
            <nldd-list-item key={fact.label}>
              {empty || plain ? (
                <nldd-text-cell
                  overline={fact.label}
                  text={empty ? 'Nog niet ingevuld' : String(fact.value)}
                  {...(empty ? { color: 'secondary' } : {})}
                />
              ) : (
                <nldd-cell width="full">
                  <nldd-container gap={GAP.tight}>
                    <Quiet>{fact.label}</Quiet>
                    {fact.value}
                  </nldd-container>
                </nldd-cell>
              )}
            </nldd-list-item>
          );
        }
        return (
          <nldd-list-item key={fact.label}>
            <nldd-text-cell width={labelWidth} color="secondary" text={fact.label} />
            {empty ? (
              <nldd-text-cell color="secondary" text="Nog niet ingevuld" />
            ) : plain ? (
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

interface NameLineProps {
  /** The name: a link, or text. One line of body size; a row is never a heading. */
  children: ReactNode;
  /** Status labels that belong to the name. They sit on the name's line, centred on it. */
  badges?: ReactNode;
  /** One quiet line under the name. */
  detail?: ReactNode;
}

/**
 * A name with its status: the one way to put a badge behind a name.
 *
 * The name and its badges share a line and a centre, so a small badge does
 * not hang at the top of a taller name. When the line is too narrow the
 * badges move under the name, left-aligned, at the tight distance; they never
 * end up alone at the right.
 */
export function NameLine({ children, badges, detail }: NameLineProps) {
  return (
    <nldd-container gap={GAP.tight}>
      <nldd-container
        layout="wrap"
        gap={badges ? GAP.close : GAP.tight}
        vertical-alignment="center"
      >
        {children}
        {badges}
      </nldd-container>
      {detail ? <Quiet>{detail}</Quiet> : null}
    </nldd-container>
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
  return <nldd-inline-dialog variant="loading" text={text} data-state="loading" />;
}

export function ErrorNotice({ message }: { message: string }) {
  return <nldd-banner variant="critical" size="sm" text={message} data-state="error" />;
}

/** An empty state says what can be done here, not only that there is nothing. */
export function EmptyNotice({ text, supportingText }: { text: string; supportingText?: string }) {
  return (
    <nldd-inline-dialog
      text={text}
      data-state="empty"
      {...(supportingText ? { 'supporting-text': supportingText } : {})}
    />
  );
}

export interface KeyFigure {
  label: string;
  value: ReactNode;
  /** One quiet line under the value: the word that reads the figure. */
  detail?: ReactNode;
  /** The figure needs attention; said by its detail, shown by its colour. */
  critical?: boolean;
}

interface KeyFiguresProps {
  /** Accessible name of the group. */
  label: string;
  figures: readonly KeyFigure[];
}

/**
 * A few figures that sum up the thing a page is about: a quiet label over
 * each value, no box, wrapping to as many columns as fit. For the head of a
 * page; a table is for rows of the same kind.
 */
export function KeyFigures({ label, figures }: KeyFiguresProps) {
  return (
    <dl className="key-figures" aria-label={label}>
      {figures.map((figure) => (
        <div key={figure.label} className="key-figure">
          <dt>{figure.label}</dt>
          <dd className={figure.critical ? 'key-figure-value critical' : 'key-figure-value'}>
            {figure.value}
          </dd>
          {figure.detail ? <dd className="key-figure-detail">{figure.detail}</dd> : null}
        </div>
      ))}
    </dl>
  );
}

export interface Signal {
  /** Stable key. */
  key: string;
  /** What is the matter, in one sentence. A link when there is a place to act. */
  text: string;
  href?: string;
  /** What it is about, quiet, under the sentence. */
  detail?: ReactNode;
  /** 'critical' for what is wrong now; the rest waits. */
  tone?: 'critical' | 'warning' | 'info';
}

/**
 * Points that ask for attention, as one calm list: a sentence per point with
 * what it is about under it. Not a stack of banners: five banners of equal
 * weight say nothing about which matters.
 */
export function SignalList({ label, signals }: { label: string; signals: readonly Signal[] }) {
  return (
    <ul className="signal-list" aria-label={label}>
      {signals.map((signal) => (
        <li key={signal.key} className={`signal signal-${signal.tone ?? 'info'}`}>
          {signal.href ? (
            <nldd-link href={signal.href} text={signal.text} size="md" />
          ) : (
            <nldd-text>{signal.text}</nldd-text>
          )}
          {signal.detail ? <Quiet>{signal.detail}</Quiet> : null}
        </li>
      ))}
    </ul>
  );
}
