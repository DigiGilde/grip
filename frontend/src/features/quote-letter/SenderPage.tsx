import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, errorMessage } from '@/api/client';
import { Button, TextInput } from '@/features/assignments/ui';
import { CheckboxInput } from '@/features/quotes/ui';
import { useInstance } from '@/layout/useInstance';
import { PATHS } from '@/paths';
import { OpenCell, OpenRow, ROW_ACTIONS_COLUMN, RowActions, type RowAction } from '@/ui/RowActions';
import {
  EmptyNotice,
  ErrorNotice,
  Facts,
  FormFields,
  FormSheet,
  Loading,
  Page,
  Quiet,
  Section,
  Stack,
  type Fact,
} from '@/ui/layout';
import {
  applyProfile,
  fetchQuoteSender,
  saveQuoteSender,
  senderKeys,
  type LetterTexts,
  type QuoteSender,
  type Sender,
  type TextBlock,
} from './api';
import {
  blockKind,
  contactLine,
  fromLines,
  keyFromHeading,
  moved,
  signatoryLine,
  toLines,
} from './text';

type Open =
  | { kind: 'organisation' }
  | { kind: 'people' }
  | { kind: 'letter' }
  | { kind: 'block'; index: number | null }
  | null;

const NEW_BLOCK: TextBlock = {
  key: '',
  heading: '',
  body: '',
  hint: '',
  included: true,
  with_costs: false,
  numbered: true,
  draftable: true,
  required: false,
};

const MARKS_HINT =
  'Een lege regel begint een alinea. Een regel met "- " is een opsomming, met "1. " een genummerde lijst. **vet** en *cursief*.';

/** Who sends the quotes of this instance, and with which standard texts. For the beheerder. */
/** Only what is filled in: an empty line says nothing about the sender. */
function filled(facts: Fact[]): Fact[] {
  return facts.filter((fact) => Boolean(fact.value));
}

function people(sender: Sender): Fact[] {
  return filled([
    { label: 'Contactpersoon', value: contactLine(sender) },
    { label: 'Tekent namens', value: sender.signatory.on_behalf_of },
    { label: 'Ondertekenaar', value: signatoryLine(sender) },
  ]);
}

