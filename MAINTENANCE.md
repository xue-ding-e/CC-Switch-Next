# Independent maintenance

- Upstream: https://github.com/farion1231/cc-switch
- Recorded upstream commit: `5de6feb4e5adda61f4ad824ce0df2c449245f447`
- Linear baseline commit: `1724cdf470d6dfa5abea782cd8c21b5c17ed67b5`
- `upstream-main` preserves the original upstream commit graph and authorship.
- `main` reconstructs the functional commit sequence without merge commits. Original author/committer identities, dates and messages are retained with an `Original-Commit` trailer. Rewritten commit signatures are not represented as original signatures; inspect `upstream-main` for the original objects.
- [Commit mapping](docs/upstream-history-map.tsv) records source commits, rewritten commits and integration records. Redundant merges map to the existing linear tip. Mainline integration commits retain the original upstream integration tree. Internal merge integrations apply a parent-relative difference conservatively: the unique original parent already ancestral to the most recent mainline boundary is preferred, otherwise the first parent is used. They are not claimed to be pure conflict-resolution changes.
- The linear baseline tree is identical to the recorded upstream tree. Every original first-parent boundary was checked for tree equality.
- Existing licenses, copyright notices and third-party notices remain authoritative. No upstream author is replaced or claimed as the independent maintainer.
- Historical contribution forks and experimental branches are not automatically incorporated.

## Automation and releases

Original workflow files are retained as documentation under `docs/upstream-workflows/` with `.txt` suffixes; GitHub does not load them as workflows. Active workflows perform structural history/JSON validation and cloud validation of the frontend and Rust backend. Cloud validation runs on `main` pushes, pull requests targeting `main`, the dedicated validation branch, and manual dispatch. It uses read-only repository permissions and does not publish releases or artifacts. Backend CI follows upstream cargo-nextest process isolation; this does not replace native desktop UI or release-channel validation.

No upstream tags, releases, secrets, signing keys, R2 storage configuration or publishing credentials are copied. This repository has not published independent binaries. Product identifiers, updater endpoints and release provenance require a separate review before building or distributing independent packages. Existing upstream development and test instructions still apply.

## Subsequent upstream maintenance

### Pending candidate: read-title range overflow

- Base: `66c2f2351ac43e0d7bdb93f2ceafeac188e00329`. Candidate only; not integrated into `main`.
- Adapted only the saturating arithmetic in `title_read` from Railgun-wiki's upstream commit [`1d470f86217e510776f9d2c83c37f193ef59d5fb`](https://github.com/farion1231/cc-switch/commit/1d470f86217e510776f9d2c83c37f193ef59d5fb). MIT attribution is unchanged; this is not an original discovery or an AGY feature import.
- Added synthetic regression cases to the existing `blocks.rs` test module for large ranges and the JSON numeric/string parameter entry points. No real sessions or credentials are required.
- **TODO — tests not run:** on an existing supported Rust/Tauri environment, run `cargo test --lib session_manager::providers::blocks::tests::` from `src-tauri/`. Establish RED with the added tests and the baseline arithmetic, then GREEN with the saturated arithmetic, including debug and release profiles. Run `cargo fmt --check` and the applicable backend suite before integration.
- Current evidence is source/call-path review and patch consistency only, not runtime reproduction, CI success, desktop validation, release, or deployment. No new validation framework or release workflow is introduced.

The recorded linear baseline above remains the initialization snapshot. Later upstream fixes are applied as focused, linear cherry-picks rather than merging the original upstream graph into `main`.

- Upstream `797e0276ffc20e54cbdf55e3de84505d77231c91` (`fix(proxy): preserve Claude JSON session identity (#8236)`) is imported as `452f15173` with original authorship and the `cherry-pick -x` provenance trailer. The two changed Rust files match that upstream commit exactly. Its five new regression tests are exercised explicitly before the full upstream-isolated backend suite. This fixes Claude / Claude Desktop JSON session identity handling; it does not change the earlier cache-test concurrency investigation or desktop/release acceptance gaps.
