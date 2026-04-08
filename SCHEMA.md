# Install Report Schema (v1)

## InstallReport

| Field | Type | Description |
|-------|------|-------------|
| `schema` | `1` | Schema version |
| `id` | `string` | UUIDv4 report identifier |
| `timestamp` | `string` | ISO 8601 timestamp |
| `os` | `"windows" \| "linux" \| "macos"` | Operating system |
| `weiduVersion` | `string` | WeiDU version (e.g. "250") |
| `runnerVersion` | `string` | EET Mod Runner version |
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
