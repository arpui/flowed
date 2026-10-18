// Cross-profile guard (docs/ENCARREC-P4-FLASH-INICI.md §4). No imports: the test loads it under node as well.

/** A tab still open on another profile (the portal cookie moved on) must not reach this one: the page sends
 *  X-Flowed-Profile (or ?profile= for the SSE stream, which cannot set headers). Anything else is served as before. */
export function profileMismatch(req: Request, profile: string): Response | null {
  const claimed = req.headers.get("x-flowed-profile") ?? new URL(req.url).searchParams.get("profile");
  if (claimed === null || claimed === profile) return null;
  return new Response(JSON.stringify({ error: "profile_mismatch" }), { status: 409, headers: { "content-type": "application/json" } });
}
