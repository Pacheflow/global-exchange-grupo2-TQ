import type { LucideIcon, LucideProps } from "lucide-react";
import {
  ChevronDown,
  Globe2,
  LayoutDashboard,
  LogIn,
  LogOut,
  Menu,
  ShieldCheck,
  UserPlus,
  UserRound,
  X,
} from "lucide-react";

const icons = {
  "chevron-down": ChevronDown,
  dashboard: LayoutDashboard,
  globe: Globe2,
  login: LogIn,
  logout: LogOut,
  menu: Menu,
  roles: ShieldCheck,
  "user-plus": UserPlus,
  user: UserRound,
  close: X,
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
