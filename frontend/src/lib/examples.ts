// Input examples only. Predictions always come from POST /api/triage.
export const EXAMPLE_INPUTS = [
  { label: 'Billing issue', text: 'My payment was deducted twice. Please help me check the duplicate charge.' },
  { label: 'Technical issue', text: 'The production API is returning server errors for every request and checkout has stopped.' },
  { label: 'Account access', text: 'Someone changed my login email without permission and I have lost access to the account.' },
  { label: 'Product question', text: 'Does the product offer a calendar view for project tasks?' },
  { label: 'Vague input', text: 'zzzzqqqvxxxx zzzzqqqvxxxx' },
] as const;
