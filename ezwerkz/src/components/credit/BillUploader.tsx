"use client";

import { useEffect, useRef, useState } from "react";
import { Camera, FileText, LoaderCircle, Upload } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import type { BillAnalysis } from "@/lib/ai/billAnalysis";
import { BILL_ACCEPT_ATTR, BILL_MAX_BYTES, BILL_UPLOAD_MESSAGES, isBillMediaType } from "@/lib/ai/billUpload";
import { BillAnalysisView } from "./BillAnalysisView";

type Status = { kind: "idle" } | { kind: "analyzing" } | { kind: "error"; message: string } | { kind: "done"; analysis: BillAnalysis };

const STEPS = ["Reading your bill…", "Checking every charge…", "Looking for savings…", "Writing your script…"];

function checkFile(file: File): string | null {
  if (file.size === 0) return BILL_UPLOAD_MESSAGES.EMPTY_FILE;
  if (file.size > BILL_MAX_BYTES) return BILL_UPLOAD_MESSAGES.TOO_LARGE;
  if (!isBillMediaType(file.type)) return BILL_UPLOAD_MESSAGES.UNSUPPORTED_TYPE;
  return null;
}

/** Drag-and-drop, file picker or camera capture → AI analysis with copyable scripts. */
export function BillUploader() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [step, setStep] = useState(0);
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!file || !file.type.startsWith("image/")) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    if (status.kind !== "analyzing") return;
    setStep(0);
    const t = window.setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 2500);
    return () => window.clearInterval(t);
  }, [status.kind]);

  useEffect(() => {
    if (status.kind === "done") resultRef.current?.focus();
  }, [status.kind]);

  const choose = (f: File | undefined | null) => {
    if (!f) return;
    const problem = checkFile(f);
    if (problem) {
      setFile(null);
      setStatus({ kind: "error", message: problem });
      return;
    }
    setFile(f);
    setStatus({ kind: "idle" });
  };

  const analyze = async () => {
    if (!file) return;
    setStatus({ kind: "analyzing" });
    const body = new FormData();
    body.append("file", file);
    try {
      const res = await fetch("/api/bills/analyze", { method: "POST", body });
      const data = (await res.json().catch(() => ({}))) as { analysis?: BillAnalysis; message?: string };
      if (!res.ok || !data.analysis) {
        setStatus({ kind: "error", message: data.message ?? "We couldn't analyze that bill. Please try again." });
        return;
      }
      setStatus({ kind: "done", analysis: data.analysis });
    } catch {
      setStatus({ kind: "error", message: "You appear to be offline. Check your connection and try again." });
    }
  };

  const busy = status.kind === "analyzing";

  return (
    <div className="space-y-4">
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          choose(e.dataTransfer.files[0]);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-[var(--radius-card)] border-2 border-dashed p-8 text-center transition has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent",
          dragging ? "border-accent bg-accent/5" : "border-line bg-surface hover:bg-surface-2",
          busy && "pointer-events-none opacity-60",
        )}
      >
        <input
          type="file"
          accept={BILL_ACCEPT_ATTR}
          className="sr-only"
          disabled={busy}
          onChange={(e) => {
            choose(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-accent/10 text-accent">
          <Upload size={22} aria-hidden />
        </span>
        <span className="font-semibold">Drop your bill here or browse</span>
        <span className="text-xs text-muted">PDF, PNG, JPEG or WebP · up to 10 MB</span>
      </label>

      <label
        className={cn(
          "flex cursor-pointer items-center justify-center gap-2 rounded-full bg-surface-2 px-5 py-2.5 text-sm font-semibold transition hover:bg-line has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent sm:hidden",
          busy && "pointer-events-none opacity-60",
        )}
      >
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          capture="environment"
          className="sr-only"
          disabled={busy}
          onChange={(e) => {
            choose(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <Camera size={16} aria-hidden /> Take a photo of your bill
      </label>

      {file ? (
        <div className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-3">
          {previewUrl ? (
            <img src={previewUrl} alt="" className="h-14 w-14 shrink-0 rounded-xl object-cover" />
          ) : (
            <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-surface-2">
              <FileText size={22} aria-hidden />
            </span>
          )}
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{file.name || "Photo"}</p>
            <p className="text-xs text-muted">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
          </div>
          <Button onClick={analyze} disabled={busy}>
            {busy ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : null}
            {busy ? "Analyzing" : "Analyze"}
          </Button>
        </div>
      ) : null}

      <div aria-live="polite">
        {busy ? (
          <p className="flex items-center gap-2 rounded-2xl bg-surface-2 p-3 text-sm text-muted">
            <LoaderCircle size={16} className="animate-spin" aria-hidden />
            {STEPS[step]}
          </p>
        ) : null}
        {status.kind === "error" ? (
          <p role="alert" className="rounded-2xl bg-danger/10 p-3 text-sm text-danger">
            {status.message}
          </p>
        ) : null}
      </div>

      {status.kind === "done" ? (
        <div ref={resultRef} tabIndex={-1} className="outline-none" aria-label="Bill analysis results">
          <BillAnalysisView analysis={status.analysis} />
        </div>
      ) : null}
    </div>
  );
}
