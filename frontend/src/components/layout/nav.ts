import { BarChart3, Ban, Bot, LayoutDashboard, Settings, Upload, Users, Wrench } from "lucide-react";

export const NAV = [
  { href: "/dashboard", key: "dashboard", Icon: LayoutDashboard },
  { href: "/stats", key: "stats", Icon: BarChart3 },
  { href: "/ban-hammer", key: "banHammer", Icon: Ban },
  { href: "/tools", key: "tools", Icon: Wrench },
  { href: "/friends", key: "friends", Icon: Users },
  { href: "/imports", key: "imports", Icon: Upload },
  { href: "/automations", key: "automations", Icon: Bot },
  { href: "/settings", key: "settings", Icon: Settings },
] as const;
