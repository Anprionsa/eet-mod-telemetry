# Install Report Schema (v1)

## InstallReport

| Field | Type | Description |
|-------|------|-------------|
| `schema` | `1` | Schema version |
| `id` | `string` | UUIDv4 report identifier |
| `timestamp` | `string` | ISO 8601 timestamp |
| `os` | `"windows" \| "linux" \| "macos"` | Operating system |
| `weiduVersion` | `string` | WeiDU version (e.g. "250") |
| `runnerVersion` | `string` | Infinity Mod Runner version |
| `forgeDataDate` | `string` | Forge data snapshot date |
| `presetId` | `string \| null` | Forge preset used, if any |
| `totalMods` | `number` | Unique mods in the install |
| `totalComponents` | `number` | Total components attempted |
| `components` | `ComponentOutcome[]` | Per-component results |
| `durationSeconds` | `number` | Total install wall clock time |
| `engineLimits` | `object \| null` | Final kit/splstate counts |

## ComponentOutcome

| Field | Type | Description |
|-------|------|-------------|
| `modId` | `number` | Forge mod ID (-1 if unmatched) |
| `ci` | `number` | Component index in Forge's co[] array (-1 if unmatched) |
| `cn` | `number` | WeiDU component number |
| `tp2` | `string` | tp2 folder name (e.g. "stratagems") |
| `outcome` | `"ok" \| "err" \| "skip" \| "crash"` | Install outcome |
| `errorPattern` | `string \| null` | Matched known issue pattern |

---

# Install Trace Schema (v1)

