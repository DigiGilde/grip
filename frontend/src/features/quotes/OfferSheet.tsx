import { useRef, useState } from 'react';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { TextInput } from '@/features/assignments/ui';
import { FormSheet, Quiet } from '@/ui/layout';
import {
  OFFER_CHANNEL_EFFECTS,
  OFFER_CHANNEL_LABELS,
  type OfferChannel,
  type QuoteChannel,
} from './api';
import { channelReason } from './offers';
import './register';

const ORDER: OfferChannel[] = ['signing_link', 'document', 'client_instance'];

function ChannelRow({
  option,
  checked,
  onChoose,
}: {
  option: QuoteChannel;
  checked: boolean;
  onChoose: () => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', (event) => {
    const detail = (event as CustomEvent<{ checked?: boolean }>).detail;
    if (detail?.checked !== false) onChoose();
  });
  // A channel that is not possible stays in the list with the reason, so the
  // reader sees why instead of meeting a dead button.
  const line = option.available
    ? (OFFER_CHANNEL_EFFECTS[option.channel] ?? '')
    : channelReason(option.reason);
  return (
    <nldd-list-item
      ref={ref}
      radio
      checked={orUndef(checked && option.available)}
      disabled={orUndef(!option.available)}
    >
      {/* The row is the radio; this only draws its shape, so the choice shows. */}
      <nldd-cell width="32px">
        <nldd-radio-button
          decorative
          checked={orUndef(checked && option.available)}
          disabled={orUndef(!option.available)}
        />
      </nldd-cell>
      <nldd-text-cell
        text={OFFER_CHANNEL_LABELS[option.channel] ?? option.channel}
        supporting-text={line}
      />
    </nldd-list-item>
  );
}

interface OfferSheetProps {
  open: boolean;
  channels: readonly QuoteChannel[];
  /** Offering with a signing link also mails the link to the invited person. */
  mailsLink?: boolean;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onOffer: (channel: OfferChannel, email: string) => void;
}

/**
 * Choosing how an issued quote reaches the client. One sheet for all
 * channels: each says in one line what happens, and one that is not possible
 * says why.
 */
export function OfferSheet({
  open,
  channels,
  mailsLink = false,
  busy,
  error,
  onClose,
  onOffer,
}: OfferSheetProps) {
  const options = ORDER.map((name) => channels.find((option) => option.channel === name)).filter(
    (option): option is QuoteChannel => option !== undefined,
  );
  // No channel is chosen for the person: offering is the moment the quote
  // leaves, and a default would send it a way nobody picked.
  const [chosen, setChosen] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  const channel = (
    options.some((option) => option.channel === chosen && option.available) ? chosen : null
  ) as OfferChannel | null;

  return (
    <FormSheet
      open={open}
      title="Offerte aanbieden"
      submitText="Bied aan"
      busy={busy}
      submitDisabled={channel === null}
      error={problem ?? error}
      onClose={() => {
        setProblem(null);
        onClose();
      }}
      onSubmit={() => {
        if (!channel) {
          setProblem('Kies hoe de opdrachtgever de offerte krijgt.');
          return;
        }
        if (channel === 'signing_link' && !/^[^@\s]+@[^@\s]+$/.test(email.trim())) {
          setProblem('Vul het e-mailadres in van wie gaat tekenen.');
          return;
        }
        setProblem(null);
        onOffer(channel, email.trim());
      }}
    >
      <nldd-list type="radiogroup" accessible-label="Hoe de opdrachtgever de offerte krijgt">
        {options.map((option) => (
          <ChannelRow
            key={option.channel}
            option={option}
            checked={option.channel === channel}
            onChoose={() => setChosen(option.channel)}
          />
        ))}
      </nldd-list>
      {channel === null ? <Quiet>Kies eerst hoe de opdrachtgever de offerte krijgt.</Quiet> : null}
      {channel === 'signing_link' ? (
        <TextInput
          label="E-mailadres van wie tekent"
          hint="Het adres waarmee deze persoon inlogt. De link werkt 30 dagen."
          value={email}
          onChange={setEmail}
          required
        />
      ) : null}
      {channel === 'signing_link' && mailsLink && /^[^@\s]+@[^@\s]+$/.test(email.trim()) ? (
        <Quiet>{email.trim()} krijgt de link per mail.</Quiet>
      ) : null}
    </FormSheet>
  );
}
