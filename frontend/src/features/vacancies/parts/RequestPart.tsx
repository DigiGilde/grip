import { useRef } from 'react';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { RouterLinks } from '@/layout/RouterLinks';
import { IconCell } from '@/ui/Icon';
import { useNarrow } from '@/ui/layout';
import { budgetLineWarning } from '../labels';
import { vacancyPartPath } from '../paths';
import { RequestFormSection } from '../RequestFormSection';
import { useVacancyShell } from '../shell';
import { requestItems, type RequestItem } from '../steps';
import { VacancyPartPage } from '../VacancyPartPage';

const NOT_FILLED = 'Nog niet ingevuld';

/** The mark, the label and the value of one thing the form asks for. */
function RowCells({ item, state, filled }: { item: RequestItem; state: string; filled: boolean }) {
  const narrow = useNarrow();
  const color = filled ? 'content' : 'secondary';
  return (
    <>
      <IconCell concept={filled ? 'done' : 'todo'} color={filled ? 'success' : 'secondary'} />
      <nldd-spacer-cell size="8" />
      {narrow ? (
        <nldd-text-cell overline={item.label} text={state} color={color} />
      ) : (
        <>
          <nldd-text-cell width="220px" color="secondary" text={item.label} />
          <nldd-text-cell text={state} color={color} />
        </>
      )}
    </>
  );
}

/** One thing the request form asks for: ticked when filled, and the way to fill it. */
function RequestRow({ item, onOpen }: { item: RequestItem; onOpen?: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onOpen ? () => onOpen() : undefined);
  const done = item.value !== null;
  const state = done ? (item.value ?? '') : NOT_FILLED;
  return (
    <nldd-list-item
      ref={ref}
      size="sm"
      button={orUndef(Boolean(onOpen))}
      {...(onOpen
        ? { 'accessible-label': `${item.label}: ${state}. ${done ? 'Wijzig' : 'Vul in'}` }
        : {})}
    >
      <RowCells item={item} state={state} filled={done} />
      {onOpen && <IconCell concept="open" />}
    </nldd-list-item>
  );
}

/** What the request form asks for, filled or visibly not, and the form itself. */
export function RequestPart() {
  const { vacancy, parts, openSheet } = useVacancyShell();
  const editable = vacancy.permissions.can_edit && ['draft', 'requested'].includes(vacancy.status);
  const hasText = parts.some((part) => part.key === 'text');
  const items = requestItems(vacancy).filter(
    // Who it is addressed to is a name; a reader without names has no such row.
    (item) => item.key !== 'addressee' || 'addressee_name' in vacancy,
  );
  const warning =
    vacancy.scale_fits_budget_line === false
      ? budgetLineWarning(vacancy.scale, vacancy.budget_line_scales)
      : null;
  return (
    <VacancyPartPage part="request" kind="document">
      <RouterLinks>
        <nldd-list accessible-label="Gegevens voor het aanvraagformulier">
          {items.map((item) =>
            item.where === 'texts' && hasText ? (
              <nldd-list-item key={item.key} size="sm" href={vacancyPartPath(vacancy.id, 'text')}>
                <RowCells
                  item={item}
                  state={item.value ?? item.missingText ?? NOT_FILLED}
                  filled={Boolean(item.value)}
                />
                <IconCell concept="open" />
              </nldd-list-item>
            ) : (
              <RequestRow
                key={item.key}
                item={item}
                onOpen={editable && item.where === 'sheet' ? () => openSheet('prepare') : undefined}
              />
            ),
          )}
        </nldd-list>
      </RouterLinks>
      {warning && <nldd-banner variant="warning" size="sm" text={warning} />}
      {vacancy.permissions.can_download_form && <RequestFormSection vacancyId={vacancy.id} />}
    </VacancyPartPage>
  );
}
