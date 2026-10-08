import type { ReactNode } from 'react';
import { errorMessage } from '@/api/client';
import './nldd';

interface QueryLike {
  isPending: boolean;
  isError: boolean;
  error: unknown;
}

interface QueryStateProps {
  query: QueryLike;
  children: ReactNode;
}

/** Loading and error states of a query; the children once there is data. */
export function QueryState({ query, children }: QueryStateProps) {
  if (query.isPending) {
    return <nldd-inline-dialog variant="loading" text="Gegevens worden geladen" />;
  }
  if (query.isError) {
    return (
      <nldd-inline-dialog
        variant="alert"
        text="De gegevens konden niet worden geladen"
        supporting-text={errorMessage(query.error)}
      />
    );
  }
  return <>{children}</>;
}

/** What an empty table says, in the table's own slot. */
export function EmptyRows({ text, supportingText }: { text: string; supportingText?: string }) {
  return (
    <nldd-inline-dialog
      slot="empty"
      text={text}
      {...(supportingText ? { 'supporting-text': supportingText } : {})}
    />
  );
}
