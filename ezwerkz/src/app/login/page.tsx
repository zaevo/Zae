import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/auth";
import { LoginForm } from "./LoginForm";

export const metadata = { title: "Sign in" };

export default async function LoginPage() {
  const user = await getSessionUser();
  if (user) redirect("/");
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Sign in to EzWerkz</h1>
        <p className="mt-1 text-sm text-muted">We&apos;ll email you a one-time sign-in link.</p>
      </div>
      <LoginForm />
    </div>
  );
}
