# Sources

This integration repository packages:

- OpenViking official OpenClaw plugin snapshot from `volcengine/OpenViking` `v0.3.8` (`examples/openclaw-plugin/`)
- Local-mode installation helpers authored for this repository
- Doubao/Volcengine `ov.conf` templates for OpenViking local mode

Notes:

- OpenClaw core is **not vendored in full** here. The default path in this repository installs OpenClaw from the npm stable channel, pinned to `2026.4.14` for reproducibility.
- The GitHub source release observed while preparing this package was OpenClaw `2026.4.14`.
- This package is designed for **Doubao API + Local Mode**.
