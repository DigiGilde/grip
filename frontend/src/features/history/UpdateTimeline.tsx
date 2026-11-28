import { useMemo, type ReactNode } from 'react';
import { RouterLinks } from '@/layout/RouterLinks';
import { Quiet, SectionHeading, Stack, TOP_ALIGNED } from '@/ui/layout';
import { placeOf } from '@/ui/track';
import { byDay, type UpdateItem } from './updates';

// Tests leave the nldd-* elements unregistered on purpose.
if (import.meta.env.MODE !== 'test') void import('./register');

// Half the first line of a sentence (nldd-text md: font size 100, snug), so
// the dot stands beside that line, also when the sentence wraps.
const FIRST_LINE_MIDDLE =
  'calc(var(--primitives-font-size-100) * var(--primitives-line-height-snug) / 2)';

/** One sentence; the thing it is about is a link to where it is to be seen. */
function Sentence({ item }: { item: UpdateItem }) {
  return (
    <nldd-text size="md" {...(item.new ? { weight: 'bold' } : {})}>
      <p>
        {item.parts.map((part, index) =>
          part.href ? (
            <nldd-link key={index} href={part.href} text={part.text} />
          ) : (
            <span key={index}>{part.text}</span>
          ),
        )}
      </p>
    </nldd-text>
  );
}

interface UpdateTimelineProps {
  items: readonly UpdateItem[];
  /** The level of the day headings: 2 on a page of its own, 3 inside a section. */
  level: 2 | 3;
  /** What comes after the last day: the way further back, or to all of it. */
  after?: ReactNode;
}

/**
 * What happened, as a timeline: a heading per day, and under it the items of
 * that day on one track, newest first. One sentence per item, the time at
 * the right.
 */
export function UpdateTimeline({ items, level, after }: UpdateTimelineProps) {
  const days = useMemo(() => byDay(items), [items]);
  return (
    <RouterLinks>
      <Stack gap="group">
        {days.map((day) => (
          <Stack key={day.items[0]!.id} gap="close">
            <SectionHeading text={day.day} level={level} />
            <nldd-list accessible-label={`Wat er gebeurde: ${day.day}`}>
              {day.items.map((item, index) => (
                <nldd-list-item key={item.id}>
                  <nldd-step-cell
                    status="past"
                    level="minor"
                    direction="up"
                    vertical-alignment="top"
                    marker-offset={FIRST_LINE_MIDDLE}
                    position={placeOf(index, day.items.length)}
                  />
                  <nldd-spacer-cell size="12" />
                  <nldd-cell width="full" divider-start {...TOP_ALIGNED}>
                    <Sentence item={item} />
                  </nldd-cell>
                  <nldd-cell horizontal-alignment="right" {...TOP_ALIGNED}>
                    <Quiet>{item.new ? `nieuw · ${item.when_text}` : item.when_text}</Quiet>
                  </nldd-cell>
                </nldd-list-item>
              ))}
            </nldd-list>
          </Stack>
        ))}
        {after}
      </Stack>
    </RouterLinks>
  );
}
