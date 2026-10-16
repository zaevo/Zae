import type { ReactNode } from "react";

/** Re-mounts on every navigation, giving each module a soft slide-in transition. */
export default function Template({ children }: { children: ReactNode }) {
  return <div className="animate-page-in">{children}</div>;
}
