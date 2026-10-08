import { useRef, type ReactNode } from 'react';
import { useNlddEvent } from '@/components/nldd/events';
import { PageHeading } from './PageHeading';

interface StatusAction {
  text: string;
  onClick: () => void;
  appearance?: 'primary' | 'secondary';
}

interface StatusPageProps {
  title: string;
  message?: string;
  variant?: 'alert' | 'loading';
  action?: StatusAction;
  secondaryAction?: StatusAction;
  children?: ReactNode;
}

function ActionButton({ action }: { action: StatusAction }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', action.onClick);
  return (
    <nldd-button
      ref={ref}
      slot="actions"
      appearance={action.appearance ?? 'primary'}
      text={action.text}
    />
  );
}

/**
 * A full-page message outside the application shell: login, no access,
 * loading, backend unreachable, page not found.
 */
export function StatusPage({
  title,
  message,
  variant,
  action,
  secondaryAction,
  children,
}: StatusPageProps) {
  return (
    <nldd-app-view background="tinted">
      <nldd-page landmarks="page">
        <nldd-simple-section width="480px" vertical-alignment="center">
          <PageHeading text={title} />
          {children}
          <nldd-inline-dialog
            {...(variant ? { variant } : {})}
            horizontal-alignment="left"
            {...(message ? { text: message } : {})}
          >
            {action && <ActionButton action={action} />}
            {secondaryAction && <ActionButton action={secondaryAction} />}
          </nldd-inline-dialog>
        </nldd-simple-section>
      </nldd-page>
    </nldd-app-view>
  );
}
