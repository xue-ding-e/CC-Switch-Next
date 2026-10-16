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
