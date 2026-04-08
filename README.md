# EET Mod Telemetry

Crowdsourced install data for [EET Mod Forge](https://github.com/Anprionsa/eet-mod-forge) and [EET Mod Runner](https://github.com/Anprionsa/eet-mod-runner).

## What This Repo Does

This repository collects **anonymized install reports** from EET Mod Runner and Forge users. A weekly GitHub Action aggregates reports into static JSON files that Forge uses to display community-sourced compatibility data.

## Privacy

Install reports contain **no identifying information**:
- No file paths
- No usernames or system details
- No mod file contents
- Only: OS type, WeiDU version, mod IDs, component numbers, and outcomes (ok/err/skip/crash)

Every report is submitted as a GitHub Issue — you can see exactly what's shared before submitting.

## How It Works

1. **EET Mod Runner** generates an install report after each install
2. User clicks "Share Report on GitHub" — opens a pre-filled GitHub Issue
3. User reviews the data and clicks Submit
4. A weekly GitHub Action aggregates all reports into `data/aggregate.json`
5. EET Mod Forge fetches this data to show stability indicators and community-reported issues

## Community Builds

Users can also submit mod builds (selection lists) via GitHub Issues labeled `community-build`. These are reviewed and approved by the maintainer before appearing in Forge's Community tab.

## Data Files

| File | Description |
|------|-------------|
| `data/aggregate.json` | Aggregated telemetry from install reports |
| `data/builds.json` | Approved community builds |

## Report Schema

See [SCHEMA.md](SCHEMA.md) for the full install report schema (v1).

## Contributing

The best way to contribute is to use EET Mod Runner and opt in to sharing install reports. Every report helps improve mod compatibility data for the entire community.
