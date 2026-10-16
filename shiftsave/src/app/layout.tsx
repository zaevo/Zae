import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { AppShell } from "@/components/shell/AppShell";
import { navFor } from "@/components/shell/nav";
import { DemoBanner } from "@/components/ui/DemoBanner";
import { getSessionUser } from "@/lib/auth";

export const metadata: Metadata = {
  title: { default: "ShiftSave", template: "%s · ShiftSave" },
  description: "Build credit, spend smarter, and pick up shifts — in one app.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f5f7" },
    { media: "(prefers-color-scheme: dark)", color: "#07080b" },
  ],
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const user = await getSessionUser();
  return (
    <html lang="en">
      <body className="font-sans">
        {user?.demo ? <DemoBanner /> : null}
        {user ? (
          <AppShell nav={navFor(user.role)} userName={user.fullName} role={user.role} demo={user.demo}>
            {children}
          </AppShell>
        ) : (
          <main className="mx-auto max-w-md px-4 py-12">{children}</main>
        )}
      </body>
    </html>
  );
}
