# DIAGNOSE-5 — Campaign Dropdown (auto-fetch) for WhatsApp builder + Creative Studio

Founder ask: stop pasting campaign details. A DROPDOWN of his campaigns that, on
select, AUTO-FETCHES that campaign's full detail and hands it to the generator
(WhatsApp template gen / Creative create-banner). One reusable component, two drops.

---

## 1. API shape (LIVE today)

### A. List — `GET /api/campaigns` → `{ campaigns: Campaign[] }`
`lib/api.ts:352 getCampaigns()`. The list record is LEAN (`lib/api.ts:26`):
```ts
type Campaign = { id, name, company, product, status, created_at }   // strings
```
Enough to populate the dropdown (label = `name`, sublabel = `product || company`,
status badge). NOT enough to drive a generator — needs the detail call below.

### B. Detail — `GET /api/assets/campaign-context?campaign_id={id}` → `CampaignContextSnapshot`
`lib/assets.ts:559 getCampaignContext(id)`. This IS the per-campaign detail endpoint
and it ALREADY EXISTS, served by the AI Asset Service (`:8310`, nginx `/api/assets/`).
Returns provenance-tagged facts (no-invent §20):
```ts
CampaignContextSnapshot = {
  campaign_id, campaign_name,
  facts: { key, label, value?, provenance }[],   // provenance: from_campaign|from_brand_kit|from_me|absent
  brand_kit_id?
}
```
Fact keys observed: business, product, offer/price, location, audience, goal, language.
It is DORMANT-SAFE: any non-200 resolves to `{ facts: [] }`, never throws.

### C. Fallback detail (no Asset Service): `contextFromCampaign(c)`
`app/whatsapp/_lib/waapi.ts:293` — pure client derivation from the lean list record
(`business=company, product=product, goal=name`). Use as the degrade path when B is
dormant so the dropdown still hands SOMETHING to the generator.

---

## 2. The reusable component — `components/CampaignSelect`

Wrap the existing premium `components/Select` (headlessui Listbox, `SelectOption`).
Self-fetches the list, owns selection, fires BOTH the lean record and the resolved
detail snapshot upward. Drop-in, dormant-safe, zero new backend.

```tsx
// components/CampaignSelect/index.tsx
type CampaignSelectProps = {
  value?: string;                                  // selected campaign id (controlled)
  onSelect: (c: Campaign, detail: CampaignContextSnapshot) => void;
  className?: string;
  autoSelectFirst?: boolean;                        // optional convenience
};
// 1. useEffect → getCampaigns() → Campaign[]  (catch → [])
// 2. map to SelectOption[] { id:i+1, name } ; remember id↔Campaign map
// 3. on Select.onChange → find Campaign → getCampaignContext(c.id)  [Promise]
//    → onSelect(c, snapshot)    (snapshot.facts=[] on dormant → caller falls back
//       to contextFromCampaign(c))
// 4. loading=Spinner in button, empty="No campaigns yet", label="Campaign"
```
Returns the SAME `<Select>` look already used in CreatePanel, so it's visually
consistent and no PageHeader/jargon rules are touched.

---

## 3. The two placements

### Placement 1 — WhatsApp builder (`app/whatsapp/_steps/CampaignStep.tsx`)
Today it's a FULL-PAGE table-select (lines 84-108) + a right-side context card.
Founder wants a DROPDOWN. Replace the `<Table>` block with `<CampaignSelect>`; on
select, set `campaign` + context via `setCampaign(c, ctxFromSnapshot(detail) ?? contextFromCampaign(c))`.
Keep the right-side "Campaign context" read-only card (it already renders the facts).
Detail then flows to `generateTemplates({ campaign_id })` in `TemplatesStep` (waapi.ts:138).

### Placement 2 — Creative Studio create-banner (`app/creative/_components/CreatePanel.tsx`)
Today the campaign `<Select>` (lines 215-226) already exists but only emits the id
via `onCampaignChange`; the detail fetch lives separately in the page's
`<CampaignContext>` panel (page.tsx:149). Swap that bare `<Select>` for
`<CampaignSelect>` so selection + detail-fetch are ONE action, and pass the
`brand_kit_id` from the snapshot into `generate({ campaign_id, brand_kit_id })`
(CreatePanel.tsx:175). The right-rail `CampaignContext` panel stays as the trust view.

---

## 4. Notes / guardrails
- NO new backend route — list + detail already LIVE. Net change is frontend-only.
- Dormant-safe everywhere: detail 404/503 → `facts:[]` → fall back to `contextFromCampaign`.
- Reuse `components/Select` + `SelectOption` (`types/select`); do NOT hand-roll a dropdown.
- Don't break the live earner: additive component, both placements degrade cleanly.
