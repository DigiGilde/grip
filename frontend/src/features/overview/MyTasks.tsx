import { MyTasksBlock } from '@/features/tasks';
import { Section } from '@/ui/layout';

interface MyTasksProps {
  /** How many tasks to show before the link to the Taken page. */
  limit?: number;
}

/**
 * The reader's own first few tasks on the start page. What a task says and
 * which tasks are the reader's to do is the tasks feature's; this is only
 * the place where the start page puts them.
 */
export function MyTasks({ limit = 4 }: MyTasksProps) {
  return (
    <Section title="Mijn taken">
      <MyTasksBlock limit={limit} />
    </Section>
  );
}
