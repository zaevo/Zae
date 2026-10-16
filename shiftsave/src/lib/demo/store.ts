/**
 * Mutable demo-mode state that survives across requests in one server
 * process. Kept on globalThis because Next.js can load a module more than
 * once (route handlers vs. server components), and module-level variables
 * would then drift apart.
 */
const ROOT = "__shiftsaveDemoStore" as const;

type Bag = Record<string, unknown>;

function bag(): Bag {
  const g = globalThis as unknown as Record<string, Bag | undefined>;
  return (g[ROOT] ??= {});
}

/** Get (or lazily create) a named piece of demo state. Mutate the returned object in place. */
export function demoStore<T>(key: string, init: () => T): T {
  const b = bag();
  if (!(key in b)) b[key] = init();
  return b[key] as T;
}
