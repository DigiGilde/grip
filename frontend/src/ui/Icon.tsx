/**
 * Icons by concept. A feature says what something is; `@/ui/icons` decides
 * the picture. See docs/ontwerp.md, "Iconen".
 */
import type { ReactNode } from 'react';
import { ICON_SIZE, iconAttribute, iconLabel, iconOf, type IconConcept } from './icons';

interface IconProps {
  concept: IconConcept;
  /** Where it stands; decides the one size for that place. */
  context?: keyof typeof ICON_SIZE;
  /**
   * What the icon says when it stands alone. Without it the icon is
   * decoration next to a label and hidden from assistive technology.
   */
  label?: string;
}

/** A loose icon. Next to a label it is decoration; alone it needs `label`. */
export function Icon({ concept, context = 'inline', label }: IconProps) {
  return (
    <nldd-icon
      icon={iconOf(concept)}
      size={ICON_SIZE[context]}
      {...(label ? { role: 'img', 'aria-label': label, 'aria-hidden': 'false' } : {})}
    />
  );
}

interface IconCellProps {
  concept: IconConcept;
  /** The colour that goes with a status; the icon carries the meaning, the colour repeats it. */
  color?: 'content' | 'secondary' | 'accent' | 'success' | 'warning' | 'critical';
  label?: string;
}

/** An icon in a table or list row: a status at the start, or the mark that the row opens at the end. */
export function IconCell({ concept, color = 'secondary', label, ...rest }: IconCellProps) {
  return (
    <nldd-icon-cell
      size={ICON_SIZE.cell}
      color={color}
      icon={iconOf(concept)}
      {...(label ? { 'aria-label': label } : {})}
      {...rest}
    />
  );
}

interface MoreButtonProps {
  /** What the menu is about, for "Meer acties voor <name>". */
  name: string;
  size?: 'sm' | 'md';
  /** The `nldd-menu` with `slot="popup"`. */
  children: ReactNode;
}

/** The one quiet icon button that holds what else a row or card can do. */
export function MoreButton({ name, size = 'sm', children }: MoreButtonProps) {
  const label = iconLabel('more', name);
  return (
    <nldd-icon-button
      icon={iconOf('more')}
      size={size}
      appearance="neutral-transparent"
      popup-type="menu"
      accessible-label={label}
      text={label}
    >
      {children}
    </nldd-icon-button>
  );
}

interface LinkProps {
  href: string;
  text: string;
}

/** "Terug naar <onderdeel>": the one link above a page title. */
export function BackLink({ href, text }: LinkProps) {
  return <nldd-link href={href} text={text} size="md" {...iconAttribute('back')} />;
}

interface DocumentLinkProps extends LinkProps {
  /**
   * `view` opens the document in a new tab, `download` saves it. Both leave
   * the page, and each says so with its fixed icon.
   */
  kind: 'view' | 'download';
  /** For a download: the full name, for instance with file name and size. */
  accessibleLabel?: string;
  size?: 'sm' | 'md';
}

/** A link to a document: the quote as PDF, an attachment, an export. */
export function DocumentLink({
  href,
  text,
  kind,
  accessibleLabel,
  size = 'md',
}: DocumentLinkProps) {
  return (
    <nldd-link
      href={href}
      text={text}
      size={size}
      {...(kind === 'view'
        ? { target: '_blank', ...iconAttribute('elsewhere') }
        : iconAttribute('download'))}
      {...(accessibleLabel ? { 'accessible-label': accessibleLabel } : {})}
    />
  );
}

interface ExternalLinkProps extends LinkProps {
  /** In running text the link follows the text size. */
  inline?: boolean;
}

/** A link to another site or system, always in a new tab. */
export function ExternalLink({ href, text, inline }: ExternalLinkProps) {
  return (
    <nldd-link
      href={href}
      text={text}
      target="_blank"
      {...(inline ? {} : { size: 'md' })}
      {...iconAttribute('elsewhere')}
    />
  );
}
