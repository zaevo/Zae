import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const variants: Record<Variant, string> = {
  primary: "bg-accent text-accent-ink hover:opacity-90",
  secondary: "bg-surface-2 text-ink hover:bg-line",
  ghost: "bg-transparent text-ink hover:bg-surface-2",
  danger: "bg-danger text-white hover:opacity-90",
};

const base =
  "inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return <button className={cn(base, variants[variant], className)} {...props} />;
}

export function ButtonLink({
  href,
  variant = "primary",
  className,
  children,
}: {
  href: string;
  variant?: Variant;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link href={href} className={cn(base, variants[variant], className)}>
      {children}
    </Link>
  );
}

/** Round icon action with a label underneath (Add money, Send, Cards …). */
export function ActionCircle({
  icon,
  label,
  href,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  href?: string;
  onClick?: () => void;
}) {
  const circle = (
    <span className="flex h-12 w-12 items-center justify-center rounded-full bg-surface-2 text-ink transition group-hover:bg-line">
      {icon}
    </span>
  );
  const text = <span className="text-xs font-medium text-muted">{label}</span>;
  if (href) {
    return (
      <Link href={href} className="group flex flex-col items-center gap-1.5">
        {circle}
        {text}
      </Link>
    );
  }
  return (
    <button type="button" onClick={onClick} className="group flex flex-col items-center gap-1.5">
      {circle}
      {text}
    </button>
  );
}
