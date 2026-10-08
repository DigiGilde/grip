import './brand.css';

interface BrandMarkProps {
  /** Side in pixels. The mark is drawn on a grid of 48 and stays sharp at 16. */
  size?: number;
  /** Goes into a named slot of a design-system component, such as `media`. */
  slot?: string;
  /** Only where the mark stands alone, without a name beside it. */
  label?: string;
}

/**
 * The product mark of grip: a bracket that holds a bar.
 *
 * The drawing is the one in frontend/brand/mark.svg; scripts/build-brand.mjs
 * makes the icon files from that same source. Decorative wherever a name
 * stands next to it; with `label` it carries the name itself.
 */
export function BrandMark({ size = 24, slot, label }: BrandMarkProps) {
  return (
    <svg
      className="brand-mark"
      {...(slot ? { slot } : {})}
      width={size}
      height={size}
      viewBox="0 0 48 48"
      {...(label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': true })}
      focusable="false"
    >
      <path d="M6 6h28v8H14v20h20v8H6z" />
      <path d="M24 20h18v8H24z" />
    </svg>
  );
}
