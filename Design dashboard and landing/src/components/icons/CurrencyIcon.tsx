import type { LucideProps } from 'lucide-react';
import AppIcon from './AppIcon';

interface CurrencyIconProps extends Omit<LucideProps, 'ref' | 'name'> {
  code?: string;
}

export default function CurrencyIcon({ code: _code, ...props }: CurrencyIconProps) {
  return <AppIcon name="currency" {...props} />;
}
