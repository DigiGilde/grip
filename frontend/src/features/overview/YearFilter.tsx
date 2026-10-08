import { InlineSelect } from '@/features/assignments/ui';
import type { YearChoice } from './api';
import { yearOptions } from './years';

export function YearFilter({
  value,
  onChange,
}: {
  value: YearChoice;
  onChange: (value: YearChoice) => void;
}) {
  return (
    <InlineSelect
      label="Jaar"
      value={value}
      onChange={onChange}
      options={yearOptions()}
      width="180px"
    />
  );
}
