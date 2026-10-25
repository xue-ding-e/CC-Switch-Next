#!/usr/bin/env bash
set -euo pipefail

# Invoke only in the workflow's empty, synthetic environment, never in a real profile.
test "$#" -eq 3
source_dir=$1
patch_dir=$2
rustup_bin=$3
test "$HOME" = "$CC_SWITCH_TEST_HOME"
test "$HOME" = "${TMPDIR%/tmp}/home"
test "$CARGO_BUILD_JOBS" = 2
test "$CI" = true
cd "$source_dir"

base=1729263841a78d4c1d6f21874f6b01448abf7683
agy=src-tauri/src/session_manager/providers/agy.rs
native=src-tauri/src/session_manager/providers/agy/native.rs
test_name=session_manager::providers::agy::native::tests::empty_export_retains_native_listing_metadata_and_order

check_sha() {
  printf '%s  %s\n' "$1" "$2" | sha256sum --check --strict -
}
check_source() {
  check_sha "$1" "$agy"
  check_sha "$2" "$native"
  test "$(git hash-object src-tauri/Cargo.lock)" = ecef0d202ec60b5945ca38931e4b27eca4acb282
  test "$(git hash-object src-tauri/Cargo.toml)" = aa6b1efb77dd85f00d1ba80f6ee31d4b9db581ff
  test "$(git hash-object rust-toolchain.toml)" = e396bd01690fcb59ad044ce62c2a355fe3a089dd
  test "$(git hash-object src-tauri/build.rs)" = 7aaeff600e3713d7f0cdab65aa80deb0c8ff642c
}
check_changed_paths() {
  test "$(git diff --name-only | LC_ALL=C sort)" = "$(printf '%s\n' "$agy" "$native" | LC_ALL=C sort)"
}