export function SenderPage() {
  const instance = useInstance();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: senderKeys.all, queryFn: fetchQuoteSender, retry: false });
  const data = query.data;

  const [open, setOpen] = useState<Open>(null);
  const [error, setError] = useState<string | null>(null);
  const [sender, setSender] = useState<Sender | null>(null);
  const [letter, setLetter] = useState<LetterTexts | null>(null);
  const [block, setBlock] = useState<TextBlock>(NEW_BLOCK);

  const done = (saved: QuoteSender) => {
    queryClient.setQueryData(senderKeys.all, saved);
    setOpen(null);
  };
  const save = useMutation({
    mutationFn: saveQuoteSender,
    onSuccess: done,
    onError: (failure) => setError(errorMessage(failure)),
  });
  const profile = useMutation({
    mutationFn: applyProfile,
    onSuccess: done,
    onError: (failure) => setError(errorMessage(failure)),
  });

  const start = (next: Open) => {
    if (!data) return;
    setError(null);
    setSender(structuredClone(data.sender));
    setLetter({ ...data.letter });
    if (next?.kind === 'block') {
      setBlock(next.index === null ? NEW_BLOCK : (data.text_blocks[next.index] ?? NEW_BLOCK));
    }
    setOpen(next);
  };

  const saveBlocks = (blocks: TextBlock[]) => save.mutate({ text_blocks: blocks });
  const submitBlock = () => {
    if (!data || open?.kind !== 'block') return;
    if (!block.heading.trim()) {
      setError('Geef het onderdeel een kop.');
      return;
    }
    const blocks = [...data.text_blocks];
    if (open.index === null) {
      const key = keyFromHeading(
        block.heading,
        blocks.map((item) => item.key),
      );
      blocks.push({ ...block, key });
    } else {
      blocks[open.index] = block;
    }
    setError(null);
    saveBlocks(blocks);
  };

  const rowActions = (index: number, blocks: TextBlock[]): RowAction[] => [
    ...(index > 0
      ? [{ text: 'Zet hoger', onSelect: () => saveBlocks(moved(blocks, index, -1)) }]
      : []),
    ...(index < blocks.length - 1
      ? [{ text: 'Zet lager', onSelect: () => saveBlocks(moved(blocks, index, 1)) }]
      : []),
    {
      text: 'Verwijder',
      destructive: true,
      confirm: {
        text: `Verwijder het onderdeel ${blocks[index]?.heading ?? ''}?`,
        supportingText:
          'Nieuwe offertes beginnen zonder dit onderdeel. Offertes die al zijn gemaakt veranderen niet.',
        confirmText: 'Verwijder',
      },
      onSelect: () => saveBlocks(blocks.filter((_, at) => at !== index)),
    },
  ];

  const forbidden = query.error instanceof ApiError && query.error.status === 403;
  const set = (change: Partial<Sender>) => setSender((now) => (now ? { ...now, ...change } : now));

  return (
    <>
      <Page
        title="Afzender en teksten van offertes"
        instanceName={instance?.name}
        spacing="sections"
        back={{ href: PATHS.admin, text: 'Terug naar Beheer' }}
      >
        {query.isPending ? <Loading /> : null}
        {query.isError && forbidden ? <EmptyNotice text="Beheer is voor beheerders" /> : null}
        {query.isError && !forbidden ? <ErrorNotice message={errorMessage(query.error)} /> : null}

        {data && !data.sender.organisation ? (
          // Nothing filled in yet: the page has one job, and says so first.
          <Stack gap="related">
            <nldd-text>Op een offerte staat nog geen afzender.</nldd-text>
            <nldd-container layout="row" gap="8">
              {data.profiles.map((name, index) => (
                <Button
                  key={name}
                  text={`Neem de gegevens van ${name} over`}
                  appearance={index === 0 ? 'primary' : 'secondary'}
                  onClick={() => profile.mutate(name)}
                />
              ))}
              <Button
                text="Vul zelf in"
                appearance={data.profiles.length === 0 ? 'primary' : 'secondary'}
                onClick={() => start({ kind: 'organisation' })}
              />
            </nldd-container>
          </Stack>
        ) : null}

        {data?.sender.organisation ? (
          <Section title="Organisatie" level={2}>
            <Facts
              label="De organisatie zoals ze op een offerte staat"
              facts={filled([
                { label: 'Naam', value: data.sender.organisation },
                { label: 'Onderdeel van', value: data.sender.part_of.join(', ') },
                { label: 'Eenheid', value: data.sender.unit },
                { label: 'Bezoekadres', value: data.sender.visiting_address.join(', ') },
                { label: 'Postadres', value: data.sender.postal_address.join(', ') },
                { label: 'Adres voor opdrachten', value: data.sender.orders_email },
              ])}
            />
            <nldd-container layout="row">
              <Button text="Wijzig organisatie" onClick={() => start({ kind: 'organisation' })} />
            </nldd-container>
          </Section>
        ) : null}

        {data?.sender.organisation ? (
          <Section title="Contactpersoon en ondertekenaar" level={2}>
            {people(data.sender).length > 0 ? (
              <Facts label="Wie op een offerte staat" facts={people(data.sender)} />
            ) : (
              <Quiet>
                Nog niemand ingevuld. Zonder ondertekenaar blijft die regel op de offerte leeg.
              </Quiet>
            )}
            <nldd-container layout="row">
              <Button text="Wijzig personen" onClick={() => start({ kind: 'people' })} />
            </nldd-container>
          </Section>
        ) : null}

        {data ? (
          <Section title="Onderdelen van een offerte" level={2}>
            <nldd-table
              accessible-label="Onderdelen van een offerte, in volgorde"
              columns={`minmax(200px,2fr) minmax(220px,2fr) 150px ${ROW_ACTIONS_COLUMN}`}
              sm-columns={`minmax(0,1fr) ${ROW_ACTIONS_COLUMN}`}
            >
              <nldd-table-row slot="header">
                <nldd-text-cell text="Onderdeel" />
                <nldd-text-cell text="Tekst" hide-below="md" />
                <nldd-text-cell text="In een nieuwe offerte" hide-below="md" />
                <nldd-cell />
              </nldd-table-row>
              {data.text_blocks.map((item, index) => {
                const edit = () => start({ kind: 'block', index });
                return (
                  <OpenRow key={item.key} onOpen={edit}>
                    <OpenCell
                      text={item.heading}
                      accessibleLabel={`Wijzig ${item.heading}`}
                      onOpen={edit}
                    />
                    <nldd-text-cell hide-below="md" text={blockKind(item)} />
                    <nldd-text-cell
                      hide-below="md"
                      text={item.required ? 'Altijd' : item.included ? 'Staat erin' : 'Op verzoek'}
                    />
                    <nldd-cell>
                      <RowActions
                        name={item.heading}
                        actions={rowActions(index, data.text_blocks)}
                      />
                    </nldd-cell>
                  </OpenRow>
                );
              })}
              <nldd-inline-dialog slot="empty" text="Nog geen onderdelen" />
            </nldd-table>
            <nldd-button-group>
              <Button
                text="Nieuw onderdeel"
                onClick={() => start({ kind: 'block', index: null })}
              />
            </nldd-button-group>
          </Section>
        ) : null}

        {data ? (
          <Section title="Opening en afsluiting" level={2}>
            <Facts
              label="De tekst om de onderdelen heen"
              facts={[
                { label: 'Opening', value: data.letter.opening },
                {
                  label: 'Afsluiting',
                  value: data.letter.closing ? `${data.letter.closing.slice(0, 140)}…` : '',
                },
                {
                  label: 'Bijlage Factuurinformatie',
                  value: data.letter.billing_annex ? 'Gaat mee' : 'Gaat niet mee',
                },
              ]}
            />
            <nldd-button-group>
              <Button
                text="Wijzig opening en afsluiting"
                onClick={() => start({ kind: 'letter' })}
              />
            </nldd-button-group>
          </Section>
        ) : null}

        {data?.drafting_available ? (
          <Section title="Taalmodel" level={2}>
            <FormFields>
              <CheckboxInput
                label="Vermeld in de offerte dat een taalmodel is gebruikt bij het opstellen"
                checked={data.ai_disclosure}
                onChange={(checked) => save.mutate({ ai_disclosure: checked })}
              />
            </FormFields>
          </Section>
        ) : null}
      </Page>

      <FormSheet
        open={open?.kind === 'organisation'}
        title="Organisatie wijzigen"
        submitText="Bewaar"
        busy={save.isPending}
        error={open?.kind === 'organisation' ? error : null}
        onClose={() => setOpen(null)}
        onSubmit={() => sender && save.mutate({ sender })}
      >
        <nldd-text>
          Geldt voor offertes die je hierna maakt. Een offerte die al is gemaakt verandert niet.
        </nldd-text>
        <TextInput
          label="Naam van de organisatie"
          value={sender?.organisation ?? ''}
          onChange={(organisation) => set({ organisation })}
        />
        <TextInput
          label="Onderdeel van"
          hint="Een regel per organisatie, de bovenste eerst. Staat naast het Rijkslint."
          value={fromLines(sender?.part_of ?? [])}
          onChange={(text) => set({ part_of: toLines(text) })}
          multiline
          optional
        />
        <TextInput
          label="Eenheid"
          hint="Bijvoorbeeld de afkorting van de organisatie en de naam van het onderdeel."
          value={sender?.unit ?? ''}
          onChange={(unit) => set({ unit })}
          optional
        />
        <TextInput
          label="Bezoekadres"
          value={fromLines(sender?.visiting_address ?? [])}
          onChange={(text) => set({ visiting_address: toLines(text) })}
          multiline
          optional
        />
        <TextInput
          label="Postadres"
          value={fromLines(sender?.postal_address ?? [])}
          onChange={(text) => set({ postal_address: toLines(text) })}
          multiline
          optional
        />
        <TextInput
          label="Adres voor opdrachten"
          hint="Het e-mailadres waar een opdrachtgever de opdracht naartoe stuurt."
          value={sender?.orders_email ?? ''}
          onChange={(orders_email) => set({ orders_email })}
          optional
        />
      </FormSheet>

      <FormSheet
        open={open?.kind === 'people'}
        title="Contactpersoon en ondertekenaar wijzigen"
        submitText="Bewaar"
        busy={save.isPending}
        error={open?.kind === 'people' ? error : null}
        onClose={() => setOpen(null)}
        onSubmit={() => sender && save.mutate({ sender })}
      >
        <TextInput
          label="Naam contactpersoon"
          value={sender?.contact.name ?? ''}
          onChange={(name) => sender && set({ contact: { ...sender.contact, name } })}
          optional
        />
        <TextInput
          label="Rol contactpersoon"
          value={sender?.contact.role ?? ''}
          onChange={(role) => sender && set({ contact: { ...sender.contact, role } })}
          optional
        />
        <TextInput
          label="E-mailadres contactpersoon"
          value={sender?.contact.email ?? ''}
          onChange={(email) => sender && set({ contact: { ...sender.contact, email } })}
          optional
        />
        <TextInput
          label="Telefoon contactpersoon"
          value={sender?.contact.phone ?? ''}
          onChange={(phone) => sender && set({ contact: { ...sender.contact, phone } })}
          optional
        />
        <TextInput
          label="Tekent namens"
          hint='Staat in het tekenblok achter "namens".'
          value={sender?.signatory.on_behalf_of ?? ''}
          onChange={(on_behalf_of) =>
            sender && set({ signatory: { ...sender.signatory, on_behalf_of } })
          }
          optional
        />
        <TextInput
          label="Naam ondertekenaar"
          value={sender?.signatory.name ?? ''}
          onChange={(name) => sender && set({ signatory: { ...sender.signatory, name } })}
          optional
        />
        <TextInput
          label="Functie ondertekenaar"
          value={sender?.signatory.title ?? ''}
          onChange={(title) => sender && set({ signatory: { ...sender.signatory, title } })}
          optional
        />
        <TextInput
          label="Organisatie in het tekenblok"
          hint="Leeg laten geeft de naam van de organisatie."
          value={sender?.signatory.organisation ?? ''}
          onChange={(organisation) =>
            sender && set({ signatory: { ...sender.signatory, organisation } })
          }
          optional
        />
      </FormSheet>

      <FormSheet
        open={open?.kind === 'block'}
        title={
          open?.kind === 'block' && open.index === null ? 'Nieuw onderdeel' : 'Onderdeel wijzigen'
        }
        submitText="Bewaar"
        busy={save.isPending}
        error={open?.kind === 'block' ? error : null}
        size="wide"
        onClose={() => setOpen(null)}
        onSubmit={submitBlock}
      >
        <TextInput
          label="Kop"
          value={block.heading}
          onChange={(heading) => setBlock((now) => ({ ...now, heading }))}
          required
        />
        <TextInput
          label="Standaardtekst"
          hint={`Leeg laten voor een onderdeel dat je per offerte schrijft. ${MARKS_HINT}${
            data ? ` Tussen accolades vult grip in: ${data.placeholders.join(', ')}.` : ''
          }`}
          value={block.body}
          onChange={(body) => setBlock((now) => ({ ...now, body }))}
          multiline
          optional
        />
        <TextInput
          label="Aanwijzing voor de schrijver"
          hint="Wat in dit onderdeel hoort. De schrijver ziet dit bij het lege onderdeel."
          value={block.hint}
          onChange={(hint) => setBlock((now) => ({ ...now, hint }))}
          multiline
          optional
        />
        <CheckboxInput
          label="Staat in elke offerte: de schrijver kan het niet weglaten"
          checked={block.required}
          onChange={(required) =>
            setBlock((now) => ({ ...now, required, included: required || now.included }))
          }
        />
        <CheckboxInput
          label="Staat standaard in een nieuwe offerte"
          checked={block.included}
          onChange={(included) => setBlock((now) => ({ ...now, included }))}
        />
        <CheckboxInput
          label="Hier staat de tabel met bedragen uit de begroting"
          checked={block.with_costs}
          onChange={(with_costs) => setBlock((now) => ({ ...now, with_costs }))}
        />
        {data?.drafting_available ? (
          <CheckboxInput
            label="Het taalmodel mag een concept voorstellen"
            checked={block.draftable}
            onChange={(draftable) => setBlock((now) => ({ ...now, draftable }))}
          />
        ) : null}
      </FormSheet>

      <FormSheet
        open={open?.kind === 'letter'}
        title="Opening en afsluiting wijzigen"
        submitText="Bewaar"
        busy={save.isPending}
        error={open?.kind === 'letter' ? error : null}
        size="wide"
        onClose={() => setOpen(null)}
        onSubmit={() => letter && save.mutate({ letter })}
      >
        <TextInput
          label="Opening"
          hint="De eerste zin na de aanhef."
          value={letter?.opening ?? ''}
          onChange={(opening) => setLetter((now) => (now ? { ...now, opening } : now))}
          multiline
          optional
        />
        <TextInput
          label="Afsluiting"
          hint={`De tekst na het laatste onderdeel, voor het tekenblok. ${MARKS_HINT}`}
          value={letter?.closing ?? ''}
          onChange={(closing) => setLetter((now) => (now ? { ...now, closing } : now))}
          multiline
          optional
        />
        <CheckboxInput
          label="Voeg de bijlage Factuurinformatie toe"
          checked={letter?.billing_annex ?? false}
          onChange={(billing_annex) => setLetter((now) => (now ? { ...now, billing_annex } : now))}
        />
      </FormSheet>
    </>
  );
}
