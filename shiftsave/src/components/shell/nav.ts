import type { Role } from "@/lib/types";

export interface NavItem {
  href: string;
  label: string;
  icon: "home" | "credit" | "wallet" | "shifts" | "business" | "admin";
}

const ALL: Array<NavItem & { roles: Role[] }> = [
  { href: "/", label: "Home", icon: "home", roles: ["member", "worker", "client_manager", "admin"] },
  { href: "/credit", label: "Credit", icon: "credit", roles: ["member", "worker", "admin"] },
  { href: "/wallet", label: "Wallet", icon: "wallet", roles: ["member", "worker", "admin"] },
  { href: "/shifts", label: "Shifts", icon: "shifts", roles: ["worker", "admin"] },
  { href: "/business", label: "Business", icon: "business", roles: ["client_manager", "admin"] },
  { href: "/admin", label: "Admin", icon: "admin", roles: ["admin"] },
];

export function navFor(role: Role): NavItem[] {
  return ALL.filter((i) => i.roles.includes(role)).map(({ roles: _roles, ...item }) => item);
}