test "$(git rev-parse HEAD)" = "$base"
test -z "$(git status --porcelain --untracked-files=all)"
test -f LICENSE
check_source c1c41b5aeb4c237b2ea38cc6436b2a0977c8c3c951b541bf890b5d61d914c72b db7b12c69c98e1eeeb3823a30e579b15e6a04bc863018fa72a93ee35b5695b39
check_sha 7fd95015b57c8cf9e6e729072995337b00239d5d43a1731c0b6f7ad6b612c7f4 "$patch_dir/fix.patch"
check_sha 8bde279382b977eb6ec8cdc9636d14344f521e8724f0470fea9003f78c81af4d "$patch_dir/regression.patch"
test "$(sed -nE 's/^channel *= *"([^"]+)".*/\1/p' rust-toolchain.toml)" = 1.95

# Pin the exact 1.95.0 release within the source's requested 1.95 family.
timeout --kill-after=15s 240s "$rustup_bin" toolchain install 1.95.0 --profile minimal --component rustfmt
cargo_bin=$("$rustup_bin" which --toolchain 1.95.0 cargo)
export PATH="$(dirname "$cargo_bin"):$PATH"
rustc --version --verbose
test "$(rustc --version --verbose | sed -n 's/^release: //p')" = 1.95.0
cargo --version
rustfmt --version

# Keep upstream source and its original Cargo graph. No frontend build or packaging.
mkdir -p dist
git apply --check "$patch_dir/regression.patch"
git apply "$patch_dir/regression.patch"
check_source c1c41b5aeb4c237b2ea38cc6436b2a0977c8c3c951b541bf890b5d61d914c72b 06b5ff524dc4ae185e282ec35a81f8056f02103f3c8f48fa8c37c23c8487ce61
test "$(git diff --name-only)" = "$native"

# A successful original-library build is mandatory before accepting any RED result.
timeout --kill-after=30s 1200s cargo test --locked --manifest-path src-tauri/Cargo.toml --package cc-switch --lib --no-run
export CARGO_NET_OFFLINE=true
cargo test --locked --manifest-path src-tauri/Cargo.toml --package cc-switch --lib "$test_name" -- --list > "$TMPDIR/red-tests.list"
cat "$TMPDIR/red-tests.list"
grep -Fx "$test_name: test" "$TMPDIR/red-tests.list"

if timeout --kill-after=10s 90s cargo test --locked --manifest-path src-tauri/Cargo.toml --package cc-switch --lib "$test_name" -- --exact --test-threads=1 > "$TMPDIR/red.log" 2>&1; then
  red_status=0
else
  red_status=$?
fi
cat "$TMPDIR/red.log"
test "$red_status" -eq 101
grep -Fx "test $test_name ... FAILED" "$TMPDIR/red.log"
grep -F 'assertion `left == right` failed' "$TMPDIR/red.log"
grep -F 'left: None' "$TMPDIR/red.log"
grep -F 'right: Some("newer native request")' "$TMPDIR/red.log"
grep -F 'test result: FAILED. 0 passed; 1 failed;' "$TMPDIR/red.log"

# The complete native module (including the regression) must stay byte-identical.
check_source c1c41b5aeb4c237b2ea38cc6436b2a0977c8c3c951b541bf890b5d61d914c72b 06b5ff524dc4ae185e282ec35a81f8056f02103f3c8f48fa8c37c23c8487ce61
git apply --check "$patch_dir/fix.patch"
git apply "$patch_dir/fix.patch"
check_source 4fd04b62f01f1f22dc0d2d87357a8d87646dcb5fb8e2e20b5c083559554134cf 06b5ff524dc4ae185e282ec35a81f8056f02103f3c8f48fa8c37c23c8487ce61
check_changed_paths

cargo test --locked --manifest-path src-tauri/Cargo.toml --package cc-switch --lib session_manager::providers::agy:: -- --list > "$TMPDIR/green-tests.list"
cat "$TMPDIR/green-tests.list"
tests=(
  "$test_name"
  session_manager::providers::agy::native::tests::export_and_summary_metadata_keep_precedence_over_native
  session_manager::providers::agy::native::tests::empty_export_without_readable_native_keeps_existing_identity
  session_manager::providers::agy::tests::reader_step_probe_preserves_read_errors
  session_manager::providers::agy::native::tests::native_scan_and_empty_transcript_fallback
  session_manager::providers::agy::native::tests::unindexed_activity_uses_latest_valid_metadata_not_first_or_last_index
  session_manager::providers::agy::native::boundary_tests::native_reads_committed_wal_and_invalidates_both_source_kinds
  session_manager::providers::agy::native::boundary_tests::sql_source_rejects_foreign_database_and_session_id
  session_manager::providers::agy::tests::agy_discovery_does_not_follow_transcripts_outside_its_root
)
for test_name in "${tests[@]}"; do
  grep -Fx "$test_name: test" "$TMPDIR/green-tests.list"
done

# Default libtest exclusion leaves the real-data local_native_databases test ignored.
# Do not use --ignored, --include-ignored, nextest, or a full-backend test sweep here.
timeout --kill-after=20s 420s cargo test --locked --manifest-path src-tauri/Cargo.toml --package cc-switch --lib session_manager::providers::agy:: -- --test-threads=1
check_source 4fd04b62f01f1f22dc0d2d87357a8d87646dcb5fb8e2e20b5c083559554134cf 06b5ff524dc4ae185e282ec35a81f8056f02103f3c8f48fa8c37c23c8487ce61
check_changed_paths
printf '%s\n' 'FUNCTIONAL_RED_GREEN_CONTROLS=PASS'

# Check formatting separately after functional verification, without rewriting any source.
# Report inherited and candidate failures independently; neither is a formatting pass.
format_base="$TMPDIR/format-baseline"
mkdir -p "$format_base/$(dirname "$native")"
git show "$base:$agy" > "$format_base/$agy"
git show "$base:$native" > "$format_base/$native"
check_sha c1c41b5aeb4c237b2ea38cc6436b2a0977c8c3c951b541bf890b5d61d914c72b "$format_base/$agy"
check_sha db7b12c69c98e1eeeb3823a30e579b15e6a04bc863018fa72a93ee35b5695b39 "$format_base/$native"
if timeout --kill-after=10s 60s rustfmt --check --edition 2021 --config skip_children=true "$format_base/$agy" "$format_base/$native" > "$TMPDIR/format-baseline.log" 2>&1; then
  baseline_format_status=0
else
  baseline_format_status=$?
fi
if timeout --kill-after=10s 60s rustfmt --check --edition 2021 --config skip_children=true "$agy" "$native" > "$TMPDIR/format-candidate.log" 2>&1; then
  candidate_format_status=0
else
  candidate_format_status=$?
fi
printf '\n%s\n' '--- Exact baseline formatting output ---'
cat "$TMPDIR/format-baseline.log"
printf '\n%s\n' '--- Revised candidate formatting output ---'
cat "$TMPDIR/format-candidate.log"
printf 'FORMATTING_BASELINE_EXIT=%s\nFORMATTING_CANDIDATE_EXIT=%s\n' "$baseline_format_status" "$candidate_format_status"
check_source 4fd04b62f01f1f22dc0d2d87357a8d87646dcb5fb8e2e20b5c083559554134cf 06b5ff524dc4ae185e282ec35a81f8056f02103f3c8f48fa8c37c23c8487ce61
check_changed_paths
if test "$baseline_format_status" -ne 0 || test "$candidate_format_status" -ne 0; then
  printf '%s\n' 'FORMATTING=FAIL: preserve the functional evidence above; public readiness remains blocked until formatting is reconciled.'
  exit 1
fi
printf '%s\n' 'FORMATTING=PASS: both exact baseline and candidate checks succeeded.'
