import { StepBar } from "@/ui/StepBar";
import { Button } from "@/features/assignments/ui";
import { formatDate, formatEuro } from "@/lib/format";
import { Quiet, Stack } from "@/ui/layout";
import {
  QUOTE_STATUS_COLORS,
  QUOTE_STATUS_LABELS,
  quoteDocumentUrl,
  signedDocumentUrl,
  signingLink,
  type QuoteDetail,
  type QuoteOffer,
  type QuoteSummary,
} from "./api";
import {
  APPROVER_RIGHT,
  approvalLine,
  awaitsApproval,
  type ApprovalState,
} from "./approval";
import { formatDateTime } from "./format";
import {
  invitationMessage,
  linkWorks,
  listedOffers,
  offerState,
  offerTitle,
  primaryAction,
  quoteSteps,
} from "./offers";
import { QuoteDetails } from "./QuoteDetails";
import { CopyButton, DocumentLink, MenuAction } from "./ui";
import "./register";

export type CardAction =
  | { kind: "offer" }
  | { kind: "upload" }
  | { kind: "reject" }
  | { kind: "request-approval" }
  | { kind: "withdraw-approval" }
  | { kind: "review" }
  | { kind: "new-quote" }
  | { kind: "withdraw-link"; invitationId: string }
  | { kind: "renew-link"; invitationId: string };

function madeText(quote: QuoteSummary): string {
  return `Gemaakt op ${formatDate(quote.issued_at)}${quote.issued_by_name ? ` door ${quote.issued_by_name}` : ""}`;
}

/** What the quote says about itself in one quiet line. */
function byline(quote: QuoteSummary): string {
  return [
    quote.valid_until ? `Geldig t/m ${formatDate(quote.valid_until)}` : null,
    madeText(quote),
  ]
    .filter(Boolean)
    .join(" · ");
}

function Decision({ quote }: { quote: QuoteSummary }) {
  const acceptance = quote.acceptance;
  if (acceptance) {
    const who = [
      acceptance.signer_name,
      acceptance.signer_function ? `(${acceptance.signer_function})` : null,
      acceptance.organisation_name
        ? `namens ${acceptance.organisation_name}`
        : null,
    ]
      .filter(Boolean)
      .join(" ");
    return (
      <nldd-text>
        Getekend op {formatDateTime(acceptance.signed_at)}
        {who ? ` door ${who}` : ""}.
      </nldd-text>
    );
  }
  if (quote.rejection) {
    return (
      <nldd-text>
        Afgewezen op {formatDateTime(quote.rejection.rejected_at)}
        {quote.rejection.reason ? `: ${quote.rejection.reason}` : "."}
      </nldd-text>
    );
  }
  return null;
}

/**
 * One offer: how it went out, where it stands, and for a signing link the
 * link itself with its actions. Stacked, so the link and its buttons have
 * the full width and never fall off the edge.
 */
function OfferRow({
  offer,
  quote,
  name,
  mayManage,
  onAction,
}: {
  offer: QuoteOffer;
  quote: QuoteSummary;
  name: string;
  mayManage: boolean;
  onAction: (action: CardAction) => void;
}) {
  const invitation = offer.invitation ?? null;
  const works = linkWorks(offer);
  const link = invitation ? signingLink(invitation.signing_path) : "";
  const open = quote.status === "issued";
  const manages = mayManage && invitation !== null && open;
  const state = [
    offerState(offer, quote),
    `aangeboden op ${formatDateTime(offer.offered_at)}`,
    manages && works && invitation.expires_at
      ? `link geldig t/m ${formatDate(invitation.expires_at)}`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <div role="listitem" data-offer={offer.channel}>
      <Stack gap="close">
        <Stack gap="tight">
          <nldd-text
            {...(offer.delivery === "refused" ? { color: "critical" } : {})}
          >
            {offerTitle(offer)}
          </nldd-text>
          <Quiet>{state}</Quiet>
        </Stack>
        {manages ? (
          <>
            {works ? (
              <nldd-text size="sm" data-signing-link>
                {link}
              </nldd-text>
            ) : null}
            <nldd-container layout="wrap" gap="8" vertical-alignment="center">
              {works ? (
                <>
                  <CopyButton text="Kopieer tekenlink" value={link} size="sm" />
                  <CopyButton
                    text="Kopieer bericht"
                    appearance="neutral-transparent"
                    size="sm"
                    value={invitationMessage({
                      reference: quote.reference,
                      name,
                      link,
                      email: offer.recipient,
                      expiresAt: invitation.expires_at,
                    })}
                  />
                </>
              ) : null}
              <nldd-icon-button
                icon="more"
                size="sm"
                text={`Meer acties voor de tekenlink${offer.recipient ? ` aan ${offer.recipient}` : ""}`}
              >
                <nldd-menu slot="popup" placement="bottom-start">
                  <MenuAction
                    text={
                      works
                        ? "Verleng met 30 dagen"
                        : "Maak de tekenlink weer geldig"
                    }
                    onSelect={() =>
                      onAction({
                        kind: "renew-link",
                        invitationId: invitation.id,
                      })
                    }
                  />
                  {works ? (
                    <MenuAction
                      text="Trek de tekenlink in"
                      onSelect={() =>
                        onAction({
                          kind: "withdraw-link",
                          invitationId: invitation.id,
                        })
                      }
                    />
                  ) : null}
                </nldd-menu>
              </nldd-icon-button>
            </nldd-container>
          </>
        ) : null}
      </Stack>
    </div>
  );
}

