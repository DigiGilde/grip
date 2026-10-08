import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { useInstance } from '@/layout/useInstance';
import { ErrorNotice, Facts, FormFields, Page, Quiet, Section, Stack } from '@/ui/layout';
import {
  momentsLine,
  receiptFacts,
  verifyBundle,
  type DecisionStatement,
  type VerifyReport,
} from './proof';
import { FileInput } from './ui';

function Findings({ title, lines }: { title: string; lines: readonly string[] }) {
  if (lines.length === 0) return null;
  return (
    <Section title={title} level={2}>
      <nldd-list accessible-label={title}>
        {lines.map((line) => (
          <nldd-list-item key={line}>
            <nldd-text-cell text={line} />
          </nldd-list-item>
        ))}
      </nldd-list>
    </Section>
  );
}

function Report({ report }: { report: VerifyReport }) {
  const statement = report.statement ?? null;
  const moments = momentsLine(statement);
  return (
    <>
      <nldd-banner
        variant={report.sound ? 'success' : 'critical'}
        text={
          report.sound
            ? 'Dit bewijs klopt in zichzelf'
            : 'Dit bewijs klopt niet: er is iets aan veranderd of het is onvolledig'
        }
        data-verify-result={report.sound ? 'sound' : 'wrong'}
      />
      {statement ? (
        <Section title="Waar het bewijs over gaat" level={2}>
          <Facts
            label="Het besluit in dit bewijs"
            facts={receiptFacts({ decision: decisionOf(statement), statement })}
            labelWidth="140px"
          />
          {moments ? <Quiet>{moments}</Quiet> : null}
        </Section>
      ) : null}
      <Findings title="Wat niet klopt" lines={report.wrong} />
      <Findings title="Wat is aangetoond" lines={report.proven} />
      <Findings title="Wat dit bewijs niet aantoont" lines={report.not_proven} />
    </>
  );
}

const DECISIONS: Record<string, string> = {
  akkoord: 'accept',
  afwijzing: 'reject',
  goedkeuring: 'approve',
  teruggestuurd: 'send_back',
};

function decisionOf(statement: DecisionStatement): string {
  return DECISIONS[statement.besluit ?? ''] ?? statement.besluit ?? '';
}

/**
 * Checking a bundle of evidence: someone picks the file they were given and
 * reads what it shows and what it leaves open. Nothing is looked up or kept;
 * a bundle of another organisation is checked the same way.
 */
export function VerifyProofPage() {
  const instance = useInstance();
  const [problem, setProblem] = useState<string | null>(null);
  const check = useMutation({ mutationFn: verifyBundle });

  const onFile = (file: File | null) => {
    setProblem(null);
    check.reset();
    if (!file) return;
    void file.text().then((text) => {
      try {
        check.mutate(JSON.parse(text));
      } catch {
        setProblem('Dit bestand is geen bewijs van grip. Kies het bestand dat je hebt gedownload.');
      }
    });
  };

  return (
    <Page title="Controleer een bewijs" instanceName={instance?.name} width="960px">
      <Stack gap="related">
        <nldd-text>
          Kies het bewijs dat je bij een besluit hebt gedownload. Je ziet wat het aantoont en wat
          niet. Er wordt niets bewaard.
        </nldd-text>
        <FormFields>
          <FileInput
            label="Bewijs"
            hint="Het bestand dat begint met bewijs- en eindigt op .json"
            accept=".json,application/json"
            onChange={onFile}
          />
        </FormFields>
      </Stack>
      {problem ? <ErrorNotice message={problem} /> : null}
      {check.isError ? <ErrorNotice message={errorMessage(check.error)} /> : null}
      {check.data ? <Report report={check.data} /> : null}
    </Page>
  );
}