Separate event stream from install reports. Install Traces capture per-component wall-clock duration so we can build ETA baselines (see the Runner's Phase 7 plan). Issues carrying a schema-1 `install_trace` JSON block are aggregated by `scripts/aggregate_traces.py` into `data/install-traces-aggregate.json`.

## InstallTrace

| Field | Type | Description |
|-------|------|-------------|
| `schema` | `1` | Schema version |
| `event` | `"install_trace"` | Event type discriminator |
| `id` | `string` | UUIDv4 trace identifier |
| `timestamp` | `string` | ISO 8601 timestamp |
| `rig` | `RigProfile` | Anonymized hardware bucket |
| `accelerators` | `AcceleratorProfile` | Accelerator state during install |
| `runnerVersion` | `string` | Infinity Mod Runner version |
| `weiduVersion` | `string` | WeiDU version |
| `totalComponents` | `number` | Components attempted |
| `totalDurationSec` | `number` | Total install wall clock time |
| `completed` | `boolean` | True if install ran to completion without abort/errors |
| `entries` | `InstallTraceEntry[]` | Per-component timing records |

## RigProfile

| Field | Type | Description |
|-------|------|-------------|
| `os` | `"windows" \| "linux" \| "macos"` | Operating system |
| `cpuClass` | `"desktop" \| "laptop" \| "unknown"` | Heuristic from `hardwareConcurrency` |
| `diskType` | `"nvme" \| "ssd" \| "hdd" \| "unknown"` | Currently always `"unknown"` (not detectable from webview) |
| `ramGbBucket` | `number` | `deviceMemory` rounded to 4GB (max 8 reported by browser) |

## AcceleratorProfile

Matches the `accelerators` shape in Forge's `data/accelerator-profile-ref.json`. The aggregator divides each entry's `sec` by the discount coefficient for this profile to recover the reference-rig-equivalent duration before pooling samples.

| Field | Type | Description |
|-------|------|-------------|
| `overrideFastDrive` | `boolean` | `override/` junctioned to a faster volume |
| `experimentalWeidu` | `boolean` | Bundled patched WeiDU binary in use |
| `batchSize` | `number` | Runner's `max_batch_size` (default 25) |

## InstallTraceEntry

| Field | Type | Description |
|-------|------|-------------|
| `mod` | `string` | Lowercase tp2 folder name |
| `cn` | `number` | WeiDU component number |
| `sec` | `number` | Wall-clock seconds for this component on the submitting user's rig |
| `status` | `"success" \| "warning" \| "error" \| "skipped" \| "already"` | Install outcome |

## Aggregate output (`data/install-traces-aggregate.json`)

Produced by the weekly workflow. Consumed by Forge's `scripts/apply_trace_aggregate.js` to patch per-mod `installProfile` fields in `eet-mod-forge/data/mods/*.json`.

| Field | Type | Description |
|-------|------|-------------|
| `schema` | `1` | Schema version |
| `updatedAt` | `string` | ISO timestamp of the run that wrote this file |
| `totalSamples` | `number` | How many `(mod, cn)` samples this run added |
| `entriesPublished` | `number` | Entries that met the `minSamplesToPublish` gate |
| `entriesBelowGate` | `number` | Entries collected but withheld pending more samples |
| `minSamplesToPublish` | `number` | Confidence gate before an entry is published (default 3) |
| `entries` | `{ [modCn: string]: AggregateEntry }` | Map keyed `"<mod_lower>:<cn>"` |

## AggregateEntry

| Field | Type | Description |
|-------|------|-------------|
| `baselineSec` | `number` | P50 seconds across normalized samples (rounded to 1 decimal) |
| `heavyClass` | `"light" \| "medium" \| "heavy"` | Derived from `baselineSec` |
| `sampleCount` | `number` | Cumulative samples backing this entry |
| `updatedAt` | `string` | YYYY-MM-DD of the most recent update |

---

# Community Build Schema

Community builds are stored as one file per build in `data/builds/<id>.json`, plus a lightweight `data/builds/_index.json` listing all builds (everything except the `keys` array) for fast browsing.

## CommunityBuild

| Field | Type | Description |
|-------|------|-------------|
| `schema` | `1` | Container schema version |
| `schemaVersion` | `1 \| 2` | Key format: 1 = idx-based (legacy, volatile on mod updates), 2 = wc-based (stable). New builds should be 2. |
| `id` | `string` | Unique build identifier (UUID for first submission; reuse the same id to publish updates) |
| `version` | `string` | Semver-ish (e.g. `"1.0.0"`, `"1.2.0"`). Aggregator picks highest version when multiple approved issues share an id. |
| `name` | `string` | Display name |
| `desc` | `string` | Description |
| `author` | `string` | Display author name |
| `authorGitHub` | `string` | GitHub username of the original author. Aggregator rejects updates from mismatched GitHub users. |
| `icon` | `string` | Emoji or icon text |
| `color` | `string` | Hex color for UI accent |
| `keys` | `string[]` | Component selection. Format is `"modId-wc"` for schemaVersion 2. |
| `tier` | `number \| null` | Difficulty tier (1=Beginner, 2=Intermediate, 3=Expert) |
| `difficulty` | `string \| null` | Free-text difficulty label |
| `focus` | `string[]` | Focus tags (e.g. `["story", "npc", "qol"]`) |
| `modCount` | `number` | Unique mods in the build |
| `componentCount` | `number` | Total components (== `keys.length`) |
| `forgeVersion` | `string` | Forge app version at publish time |
| `createdAt` | `string` | ISO timestamp of first submission |
| `updatedAt` | `string` | ISO timestamp of most recent update |
| `issueNumber` | `number` | GitHub issue number that produced this build |
| `recommendedInstaller` | `string \| null` | Optional. Key of an installer defined in the Forge's `config.json` `installers` map (e.g. `"runner"`). Signals that cross-mod conflicts shown in the Forge are resolved by that installer's patch system. UI will surface a notice on the build card, detail modal, and conflict panel. |
| `installNotes` | `string` | Optional free-text note shown in the detail modal (e.g. install caveats, known gotchas). |

## Labels

- `community-build` (auto, from issue template)
- `approved` (required for aggregation)
- `yanked` (removes a previously-approved version from the published index)

## Update / ownership rules

When multiple approved issues share an `id`, the aggregator picks the one with the highest `version` (tiebreak: newest `updatedAt`, then newest `createdAt`). Updates are only accepted if the new submission's `authorGitHub` matches the existing build's — preventing build-id hijacking.
