# 3. No direct DOB filing; consider a pre-filled filing summary instead

## Status

Proposed — for team discussion. (Filed as an ADR-backed PR because GitHub Issues are disabled on this repository.)

## Context

A proposal was raised for Riser to **submit CAT1/CAT5 elevator inspection filings to the city on behalf of property managers**. On investigation, "filing on behalf of the manager" does not describe a gap in Riser's actual workflow, for two independent reasons.

**Legal — the property manager was never the filer.** CAT1/CAT5 elevator test reports (forms **ELV3 / ELV29**) must be filed by the **DOB-licensed elevator inspection agency** that performed the test; a licensed director/co-director signs and submits. Property managers *hire* the agency — they do not file. There is therefore no manual manager-filing step in the real-world process for Riser to automate away.

**Technical — there is nothing to integrate with.** DOB NOW: Safety, which handles these filings, has **no public submission API**. It is a login-and-click web portal requiring an NYC.ID account. The only "integrations" seen in the wild are RPA bots driving the browser UI on someone's behalf — itself evidence that no real programmatic interface exists. Even in a hypothetical where Riser became a licensed elevator agency, a human or bot would still have to operate the portal under that agency's own credentials.

## Decision

Riser will **not** attempt to submit filings to the DOB, now or as a planned feature. Doing so would (a) automate a step the manager never performs, (b) have no API to integrate against, and (c) pull a single-tenant, no-auth MVP into **regulated professional liability** — a scope jump inconsistent with [ADR 0002](0002-no-auth-for-mvp.md).

The likely underlying need is smaller and is **in scope**: **auto-generate a pre-filled filing summary / PDF** from data Riser already holds — device identifier, inspection type (CAT1/CAT5), last inspection date, computed due date — which the manager hands to their own licensed agency so the agency does not have to re-key the data. This composes naturally with the existing due-date/status engine and the reminder feature.

## Consequences

- "Riser files with the city" is explicitly **out of scope**; if formally requested it should be closed as won't-do with a pointer to this ADR.
- The pre-filled-summary feature is **not yet scoped or committed** — open questions for the team: PDF vs. structured export; exact field set; per-elevator vs. per-building batch; whether it lands in the current MVP window or later.
- The legal/technical domain facts above (ELV3/ELV29, licensed-agency filing, the DOB NOW portal, absence of a public API) were provided by the team and are **not independent legal advice** — confirm with someone versed in the DOB process before relying on this ADR for a compliance decision.
- If the DOB ever ships a real submission API, or Riser's regulatory posture changes materially, this ADR should be revisited and superseded.
