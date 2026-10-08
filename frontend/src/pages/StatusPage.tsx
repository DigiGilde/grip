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
  /** `alert` is kept for callers; a problem reads from the words, not from a sign. */
  variant?: 'alert' | 'loading';
  action?: StatusAction;
  secondaryAction?: StatusAction;
  children?: ReactNode;
}

function ActionButton({ action }: { action: StatusAction }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', action.onClick);
  return <nldd-button ref={ref} appearance={action.appearance ?? 'primary'} text={action.text} />;
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

  // One block in the middle of the page: where you are, what is the matter,
  // what you can do. A heading at the top with the message far below it
  // reads as two unrelated things.
  return (
    <nldd-app-view background="tinted">
      <nldd-page landmarks="page">
        <nldd-simple-section width="480px" vertical-alignment="center">
          <nldd-container gap="24">
            <Brand variant="compact" />
            <nldd-container gap="8">
              <PageHeading text={title} inline />
              {message && <nldd-text color="secondary">{message}</nldd-text>}
            </nldd-container>
            {children}
            {(action || secondaryAction) && (
              <nldd-container layout="row" gap="8">
                {action && <ActionButton action={action} />}
                {secondaryAction && <ActionButton action={secondaryAction} />}
              </nldd-container>
            )}
          </nldd-container>
        </nldd-simple-section>
      </nldd-page>
    </nldd-app-view>
  );
}
