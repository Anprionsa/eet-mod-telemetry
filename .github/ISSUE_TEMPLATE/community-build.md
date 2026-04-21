---
name: Community Build
about: Share or update a mod build with the Infinity Engine community
title: "Community Build: [Name]"
labels: community-build
---

Paste the community build JSON below (auto-filled by Infinity Mod Forge's Publish dialog):

```json

```

## Updating an existing build

To publish an update to a build you previously submitted:

1. In the Forge's Publish dialog, keep the **Build ID** field set to your existing build's id.
2. **Bump the version** (e.g., `1.0.0` → `1.1.0`).
3. Set the **GitHub username** field to the same value you used originally.
4. Submit the new issue with the updated JSON.

The aggregator will verify that the GitHub issue author matches the original build's `authorGitHub` before accepting the update. Mismatched authors are rejected to prevent build-id hijacking.

## Labels

- `community-build` (auto) — marks the issue for aggregation
- `approved` (maintainer) — required for the build to be published
- `yanked` (maintainer) — removes a previously-approved version from the published list

## Schema fields

- `id` — unique build id. New submissions get a UUID; updates reuse the existing id.
- `version` — semver-ish string; higher version wins when the same id appears in multiple approved issues.
- `authorGitHub` — required for updates; must match the GitHub issue author.
- `schemaVersion: 2` — keys are WeiDU component numbers (stable across mod updates).
- `recommendedInstaller` — optional. Set to `"runner"` to tell users that your build needs Infinity Mod Runner (e.g. because cross-mod conflicts are resolved by its patch system). The Forge displays a notice on the build card, detail modal, and conflict panel.
- `installNotes` — optional free-text note shown alongside the recommended-installer notice (e.g. install-order caveats, known gotchas).

See `SCHEMA.md` in this repo for the full field list.
