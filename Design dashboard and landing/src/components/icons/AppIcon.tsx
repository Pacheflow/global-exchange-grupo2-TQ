import type { LucideIcon, LucideProps } from 'lucide-react';
import {
  Activity,
  ArrowDown,
  ArrowLeft,
  ArrowLeftRight,
  ArrowRight,
  ArrowUp,
  ArrowUpDown,
  Bell,
  BriefcaseBusiness,
  Building2,
  ChartLine,
  Check,
  ChevronDown,
  CircleCheck,
  CircleDollarSign,
  ClipboardList,
  CreditCard,
  Equal,
  FileCheck2,
  FileText,
  Globe2,
  HandCoins,
  History,
  Hourglass,
  Info,
  KeyRound,
  LayoutDashboard,
  Lightbulb,
  Link2,
  LockKeyhole,
  LockOpen,
  Minus,
  Plus,
  Scale,
  Settings,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  UserRound,
  Users,
  Vault,
  Zap,
} from 'lucide-react';

const ICONS = {
  activity: Activity,
  buy: ArrowDown,
  back: ArrowLeft,
  exchange: ArrowLeftRight,
  forward: ArrowRight,
  sell: ArrowUp,
  movements: ArrowUpDown,
  bell: Bell,
  briefcase: BriefcaseBusiness,
  building: Building2,
  chart: ChartLine,
  check: Check,
  'chevron-down': ChevronDown,
  confirmation: CircleCheck,
  currency: CircleDollarSign,
  equal: Equal,
  reports: ClipboardList,
  payment: CreditCard,
  'file-check': FileCheck2,
  file: FileText,
  globe: Globe2,
  earnings: HandCoins,
  history: History,
  pending: Hourglass,
  info: Info,
  authentication: KeyRound,
  dashboard: LayoutDashboard,
  insight: Lightbulb,
  association: Link2,
  security: LockKeyhole,
  unlock: LockOpen,
  neutral: Minus,
  plus: Plus,
  scale: Scale,
  settings: Settings,
  roles: ShieldCheck,
  down: TrendingDown,
  up: TrendingUp,
  user: UserRound,
  users: Users,
  vault: Vault,
  realtime: Zap,
} satisfies Record<string, LucideIcon>;

export type AppIconName = keyof typeof ICONS;

interface AppIconProps extends Omit<LucideProps, 'ref'> {
  name: AppIconName;
}

export default function AppIcon({
  name,
  size = 20,
  strokeWidth = 1.8,
  ...props
}: AppIconProps) {
  const Icon = ICONS[name];
  return (
    <Icon
      aria-hidden="true"
      focusable="false"
      size={size}
      strokeWidth={strokeWidth}
      {...props}
    />
  );
}
