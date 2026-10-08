/** What is wrong with the form, or null. Checked here so the message is Dutch. */
export function validateRequest(values: {
  contractor: string;
  name: string;
  startDate: string;
  endDate: string;
}): string | null {
  if (!values.contractor) return 'Kies de opdrachtnemer bij wie je de offerte aanvraagt.';
  if (!values.name.trim()) return 'Geef de aanvraag een naam.';
  if (values.startDate && values.endDate && values.endDate < values.startDate) {
    return 'De einddatum ligt voor de begindatum.';
  }
  return null;
}
