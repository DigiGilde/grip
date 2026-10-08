import { useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { Button } from '@/features/assignments/ui';
import { ErrorNotice, Loading, SectionHeading } from '@/ui/layout';
import { formatDate, formatPeriod } from '@/lib/format';
import type { NodeLookup, NodePath, PathStep } from './api';
import { edgeTypeLabel, nodeTypeLabel } from './labels';
import { corpusLabel, endOf, notableStatus } from './summary';
import './register';

export interface NodeDetailSheetProps {
  /** The node to show; null closes the sheet. */
  uri: string | null;
  /** What the list already knows about a node, shown at once while the rest loads. */
  known: readonly NodeLookup[];
  /** Fetches a node the list does not hold: a step on a path. */
  fetchNode: (uri: string) => Promise<NodeLookup>;
  /** Part of the query key, so answers of another assignment or date are not reused. */
  scope: string;
  onClose: () => void;
}

function PathView({
  path,
  currentUri,
  onStep,
}: {
  path: NodePath;
  currentUri: string;
  onStep: (uri: string) => void;
}) {
  const steps = path.steps ?? [];
  const end = endOf(path);
  const label = end?.external
    ? `Pad naar ${corpusLabel(end)}`
    : `Pad naar ${end?.title ?? 'het eindpunt'}`;
  return (
    <ol aria-label={label} style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {steps.map((step, index) => (
        <li key={step.uri}>
          <StepView step={step} current={step.uri === currentUri} onStep={onStep} />
          {index < steps.length - 1 && step.edge_type ? (
            <nldd-container padding-inline="16" padding-block="4">
              <nldd-text size="sm">↓ {edgeTypeLabel(step.edge_type)}</nldd-text>
            </nldd-container>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

function StepView({
  step,
  current,
  onStep,
}: {
  step: PathStep;
  current: boolean;
  onStep: (uri: string) => void;
}) {
  if (step.external && !step.title) {
    // A step in another corpus: named as such, with the way to it.
    return (
      <nldd-container layout="wrap" gap="8">
        <nldd-badge color="neutral" text="Ander corpus" />
        <nldd-text>{corpusLabel(step)}</nldd-text>
        {step.resolvable ? (
          <Button
            text="Bekijk"
            size="sm"
            appearance="neutral-transparent"
            accessibleLabel={`Bekijk de node in ${corpusLabel(step)}`}
            onClick={() => onStep(step.uri)}
          />
        ) : null}
        <nldd-link href={step.uri} target="_blank" text="Open in dat corpus" />
      </nldd-container>
    );
  }
  const title = step.title ?? step.uri;
  return (
    <nldd-container layout="wrap" gap="8">
      <nldd-badge color={current ? 'accent' : 'neutral'} text={nodeTypeLabel(step.type ?? '')} />
      {current || !step.resolvable ? (
        <nldd-text>
          {current ? <strong>{title}</strong> : title}
          {current ? ' (deze node)' : ''}
        </nldd-text>
      ) : (
        <Button
          text={title}
          size="sm"
          appearance="neutral-transparent"
          accessibleLabel={`Bekijk ${title}`}
          onClick={() => onStep(step.uri)}
        />
      )}
    </nldd-container>
  );
}

function CopyUri({ uri }: { uri: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard
      ?.writeText(uri)
      .then(() => setCopied(true))
      .catch(() => setCopied(false));
  };
  return (
    <nldd-container gap="8">
      <nldd-text size="sm" style={{ overflowWrap: 'anywhere' }}>
        {uri}
      </nldd-text>
      <nldd-container layout="wrap" gap="16">
        <Button text="Kopieer URI" size="sm" onClick={copy} />
        <nldd-link href={uri} target="_blank" text="Open in het corpus" />
      </nldd-container>
      <nldd-text size="sm" aria-live="polite">
        {copied ? 'De URI is gekopieerd.' : ''}
      </nldd-text>
    </nldd-container>
  );
}

function Detail({ item, onStep }: { item: NodeLookup; onStep: (uri: string) => void }) {
  const node = item.node;
  if (!node) {
    return (
      <nldd-container gap="16">
        <nldd-banner
          variant="neutral"
          size="sm"
          text="Deze node is niet op te halen"
          supporting-text={item.problem ?? 'De verwijzing blijft bewaard zoals hij is.'}
        />
        <CopyUri key={item.uri} uri={item.uri} />
      </nldd-container>
    );
  }
  const status = notableStatus(node.status);
  const facts: [string, string][] = [
    ['Beheerd door', node.managing_organisation?.name ?? ''],
    ['Corpus', item.corpus_name ?? ''],
    ['Status', node.status ?? ''],
    ['Geldig', formatPeriod(node.valid_from, node.valid_until)],
  ];
  const paths = item.paths ?? [];
  return (
    <nldd-container gap="16">
      <nldd-container layout="wrap" gap="8">
        <nldd-badge color="accent" text={nodeTypeLabel(node.type)} />
        {status ? <nldd-badge color="warning" text={status} /> : null}
      </nldd-container>
      {node.description ? <nldd-text>{node.description}</nldd-text> : null}
      <nldd-list accessible-label="Gegevens van de node" appearance="box-base">
        {facts
          .filter(([, value]) => value !== '')
          .map(([label, value]) => (
            <nldd-list-item key={label}>
              <nldd-text-cell overline={label} text={value} />
            </nldd-list-item>
          ))}
      </nldd-list>

      <SectionHeading text="Waar dit uit voortkomt" level={2} />
      {item.falls_under ? (
        <nldd-text size="sm">
          Deze node valt onder {item.falls_under.title}, die ook aan deze opdracht is gekoppeld.
        </nldd-text>
      ) : null}
      {paths.length === 0 ? (
        <nldd-text size="sm">
          {node.type === 'politieke_input'
            ? 'Dit is zelf een politieke input: hier begint de keten.'
            : 'Het corpus kent voor deze node geen keten naar een politieke input.'}
        </nldd-text>
      ) : (
        paths.map((path) => (
          <PathView key={endOf(path)?.uri ?? 'pad'} path={path} currentUri={item.uri} onStep={onStep} />
        ))
      )}
      <nldd-text size="sm">
        Titel en status zijn die van {node.peildatum ? formatDate(node.peildatum) : 'vandaag'}.
        De keten is altijd de keten van nu: een corpus bewaart niet hoe de verbanden vroeger
        liepen.
      </nldd-text>

      <SectionHeading text="Verwijzing" level={2} />
      <CopyUri key={item.uri} uri={item.uri} />
    </nldd-container>
  );
}

/**
 * The detail of a node, on demand: its description, where it comes from as
 * paths, and the reference itself. A step on a path opens in the same sheet,
 * with the way back in the title bar. The sheet stays in the document while
 * closed, so its animation runs and focus returns to what opened it.
 */
export function NodeDetailSheet({ uri, known, fetchNode, scope, onClose }: NodeDetailSheetProps) {
  const sheetRef = useRef<HTMLElement>(null);
  const barRef = useRef<HTMLElement>(null);
  const titleId = useId();
  // The steps taken from the node the sheet was opened on.
  // Kept with the node they started from, so opening another card starts anew.
  const [walk, setWalk] = useState<{ from: string | null; steps: string[] }>({
    from: null,
    steps: [],
  });
  const trail = walk.from === uri ? walk.steps : [];
  const setTrail = (change: (steps: string[]) => string[]) =>
    setWalk({ from: uri, steps: change(trail) });

  const current = trail[trail.length - 1] ?? uri;
  const fromList = known.find((item) => item.uri === current);
  const query = useQuery({
    queryKey: ['nodes', 'detail', scope, current],
    queryFn: () => fetchNode(current as string),
    enabled: current !== null && fromList === undefined,
    retry: false,
  });
  const item = fromList ?? query.data;

  useNlddEvent(sheetRef, 'close', onClose);
  useNlddEvent(barRef, 'back', () => setTrail((steps) => steps.slice(0, -1)));

  const title = item?.node?.title ?? (current ? 'Node' : '');
  return createPortal(
    <nldd-sheet ref={sheetRef} open={orUndef(uri !== null)} placement="right" width="520px">
      <nldd-page>
        <nldd-top-title-bar
          ref={barRef}
          slot="header"
          text={title}
          dismiss-text="Sluit"
          collapse-anchor={titleId}
          {...(trail.length > 0 ? { 'back-text': 'Terug' } : {})}
        />
        <nldd-simple-section>
          <nldd-title id={titleId} slot="header" size={2} text={title} heading-level={1} />
          {current && !item && query.isPending ? <Loading text="Bezig met ophalen" /> : null}
          {query.isError && !item ? <ErrorNotice message={errorMessage(query.error)} /> : null}
          {item ? (
            <Detail item={item} onStep={(next) => setTrail((steps) => [...steps, next])} />
          ) : null}
        </nldd-simple-section>
      </nldd-page>
    </nldd-sheet>,
    document.body,
  );
}
