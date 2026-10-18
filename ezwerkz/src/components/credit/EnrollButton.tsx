"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { errorMessage, sendJson } from "./api";

export function EnrollButton({ label }: { label: string }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  return (
    <div className="space-y-2">
      <Button
        disabled={pending}
        onClick={() =>
          start(async () => {
            setError(null);
            try {
              await sendJson("/api/credit/enroll", { method: "POST" });
              router.refresh();
            } catch (err) {
              setError(errorMessage(err));
            }
          })
        }
      >
        {pending ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : null}
        {label}
      </Button>
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
