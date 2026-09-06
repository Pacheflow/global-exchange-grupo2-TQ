import type { LucideIcon, LucideProps } from "lucide-react";
import {
  Activity,
  ArrowDown,
  ArrowLeftRight,
  ArrowRight,
  ArrowUp,
  BadgeCheck,
  Building2,
  ChartNoAxesCombined,
  Check,
  ChevronDown,
  CircleDollarSign,
  Clock3,
  Equal,
  FileCheck2,
  Globe2,
  History,
  Info,
  KeyRound,
  LayoutDashboard,
  LockKeyhole,
  LogIn,
  LogOut,
  Menu,
  Plus,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  UserPlus,
  UserRound,
  UsersRound,
  WalletCards,
  X,
  Zap,
} from "lucide-react";

const icons = {
  activity: Activity,
  "arrow-down": ArrowDown,
  exchange: ArrowLeftRight,
  forward: ArrowRight,
  "arrow-up": ArrowUp,
  verified: BadgeCheck,
  building: Building2,
  chart: ChartNoAxesCombined,
  check: Check,
  "chevron-down": ChevronDown,
  currency: CircleDollarSign,
  clock: Clock3,
  equal: Equal,
  dashboard: LayoutDashboard,
  "file-check": FileCheck2,
  globe: Globe2,
  history: History,
  info: Info,
  authentication: KeyRound,
  security: LockKeyhole,
  login: LogIn,
  logout: LogOut,
  menu: Menu,
  plus: Plus,
  refresh: RefreshCw,
  roles: ShieldCheck,
  sparkles: Sparkles,
  "user-plus": UserPlus,
  user: UserRound,
  users: UsersRound,
  wallet: WalletCards,
  close: X,
  realtime: Zap,
} satisfies Record<string, LucideIcon>;

export type AppIconName = keyof typeof icons;

interface AppIconProps extends Omit<LucideProps, "ref"> {
  name: AppIconName;
}

export function AppIcon({
  name,
  size = 20,
  strokeWidth = 1.8,
  ...props
}: AppIconProps) {
  const Icon = icons[name];

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
