import { z } from "zod";
import { requireRole } from "@/lib/auth";
import { ADDONS } from "@/lib/pricing";
import { handleCredit } from "@/lib/credit/errors";
import { cancelAddon, subscribeAddon } from "@/lib/credit/service";

const AddonKey = z.enum([ADDONS.rentReporting.key, ADDONS.aiCoach.key]);

export async function POST(req: Request) {
  return handleCredit(async () => {
    const user = await requireRole("member", "worker", "admin");
    const { addon } = z.object({ addon: AddonKey }).parse(await req.json());
    return subscribeAddon(user, addon);
  });
}

/** One-tap cancel: DELETE /api/credit/addons?addon=rent_reporting */
export async function DELETE(req: Request) {
  return handleCredit(async () => {
    const user = await requireRole("member", "worker", "admin");
    const addon = AddonKey.parse(new URL(req.url).searchParams.get("addon"));
    return cancelAddon(user, addon);
  });
}
