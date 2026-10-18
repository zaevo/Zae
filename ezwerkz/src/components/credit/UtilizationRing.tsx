import { cn } from "@/components/ui/cn";

/**
 * Circular meter for credit utilization, drawn for the gradient hero card.
 * The track is a lighter step of the same (white) ramp; the fill shifts to
 * warning/danger as utilization rises, and the label says it in words too.
 */
export function UtilizationRing({ value, size = 92 }: { value: number; size?: number }) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
  const stroke = 8;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const level = pct <= 30 ? "low" : pct <= 70 ? "moderate" : "high";
  const fill = level === "low" ? "stroke-white" : level === "moderate" ? "stroke-warning" : "stroke-danger";
  return (
    <div
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      aria-valuetext={`${pct}% of your limit used (${level})`}
      aria-label="Credit utilization"
      className="relative shrink-0"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} className="stroke-white/25" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - Math.max(pct, pct > 0 ? 2 : 0) / 100)}
          className={cn(fill, "transition-[stroke-dashoffset] duration-700")}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center leading-none">
        <span className="text-lg font-bold">{pct}%</span>
        <span className="mt-1 text-[10px] font-medium uppercase tracking-wider text-white/75">used</span>
      </div>
    </div>
  );
}
