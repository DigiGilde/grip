import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PHASE_VIEW_LABELS } from '@/features/assignments/labels';
import { assignmentPath } from '@/features/assignments/paths';
import { vacancyPath } from '@/features/vacancies/paths';
import { useInstance } from '@/layout/useInstance';
import { PAGE_HEADING_ID } from '@/pages/PageHeading';
import { PATHS } from '@/paths';
import { LinkRows, type LinkRow } from '@/ui/LinkRows';
import { EmptyNotice, LoadError, Loading, Page, Section } from '@/ui/layout';
import { cleanQuery, MAX_QUERY, MIN_QUERY, searchable, useSearch, type SearchResults } from './api';
import { SearchField } from './SearchField';

const personPath = (id: string) => PATHS.person.replace(':personId', id);

/** Whether the field in the top bar is on screen; in the menu it is not. */
function useBarFieldShown(): boolean {
  const [shown, setShown] = useState(true);
  useEffect(() => {
    const measure = () => {
      const field = document.querySelector('nldd-toolbar nldd-search-field');
      setShown(!!field && field.getBoundingClientRect().width > 0);
    };
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, []);
  return shown;
}

function groups(results: SearchResults): { title: string; label: string; rows: LinkRow[] }[] {
  return [
    {
      title: 'Opdrachten',
      label: 'Gevonden opdrachten',
      rows: results.assignments.map((row) => ({
        key: row.id,
        text: row.name,
        href: assignmentPath(row.id),
        ...(row.client_name ? { notice: row.client_name } : {}),
        end: PHASE_VIEW_LABELS[row.phase],
      })),
    },
    {
      title: 'Vacatures',
      label: 'Gevonden vacatures',
      rows: results.vacancies.map((row) => ({
        key: row.id,
        text: row.title,
        href: vacancyPath(row.id),
      })),
    },
    {
      title: 'Mensen',
      label: 'Gevonden mensen',
      rows: results.people.map((row) => ({
        key: row.id,
        text: row.name,
        href: personPath(row.id),
      })),
    },
  ].filter((group) => group.rows.length > 0);
}

/** What was searched for, as rows per kind. */
export function SearchPage() {
  const instance = useInstance();
  const [params] = useSearchParams();
  const q = cleanQuery(params.get('q'));
  const search = useSearch(q);
  const barFieldShown = useBarFieldShown();

  const settled = !search.isLoading;
  useEffect(() => {
    if (settled) document.getElementById(PAGE_HEADING_ID)?.focus();
  }, [q, settled]);

  let content = null;
  if (q === '') {
    content = <EmptyNotice text="Typ een woord of een naam om te zoeken." />;
  } else if (q.length < MIN_QUERY) {
    content = <EmptyNotice text={`Typ minstens ${MIN_QUERY} tekens.`} />;
  } else if (q.length > MAX_QUERY) {
    content = <EmptyNotice text={`Gebruik hooguit ${MAX_QUERY} tekens.`} />;
  } else if (searchable(q)) {
    if (search.isLoading) {
      content = <Loading />;
    } else if (search.isError) {
      content = <LoadError error={search.error} retry={() => void search.refetch()} />;
    } else if (search.data) {
      const found = groups(search.data);
      content =
        found.length === 0 ? (
          <EmptyNotice text={`Niets gevonden voor “${q}”`} />
        ) : (
          found.map((group) => (
            <Section key={group.title} title={group.title}>
              <LinkRows label={group.label} rows={group.rows} />
            </Section>
          ))
        );
    }
  }

  return (
    <Page kind="list" title="Zoeken" instanceName={instance?.name}>
      {!barFieldShown && <SearchField />}
      {content}
    </Page>
  );
}
