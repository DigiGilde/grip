/**
 * The nldd-* elements the client-side screens use beyond what the shell and
 * the assignment, quote and node screens already register. Importing a
 * component module twice is harmless.
 */
import '@/features/assignments/register';
import '@/features/quotes/elements';
import '@/features/nodes/elements';
import '@nldd/design-system/modal-dialog';
