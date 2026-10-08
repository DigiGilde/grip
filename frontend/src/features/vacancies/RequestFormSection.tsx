import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { PATHS } from '@/paths';
import {
  VACANCY_KEYS,
  fetchRequestFormStatus,
  requestFormUrl,
  type Vacancy,
  type VacancyOptions,
} from './api';
import { ErrorNotice, LinkButton, Loading, Note, SectionHeading } from './ui';

/** The request form of the instance, filled in for this vacancy. */
export function RequestFormSection({
  vacancy,
  options,
}: {
  vacancy: Vacancy;
  options: VacancyOptions | undefined;
}) {
  const status = useQuery({
    queryKey: VACANCY_KEYS.formStatus(vacancy.id),
    queryFn: () => fetchRequestFormStatus(vacancy.id),
  });

  return (
    <>
      <SectionHeading text="Aanvraagformulier" />
      {status.isPending && <Loading />}
      {status.isError && <ErrorNotice message={errorMessage(status.error)} />}
      {status.data && !status.data.available && (
        <>
          <Note>
            Er is geen leeg aanvraagformulier ingesteld voor deze instantie. De beheerder levert
            het formulier en de veldkoppeling aan.
          </Note>
          {options?.can_manage_setup && (
            <>
              <nldd-spacer size="8" />
              <LinkButton text="Formulier instellen" href={PATHS.vacancySetup} />
            </>
          )}
        </>
      )}
      {status.data?.available && (
        <>
          <Note>
            Het formulier wordt ingevuld met wat in grip bekend is en blijft invulbaar, zodat een
            adviseur het buiten grip kan aanvullen. Het bevat namen van collega's en wordt niet
            bewaard.
          </Note>
          {!status.data.motivation_established && (
            <Note>
              De aanleiding en motivatie komt pas op het formulier als die is vastgesteld.
            </Note>
          )}
          <nldd-spacer size="8" />
          {status.data.open_fields.length > 0 ? (
            <>
              <SectionHeading text="Blijft open op het formulier" level={3} />
              <nldd-list accessible-label="Velden die open blijven op het formulier">
                {status.data.open_fields.map((field) => (
                  <nldd-list-item key={field.source} size="sm">
                    <nldd-text-cell text={field.label} />
                  </nldd-list-item>
                ))}
              </nldd-list>
            </>
          ) : (
            <Note>Alle velden van het formulier zijn ingevuld.</Note>
          )}
          <nldd-spacer size="8" />
          <LinkButton
            text="Download ingevuld formulier (pdf)"
            href={requestFormUrl(vacancy.id)}
            appearance="primary"
            download
          />
        </>
      )}
    </>
  );
}
