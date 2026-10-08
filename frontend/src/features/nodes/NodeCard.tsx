import { useRef, type ReactNode } from 'react';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import type { NodeLookup } from './api';
import { nodeTypeLabel, uriHost } from './labels';
import { notableStatus, originLine, stepsText } from './summary';
import './register';

export interface NodeCardProps {
  /** The node as looked up: resolved with where it comes from, or a bare URI with the reason. */
  item: NodeLookup;
  /** Makes the whole card the way to the detail of this node. */
  onOpen?: (uri: string) => void;
  /** Still being looked up: the same card shape, so nothing jumps when the answer arrives. */
  pending?: boolean;
  /** Leave out the reason on an unresolved card, when one notice above says it for all. */
  hideReason?: boolean;
  /** A control on the card that is not the click-through, such as "Verwijder". */
  action?: ReactNode;
}

// Above the overlay that makes the card one button, so the control stays clickable.
const LIFTED = { position: 'relative', zIndex: 1 } as const;
// One height for every state of a card: pending, resolved and unresolved.
const BODY = { minHeight: '6.5rem' } as const;

/**
 * A context node as a compact card: what kind of thing it is, what it is
 * called, who manages it, and in one line where it comes from. Everything
 * else is in the detail the card opens. Used wherever nodes are listed: the
 * context of an assignment, a client's request, and the picker's choices.
 */
export function NodeCard({ item, onOpen, pending, hideReason, action }: NodeCardProps) {
  const ref = useRef<HTMLElement>(null);
  const node = item.node;
  const clickable = Boolean(onOpen) && !pending;
  useNlddEvent(ref, 'click', clickable ? () => onOpen?.(item.uri) : undefined);

  const organisation = node?.managing_organisation?.name ?? '';
  const status = notableStatus(node?.status);
  const origin = node ? originLine(item) : '';
  const steps = node ? stepsText(item) : '';
  const name = node?.title ?? item.uri;

  return (
    <nldd-card
      ref={ref}
      button={orUndef(clickable)}
      accessible-label={
        pending ? 'Bezig met ophalen van een node' : clickable ? `Bekijk ${name}` : name
      }
      data-node-uri={item.uri}
      aria-busy={pending ? 'true' : undefined}
    >
      <nldd-container padding="16" gap="8" style={BODY}>
        {pending ? (
          <nldd-text size="sm">Bezig met ophalen</nldd-text>
        ) : node ? (
          <>
            <nldd-container layout="wrap" gap="8">
              <nldd-badge color="accent" text={nodeTypeLabel(node.type)} />
              {status ? <nldd-badge color="warning" text={status} /> : null}
            </nldd-container>
            <nldd-title size={5} text={node.title} heading-level={3} />
            {organisation ? <nldd-text size="sm">{organisation}</nldd-text> : null}
            {origin ? (
              <nldd-text size="sm">
                {origin}
                {steps ? ` (${steps})` : ''}
              </nldd-text>
            ) : null}
          </>
        ) : (
          <>
            <div>
              <nldd-badge color="neutral" text="Niet op te halen" />
            </div>
            <nldd-title size={5} text={uriHost(item.uri) || 'Verwijzing'} heading-level={3} />
            <nldd-text size="sm" style={{ overflowWrap: 'anywhere' }}>
              {item.uri}
            </nldd-text>
            {!hideReason && item.problem ? <nldd-text size="sm">{item.problem}</nldd-text> : null}
          </>
        )}
      </nldd-container>
      {action ? (
        <div slot="footer" style={LIFTED}>
          <nldd-container padding-inline="16" padding-bottom="16">
            {action}
          </nldd-container>
        </div>
      ) : null}
    </nldd-card>
  );
}

/** Node cards in a responsive grid; the cards of a row are equally high. */
export function NodeCardGrid({ label, children }: { label: string; children: ReactNode }) {
  return (
    <nldd-collection layout="grid" item-width="280px" gap="16" role="group" aria-label={label}>
      {children}
    </nldd-collection>
  );
}
