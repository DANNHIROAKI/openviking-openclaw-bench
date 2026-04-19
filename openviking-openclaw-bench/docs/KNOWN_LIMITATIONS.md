# Known limitations

1. `ovbench setup-group` assumes the OpenClaw CLI installed under `openclaw.prefix` places the package root under either:
   - `<prefix>/lib/node_modules/openclaw`
   - `<prefix>/node_modules/openclaw`

2. The LanceDB fix is best-effort. It follows the currently reported workaround pattern: add a minimal `dist/package.json` if needed, then run `npm install @lancedb/lancedb` inside the extension directory.

3. `ovbench` captures OpenClaw logs on a best-effort basis with `openclaw logs`. If your build exposes logs differently, you may want to copy your gateway logs manually into the run directory.

4. The repository does not vendor the OpenViking plugin snapshot. You still need a local plugin directory, usually from your `openclaw-openviking-doubao` checkout.