interface QuoteCardProps {
  quote: QuoteSummary;
  /** The quote with its offers, once loaded. */
  detail: QuoteDetail | undefined;
  /** Internal approval, where the organisation asks for it; undefined while loading. */
  approval?: ApprovalState | null;
  mayManage: boolean;
  busy: boolean;
  onAction: (action: CardAction) => void;
}

/**
 * One quote as one card: the amount, where it stands, and the one thing to
 * do next. Everything else is quiet.
 */
export function QuoteCard({
  quote,
  detail,
  approval,
  mayManage,
  busy,
  onAction,
}: QuoteCardProps) {
  const offers = detail?.offers ?? [];
  const listed = listedOffers(offers);
  const steps = quoteSteps(quote, offers, approval);
  // Complete once the offers and the approval are in: until then no action,
  // so a button never changes under the pointer.
  const ready = detail !== undefined && approval !== undefined;
  const next =
    mayManage && ready ? primaryAction(quote, offers, approval) : null;
  const open = quote.status === "issued";
  const blocked = awaitsApproval(approval);
  // Approval is a matter between making and offering; once the quote is out
  // or decided it is history and stays in the details.
  const approvalText =
    open && offers.length === 0 ? approvalLine(approval) : null;
  const mayReview = open && Boolean(approval?.may_decide_approval);
  const mayWithdrawApproval = open && Boolean(approval?.may_withdraw);
  const name = detail?.content?.name ?? "";
  const current = steps.findIndex((step) => step.status === "current") + 1;

  return (
    <nldd-card accessible-label={`Offerte ${quote.reference ?? ""}`.trim()}>
      <nldd-container padding="24" gap="24">
        <Stack gap="close">
          <nldd-title
            size={3}
            heading-level={3}
            overline={
              quote.reference ? `Offerte ${quote.reference}` : "Offerte"
            }
            text={
              quote.total_cents !== undefined
                ? formatEuro(quote.total_cents)
                : "Offerte"
            }
          >
            <nldd-badge
              slot="end"
              color={QUOTE_STATUS_COLORS[quote.status] ?? "neutral"}
              text={
                open && offers.length > 0
                  ? "Aangeboden"
                  : (QUOTE_STATUS_LABELS[quote.status] ?? quote.status)
              }
            />
          </nldd-title>
          <Quiet>{byline(quote)}</Quiet>
          {quote.snapshot_hash !== undefined ? (
            <nldd-container layout="row" gap="16" vertical-alignment="center">
              <DocumentLink
                href={quoteDocumentUrl(quote.id)}
                text="Bekijk"
                newTab
              />
              <DocumentLink
                href={quoteDocumentUrl(quote.id, true)}
                text="Download pdf"
              />
              {quote.acceptance?.has_document ? (
                <DocumentLink
                  href={signedDocumentUrl(quote.id)}
                  text="Getekend exemplaar"
                />
              ) : null}
              <QuoteDetails
                hash={quote.snapshot_hash}
                facts={[
                  { label: "Kenmerk", value: quote.reference ?? "" },
                  {
                    label: "Gemaakt",
                    value: `${formatDate(quote.issued_at)}${quote.issued_by_name ? ` door ${quote.issued_by_name}` : ""}`,
                  },
                  { label: "Adres voor systemen", value: quote.uri },
                ]}
              />
            </nldd-container>
          ) : null}
        </Stack>

        <StepBar
          steps={steps}
          current={current > 0 ? current : steps.length + 1}
          accessibleLabel="Stappen van deze offerte"
          ready={ready}
        />

        <Decision quote={quote} />

        {listed.length > 0 ? (
          <div role="list" aria-label="Hoe deze offerte is aangeboden">
            <Stack gap="related">
              {listed.map((offer) => (
                <OfferRow
                  key={offer.id}
                  offer={offer}
                  quote={quote}
                  name={name}
                  mayManage={mayManage}
                  onAction={onAction}
                />
              ))}
            </Stack>
          </div>
        ) : null}

        {approvalText ? (
          <Stack gap="close">
            <nldd-text>{approvalText}</nldd-text>
            {approval?.status === "requested" &&
            approval.current?.request_note ? (
              <Quiet>
                Toelichting bij de aanvraag: {approval.current.request_note}
              </Quiet>
            ) : null}
            {blocked && approval && !approval.approver_available ? (
              <nldd-banner
                variant="warning"
                size="sm"
                text="Niemand kan deze offerte nu goedkeuren"
                supporting-text={`Een beheerder kent het recht "${APPROVER_RIGHT}" toe bij Team, onder Rechten in grip van een persoon.`}
              />
            ) : null}
          </Stack>
        ) : null}

        {open && ready && (mayManage || mayReview || mayWithdrawApproval) ? (
          <nldd-container layout="row" gap="8" vertical-alignment="center">
            {next === "offer" ? (
              <Button
                text="Bied aan"
                appearance="primary"
                disabled={busy}
                onClick={() => onAction({ kind: "offer" })}
              />
            ) : null}
            {next === "request-approval" ? (
              <Button
                text="Vraag goedkeuring"
                appearance="primary"
                disabled={busy}
                onClick={() => onAction({ kind: "request-approval" })}
              />
            ) : null}
            {next === "new-quote" ? (
              <Button
                text="Maak nieuwe offerte"
                appearance="primary"
                disabled={busy}
                onClick={() => onAction({ kind: "new-quote" })}
              />
            ) : null}
            {next === "record-signed" ? (
              <Button
                text="Leg getekende pdf vast"
                appearance="primary"
                disabled={busy}
                onClick={() => onAction({ kind: "upload" })}
              />
            ) : null}
            {mayReview ? (
              <Button
                text="Beoordeel"
                appearance={next === null ? "primary" : "secondary"}
                disabled={busy}
                onClick={() => onAction({ kind: "review" })}
              />
            ) : null}
            {mayManage || mayWithdrawApproval ? (
              <nldd-icon-button
                icon="more"
                text="Meer acties voor deze offerte"
              >
                <nldd-menu slot="popup" placement="bottom-start">
                  {mayWithdrawApproval ? (
                    <MenuAction
                      text={
                        approval?.status === "approved"
                          ? "Trek de goedkeuring in"
                          : "Trek de aanvraag in"
                      }
                      onSelect={() => onAction({ kind: "withdraw-approval" })}
                    />
                  ) : null}
                  {mayManage && next !== "offer" && !blocked ? (
                    <MenuAction
                      text="Bied opnieuw aan"
                      onSelect={() => onAction({ kind: "offer" })}
                    />
                  ) : null}
                  {mayManage && next !== "record-signed" && !blocked ? (
                    <MenuAction
                      text="Leg getekende pdf vast"
                      onSelect={() => onAction({ kind: "upload" })}
                    />
                  ) : null}
                  {mayManage ? (
                    <MenuAction
                      text="Leg afwijzing vast"
                      onSelect={() => onAction({ kind: "reject" })}
                    />
                  ) : null}
                </nldd-menu>
              </nldd-icon-button>
            ) : null}
          </nldd-container>
        ) : null}
        {mayManage &&
        open &&
        blocked &&
        approval?.blocked_message &&
        approval.approver_available &&
        next !== "new-quote" ? (
          <Quiet>{approval.blocked_message}</Quiet>
        ) : null}
      </nldd-container>
    </nldd-card>
  );
}

/** An earlier quote in one line: its reference, date, amount and how it ended. */
export function EarlierQuoteRow({ quote }: { quote: QuoteSummary }) {
  const title = [quote.reference, formatDate(quote.issued_at)]
    .filter(Boolean)
    .join(" · ");
  return (
    <nldd-list-item>
      <nldd-text-cell
        text={title}
        supporting-text={[
          QUOTE_STATUS_LABELS[quote.status] ?? quote.status,
          quote.total_cents !== undefined
            ? formatEuro(quote.total_cents)
            : null,
        ]
          .filter(Boolean)
          .join(" · ")}
      />
      {quote.snapshot_hash !== undefined ? (
        <nldd-cell width="fit-content">
          <nldd-link
            href={quoteDocumentUrl(quote.id)}
            text="Bekijk"
            size="md"
            target="_blank"
            accessible-label={`Bekijk offerte ${quote.reference ?? formatDate(quote.issued_at)}`}
          />
        </nldd-cell>
      ) : null}
    </nldd-list-item>
  );
}
