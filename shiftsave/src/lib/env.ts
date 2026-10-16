/**
 * Server-side environment access. Demo mode is on whenever Supabase isn't
 * configured, so every page renders with seeded sample data and every API
 * route returns a realistic mock instead of failing.
 */

export const env = {
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  supabaseAnonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "",
  supabaseServiceRoleKey: process.env.SUPABASE_SERVICE_ROLE_KEY ?? "",
  stripeSecretKey: process.env.STRIPE_SECRET_KEY ?? "",
  stripeWebhookSecret: process.env.STRIPE_WEBHOOK_SECRET ?? "",
  twilioAccountSid: process.env.TWILIO_ACCOUNT_SID ?? "",
  twilioAuthToken: process.env.TWILIO_AUTH_TOKEN ?? "",
  twilioMessagingServiceSid: process.env.TWILIO_MESSAGING_SERVICE_SID ?? "",
  anthropicApiKey: process.env.ANTHROPIC_API_KEY ?? "",
  checkrApiKey: process.env.CHECKR_API_KEY ?? "",
  furnisherApiUrl: process.env.FURNISHER_API_URL ?? "",
  furnisherApiKey: process.env.FURNISHER_API_KEY ?? "",
  appUrl: process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000",
};

export function isDemoMode(): boolean {
  return !env.supabaseUrl || !env.supabaseAnonKey;
}

/** Throws a clear error when a live integration is called without its key. */
export function requireEnv(name: keyof typeof env): string {
  const value = env[name];
  if (!value) throw new Error(`Missing environment variable for ${name}`);
  return value;
}
