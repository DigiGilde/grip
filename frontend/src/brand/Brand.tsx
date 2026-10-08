import { BrandMark } from './BrandMark';
import { PRODUCT_NAME, PRODUCT_SENTENCE, instanceNames } from './names';

interface BrandProps {
  /**
   * Where the brand stands. `login`: the product introduces itself, then the
   * organisation. `signing`: a guest from another organisation sees whose page
   * this is first, and the tool second. `compact`: mark and word only.
   */
  variant: 'login' | 'signing' | 'compact';
  /** The instance name as the server gives it. */
  instanceName?: string | null;
}

/**
 * The product and the organisation together, outside the main toolbar. In the
 * toolbar the same pair is the toolbar title with the mark in its media slot.
 */
export function Brand({ variant, instanceName }: BrandProps) {
  const { organisation } = instanceNames(instanceName);

  if (variant === 'signing') {
    return (
      <div className="brand">
        <BrandMark size={24} />
        <div className="brand-lines">
          <span className="brand-name">{organisation || PRODUCT_NAME}</span>
          {organisation && <span className="brand-quiet">met {PRODUCT_NAME}</span>}
        </div>
      </div>
    );
  }

  if (variant === 'compact') {
    return (
      <div className="brand">
        <BrandMark size={24} />
        <span className="brand-word">{PRODUCT_NAME}</span>
      </div>
    );
  }

  return (
    <div className="brand">
      <BrandMark size={40} />
      <div className="brand-lines">
        <span className="brand-word brand-word-large">{PRODUCT_NAME}</span>
        <span className="brand-quiet">{PRODUCT_SENTENCE}</span>
      </div>
    </div>
  );
}
