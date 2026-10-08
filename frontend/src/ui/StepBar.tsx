/**
 * The one step bar of the application.
 *
 * The design system's bar takes no "current" of its own: every item says
 * whether it is past, current or future, and an item without a status makes
 * step 1 the current one. Two screens set a `current` attribute on the bar,
 * which it ignores, and so showed step 1 whatever the real state was. This
 * component takes the position once and gives every item its status, so a
 * bar cannot disagree with the state it is given.
 */
interface Step {
  /** Stable key; the text when omitted. */
  key?: string;
  text: string;
  /** Makes a past or current step a link, for instance to the tab where it was done. */
  href?: string;
}

interface StepBarProps {
  steps: readonly Step[];
  /**
   * Position of the current step, counted from 1. A number above the number
   * of steps means every step is done.
   */
  current: number;
  accessibleLabel: string;
  /** Set while the facts behind the bar are still loading; tests wait on it. */
  ready?: boolean;
}

export function StepBar({
  steps,
  current,
  accessibleLabel,
  ready,
}: StepBarProps) {
  return (
    <nldd-step-bar
      accessible-label={accessibleLabel}
      {...(ready === undefined
        ? {}
        : { "data-ready": ready ? "true" : "false" })}
    >
      {steps.map((step, index) => {
        const position = index + 1;
        const status =
          position < current
            ? "past"
            : position === current
              ? "current"
              : "future";
        return (
          <nldd-step-bar-item
            key={step.key ?? step.text}
            text={step.text}
            status={status}
            {...(step.href && status !== "future" ? { href: step.href } : {})}
          />
        );
      })}
    </nldd-step-bar>
  );
}
