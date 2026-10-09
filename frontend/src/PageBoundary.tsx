/**
 * The place where pages render: quiet while the file of a page is on its
 * way, and one shape when it cannot be fetched (see `pageChunks`).
 */
import { Component, Suspense, type ReactNode } from 'react';
import { Loading, StateNotice } from '@/ui/layout';

/** What the content pane shows while the file of a page is on its way. */
export function PageLoading() {
  return (
    <nldd-simple-section>
      <Loading />
    </nldd-simple-section>
  );
}

interface BoundaryProps {
  /** Changes with the address, so going elsewhere leaves the failure behind. */
  resetKey: string;
  children: ReactNode;
}

/** Shows that a page could not be loaded, in the shape of every other failure. */
class ChunkBoundary extends Component<BoundaryProps, { failedAt: string | null }> {
  override state: { failedAt: string | null } = { failedAt: null };

  static getDerivedStateFromError(): { failedAt: string | null } {
    return { failedAt: window.location.pathname };
  }

  static getDerivedStateFromProps(
    props: BoundaryProps,
    state: { failedAt: string | null },
  ): { failedAt: string | null } | null {
    return state.failedAt !== null && state.failedAt !== props.resetKey ? { failedAt: null } : null;
  }

  override render() {
    if (this.state.failedAt === null) return this.props.children;
    return (
      <nldd-simple-section>
        <StateNotice
          state="unreachable"
          text="Deze pagina laden is niet gelukt"
          detail="Controleer je verbinding en laad de pagina opnieuw."
          action={{ text: 'Laad opnieuw', onClick: () => window.location.reload() }}
        />
      </nldd-simple-section>
    );
  }
}

/**
 * Around the place where pages render: the quiet loading state while a file
 * is fetched, and one shape when it cannot be.
 */
export function PageBoundary({
  resetKey,
  fallback = <PageLoading />,
  children,
}: BoundaryProps & { fallback?: ReactNode }) {
  return (
    <ChunkBoundary resetKey={resetKey}>
      <Suspense fallback={fallback}>{children}</Suspense>
    </ChunkBoundary>
  );
}
