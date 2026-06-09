# App icons & launch assets

`icon.png` is a **1024×1024 placeholder** — a clay (`#C96442`) rounded square with
a serif "C", matching the CONNECT screen's brand mark. It exists so the project
builds and runs with a real-looking icon today.

## Generating the full icon set (follow-up)

Capacitor does not generate iOS icons on its own. The standard path is the
`@capacitor/assets` tool, which expands a single source image into every required
`AppIcon.appiconset` size and the launch-screen images:

```bash
# from ios-app/, after `npx cap add ios`
npm i -D @capacitor/assets
npx capacitor-assets generate --ios \
  --iconBackgroundColor '#C96442' \
  --splashBackgroundColor '#FAF9F5'
```

That reads `resources/icon.png` (and an optional `resources/splash.png`) and
writes the sized assets into `ios/App/App/Assets.xcassets`.

## Final icon — owner's design pass (Jon)

This placeholder is intentionally simple. The shipping icon should align with the
**Ed mascot / MacxLabs brand** (see `docs/ed-mascot.png` in the repo root) and be
designed deliberately, not auto-rendered. Replacing `icon.png` with the final
1024×1024 artwork and re-running the generate step above is all that's needed.
