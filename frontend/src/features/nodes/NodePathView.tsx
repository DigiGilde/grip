import type { ReactNode } from 'react';
import { Quiet, Stack } from '@/ui/layout';
import type { NodePath, PathStep } from './api';
import { edgeTypeLabel, nodeTypeLabel } from './labels';
import { toTree, type PathBranch } from './pathTree';
import { corpusLabel } from './summary';
import './path.css';
import './register';

interface NodePathViewProps {
  paths: readonly NodePath[];
  /** The node the paths start at; its step is the marked one. */
  currentUri: string;
  /** Opens a step this instance can ask its corpus for. */
  onStep: (uri: string) => void;
}

interface StepRowProps {
  step: PathStep;
  first: boolean;
  last: boolean;
  /** The step is where a path ends. */
  end: boolean;
  current: boolean;
  /** Who manages the step before this one; said again only when it changes. */
  previousOrganisation: string | null;
  onStep: (uri: string) => void;
}

function isOtherCorpus(step: PathStep): boolean {
  return Boolean(step.external) && !step.title;
}

function StepRow({ step, first, last, end, current, previousOrganisation, onStep }: StepRowProps) {
  const elsewhere = isOtherCorpus(step);
  const kind = elsewhere ? 'Ander corpus' : nodeTypeLabel(step.type ?? '');
  const title = elsewhere ? corpusLabel(step) : (step.title ?? step.uri);
  const organisation =
    step.organisation_name && step.organisation_name !== previousOrganisation
      ? step.organisation_name
      : '';
  const opens = !current && step.resolvable === true;
  const leaves = !current && !opens && elsewhere;

  const content: ReactNode = (
    <>
      <nldd-text class="grip-path__kind" size="sm" color="secondary">
        {kind}
      </nldd-text>
      <nldd-text class="grip-path__title" weight={current ? 'bold' : undefined}>
        {title}
      </nldd-text>
      <nldd-text class="grip-path__by" size="sm" color="secondary">
        {organisation}
      </nldd-text>
      <span className="grip-path__mark">
        {current ? (
          <nldd-text size="sm" color="secondary">
            Deze node
          </nldd-text>
        ) : null}
        {end && !elsewhere ? (
          <nldd-text size="sm" color="secondary">
            Herkomst
          </nldd-text>
        ) : null}
        {opens ? <nldd-icon icon="chevron-right" size="16" /> : null}
        {leaves ? <nldd-icon icon="external-link" size="16" /> : null}
      </span>
    </>
  );

  const classes = [
    'grip-path__step',
    first ? 'grip-path__step--first' : '',
    last ? 'grip-path__step--last' : '',
    current ? 'grip-path__step--current' : '',
    end && !current ? 'grip-path__step--end' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <li className={classes} data-step-uri={step.uri}>
      <span className="grip-path__rail grip-path__rail--before" aria-hidden="true" />
      <span className="grip-path__rail grip-path__rail--marker" aria-hidden="true" />
      <span className="grip-path__rail grip-path__rail--after" aria-hidden="true" />
      {opens ? (
        <button
          type="button"
          className="grip-path__body"
          aria-label={`${kind}: ${title}. Bekijk`}
          onClick={() => onStep(step.uri)}
        >
          {content}
        </button>
      ) : leaves ? (
        <a
          className="grip-path__body"
          href={step.uri}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Ander corpus: ${title}. Opent in een nieuw tabblad`}
        >
          {content}
        </a>
      ) : (
        <div className="grip-path__body" aria-current={current ? 'step' : undefined}>
          {content}
        </div>
      )}
    </li>
  );
}

function RelationRow({ type }: { type: string }) {
  return (
    <li className="grip-path__relation">
      <span className="grip-path__rail" aria-hidden="true" />
      <nldd-text class="grip-path__label" size="sm" color="secondary">
        {edgeTypeLabel(type)}
      </nldd-text>
    </li>
  );
}

interface RailProps {
  label: string;
  steps: readonly PathStep[];
  currentUri: string;
  onStep: (uri: string) => void;
  /** The relation that leads into the first step, for a branch. */
  lead?: string | null;
  /** The rail runs on below the last step: more follows. */
  open?: boolean;
  /** Who manages the step this rail continues from. */
  from?: string | null;
}

function Rail({ label, steps, currentUri, onStep, lead, open, from }: RailProps) {
  const rows: ReactNode[] = [];
  if (lead) rows.push(<RelationRow key="lead" type={lead} />);
  steps.forEach((step, index) => {
    const isLast = index === steps.length - 1;
    rows.push(
      <StepRow
        key={step.uri}
        step={step}
        first={index === 0 && !lead}
        last={isLast && !open}
        end={isLast && !open}
        current={step.uri === currentUri}
        previousOrganisation={
          index === 0 ? (from ?? null) : (steps[index - 1]?.organisation_name ?? null)
        }
        onStep={onStep}
      />,
    );
    if (!isLast && step.edge_type) {
      rows.push(<RelationRow key={`${step.uri}-relation`} type={step.edge_type} />);
    }
  });
  return (
    <ol className="grip-path" aria-label={label}>
      {rows}
    </ol>
  );
}

function branchHeading(branch: PathBranch): string {
  const end = branch.steps[branch.steps.length - 1];
  return end && isOtherCorpus(end) ? 'Loopt door in een ander corpus' : 'Komt voort uit';
}

function endTitle(steps: readonly PathStep[]): string {
  const end = steps[steps.length - 1];
  if (!end) return 'het eindpunt';
  return isOtherCorpus(end) ? corpusLabel(end) : (end.title ?? 'het eindpunt');
}

/**
 * Where a node comes from, drawn as a path: the node on top, each step
 * below it on one rail with the relation between them, down to the
 * political input. When there is more than one end point, the steps all
 * paths share are drawn once and the ways part below them, side by side
 * where they fit.
 */
export function NodePathView({ paths, currentUri, onStep }: NodePathViewProps) {
  const tree = toTree(paths);
  if (tree.trunk.length === 0) return null;
  if (tree.branches.length === 0) {
    return (
      <Rail
        label={`Pad naar ${endTitle(tree.trunk)}`}
        steps={tree.trunk}
        currentUri={currentUri}
        onStep={onStep}
      />
    );
  }
  const from = tree.trunk[tree.trunk.length - 1]?.organisation_name ?? null;
  return (
    <Stack gap="related">
      <Rail
        label="Wat alle paden delen"
        steps={tree.trunk}
        currentUri={currentUri}
        onStep={onStep}
        open
      />
      <div className="grip-path-branches">
        {tree.branches.map((branch) => (
          <Stack key={branch.steps[branch.steps.length - 1]?.uri ?? 'pad'} gap="tight">
            <Quiet>{branchHeading(branch)}</Quiet>
            <Rail
              label={`Pad naar ${endTitle(branch.steps)}`}
              steps={branch.steps}
              currentUri={currentUri}
              onStep={onStep}
              lead={branch.lead}
              from={from}
            />
          </Stack>
        ))}
      </div>
    </Stack>
  );
}
