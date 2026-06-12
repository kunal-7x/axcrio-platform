# Signal Aurora — generation loader uplift (frontend-only)

GOAL: replace the cheap grey-dots-on-black loader with a premium fluid "Signal Aurora"
window — WebGL domain-warped noise aurora (Signal blue) behind flow-coupled sparks,
glow + grain, framer-motion chrome. Drop-in: same GenerationLoader public API. Reused by
TemplatesStep, BannerStep, GenerationQueue automatically.

## Plan / progress  — ALL DONE
- [DONE] read field.ts, index.tsx, gl-* CSS, consumers, package.json (framer-motion@12.5 present, no 3D lib)
- [DONE] add components/GenerationLoader/aurora.ts  (raw WebGL fragment shader, no dep)
- [DONE] couple field.ts sparks to aurora luminance + brand tint (additive bright sparks)
- [DONE] rewire index.tsx: aurora layer under sparks, intensity uniform from phase, framer-motion status crossfade, dispose-on-unmount
- [DONE] globals.css: aurora/grain/vignette CSS + gradient-mesh reduced-motion fallback + brand tint/palette tokens
- [DONE] npx tsc --noEmit  -> EXIT 0
- [DONE] npm run build  -> EXIT 0 (no errors/warnings)
- [DONE] commit on feat/premium-ui

## Contract preserved (do NOT break)
props: state/title/label/phase/statusLines/progress/intensity/lowPower/mode/errorMessage/onRetry/onCancel/onCompleted/className
consumers: app/whatsapp/_steps/TemplatesStep.tsx, BannerStep.tsx, app/creative/_components/GenerationQueue.tsx — NO change needed

## Tokens (token-pure, resolved via getComputedStyle)
--primary-01 #2a85ff (Signal blue) · shades 01-10 · gl-card defines --gl-dot/--gl-dot-soft
NEW aurora palette tokens added to .gl-card: --gl-aur-a/b/c (deep indigo-black -> signal blue -> cool white)
