import { CreditCard, Wrench, UserRound, Package } from 'lucide-react';
import type { Category } from '../../lib/types';

const categoryIcons = { Billing: CreditCard, Technical: Wrench, Account: UserRound, Product: Package };
export function CategoryIcon({ category, size = 16 }: { category: Category; size?: number }) {
  const Icon = categoryIcons[category];
  return <Icon size={size} aria-hidden="true" />;
}
