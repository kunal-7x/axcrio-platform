// Ad Automation — the old single-route, custom-pill-strip monolith is retired
// (V2-W5). "Ad Automation" is now its own sidebar SECTION with four real pages
// (Command & Analytics, Run a Campaign, Creative, Connections & Vault), each using
// the app-native transparent <Tabs>. /ads simply forwards to the cockpit so any
// old bookmark still resolves.

import { redirect } from "next/navigation";

export default function AdsIndexRedirect() {
    redirect("/ads/command");
}
