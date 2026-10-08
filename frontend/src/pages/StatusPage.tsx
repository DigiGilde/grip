import { useRef, type ReactNode } from 'react';
import { Brand } from '@/brand/Brand';
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
  if (variant === 'loading') {
    // Spinner and heading form one centered block. The inline dialog would
    // put the heading at the top of the page and the spinner in the middle.
    return (
      <nldd-app-view background="tinted">
        <nldd-page landmarks="page">
          <nldd-simple-section
            width="480px"
            vertical-alignment="center"
            horizontal-alignment="center"
          >
            <div className="status-loading">
              <Brand variant="compact" />
              <nldd-activity-indicator size="40" timing="instant" />
              <PageHeading text={title} inline />
              {children}
            </div>
          </nldd-simple-section>
        </nldd-page>
      </nldd-app-view>
    );
  }

  return (
    <nldd-app-view background="tinted">
      <nldd-page landmarks="page">
        <nldd-simple-section width="480px" vertical-alignment="center">
          <nldd-container slot="header" gap="16">
            <Brand variant="compact" />
            <PageHeading text={title} inline />
          </nldd-container>
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
