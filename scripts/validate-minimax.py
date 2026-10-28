#!/usr/bin/env python3
"""Bounded real Cargo/libtest validation; no account or GUI traffic."""
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time

SHA = 'bd416383d971e302ed059ae7ada73fd57429ab26'
PREFIX = 'services::coding_plan::tests::'
NAMES = [
    'minimax_general_two_tiers_from_remaining_percent',
    'minimax_skips_video_and_finds_general_in_any_position',
    'minimax_missing_general_returns_empty',
    'minimax_missing_percent_fields_skips_tier',
    'minimax_negative_percent_passes_through',
    'minimax_weekly_status_3_skips_weekly_tier',
    'minimax_weekly_status_2_keeps_exhausted_weekly_tier',
]
EXPECTED = {PREFIX + n for n in NAMES}
SUMMARY = re.compile(r'^test result: ok\. 1 passed; 0 failed; 0 ignored; 0 measured; \d+ filtered out; finished in [0-9.]+s$')


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_hash(actual, expected):
    assert actual == expected, 'test binary changed'


def parse_inventory(output):
    names = [line[:-6] for line in output.splitlines() if line.endswith(': test')]
    assert len(names) == len(set(names)) and EXPECTED <= set(names), 'missing/duplicate test'
    parser_names = {n for n in names if n.startswith(PREFIX + 'minimax_')}
    parser_names.discard(PREFIX + 'minimax_cn_detects_current_and_legacy_hosts')
    assert parser_names == EXPECTED, parser_names
    return names


def parse_result(output, name):
    lines = output.splitlines()
    assert lines.count('running 1 test') == 1, 'not exactly one running test'
    assert [x for x in lines if x.startswith('test ') and ' ... ' in x] == ['test ' + name + ' ... ok'], 'wrong/ignored/duplicate case'
    summaries = [x for x in lines if x.startswith('test result:')]
    assert len(summaries) == 1 and SUMMARY.fullmatch(summaries[0]), 'not unique successful one-test summary'


def group_rss_kib(group):
    # Sample the entire dedicated process group, not just Cargo/rustc parent RSS.
    total = 0
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) != group:
                continue
            for line in (entry / 'status').read_text().splitlines():
                if line.startswith('VmRSS:'):
                    total += int(line.split()[1])
        except (FileNotFoundError, ProcessLookupError):
            continue
    return total


def run(argv, stem, seconds, cap=8 * 1024 * 1024):
    start = time.monotonic()
    size = 0
    peak_group_rss_kib = 0
    p = poller = None
    blocked = {signal.SIGTERM, signal.SIGINT}
    oldmask = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
    try:
        p = subprocess.Popen(argv, cwd=SOURCE, env=ENV, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, start_new_session=True)
        signal.pthread_sigmask(signal.SIG_SETMASK, oldmask)
        poller = selectors.DefaultSelector()
        poller.register(p.stdout, selectors.EVENT_READ)
        with open(OUT / (stem + '.log'), 'wb') as log:
            while poller.get_map() or p.poll() is None:
                if time.monotonic() - start > seconds:
                    raise RuntimeError(stem + ': timeout')
                if shutil.disk_usage(OUT).free < 2 * 1024**3:
                    raise RuntimeError(stem + ': disk budget (<2 GiB free)')
                peak_group_rss_kib = max(peak_group_rss_kib, group_rss_kib(p.pid))
                if peak_group_rss_kib > 6 * 1024**2:
                    raise RuntimeError(stem + ': sampled process-group RSS budget >6 GiB')
                if not poller.get_map():
                    time.sleep(0.2)
                for key, _ in poller.select(0.2) if poller.get_map() else []:
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        poller.unregister(key.fileobj)
                        continue
                    size += len(chunk)
                    if size > cap:
                        raise RuntimeError(stem + ': output budget exceeded')
                    log.write(chunk)
            code = p.wait(timeout=max(1, seconds - (time.monotonic() - start)))
        evidence = {'argv': argv, 'exit': code, 'seconds': time.monotonic() - start,
                    'bytes': size, 'peak_group_rss_kib': peak_group_rss_kib, 'disk_free': shutil.disk_usage(OUT).free}
        (OUT / (stem + '.json')).write_text(json.dumps(evidence, indent=2))
        if code != 0:
            raise RuntimeError(stem + ': exit ' + str(code))
        return (OUT / (stem + '.log')).read_text()
    finally:
        # Prevent repeated cancellation from interrupting bounded group cleanup.
        previous_handlers = {sig: signal.signal(sig, signal.SIG_IGN) for sig in blocked}
        signal.pthread_sigmask(signal.SIG_SETMASK, oldmask)
        try:
            if p is not None:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    (OUT / (stem + '-cleanup.json')).write_text(json.dumps({
                        'cleanup': 'uncertain: child did not reap within 10s', 'pid': p.pid}))
                    raise RuntimeError(stem + ': cleanup uncertain')
                p.stdout.close()
            if poller is not None:
                poller.close()
        finally:
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)


def interrupted(signum, _frame):
    raise RuntimeError('driver interrupted by signal ' + str(signum))


def validate():
    global FIXTURE_CREATED
    control_sha = os.environ['GITHUB_SHA']
    assert re.fullmatch(r'[0-9a-f]{40}', control_sha), 'invalid control SHA'
    control_checkout = Path(__file__).resolve().parent.parent
    actual_control = run(['git', '-C', str(control_checkout), 'rev-parse', 'HEAD'], 'control-head', 10).strip()
    assert actual_control == control_sha, 'control checkout does not match GITHUB_SHA'
    head = run(['git', 'rev-parse', 'HEAD'], 'head', 10).strip()
    assert head == SHA, (head, SHA)
    assert not run(['git', 'status', '--porcelain', '--untracked-files=all', '--ignored'], 'clean-before', 10).strip()
    ENV['HOME'] = str(OUT / 'home')
    ENV['CARGO_HOME'] = str(OUT / 'cargo-home')
    ENV['CARGO_TARGET_DIR'] = str(OUT / 'target')
    ENV['CC_SWITCH_TEST_HOME'] = str(OUT / 'test-home')
    ENV['XDG_CACHE_HOME'] = str(OUT / 'cache')
    ENV['XDG_CONFIG_HOME'] = str(OUT / 'config')
    for name in ['home', 'cargo-home', 'test-home', 'cache', 'config']:
        (OUT / name).mkdir()
    # Empty frontend output is documented for backend-only builds, not UI validation.
    assert not (SOURCE / 'dist').exists(), 'pre-existing frontend dist not permitted'
    (SOURCE / 'dist').mkdir()
    FIXTURE_CREATED = True
    assert not any((SOURCE / 'dist').iterdir())
    run([CARGO, 'fmt', '--check', '--manifest-path', 'src-tauri/Cargo.toml'], 'fmt', 120)
    output = run([CARGO, 'test', '--locked', '--manifest-path', 'src-tauri/Cargo.toml',
                  '--lib', '--no-run', '--message-format=json'], 'compile', 2400, 64*1024*1024)
    artifacts = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue  # Cargo progress goes to stderr, merged into the bounded log.
        if (item.get('reason') == 'compiler-artifact' and item.get('profile', {}).get('test')
                and item.get('executable') and
                Path(item['target']['src_path']).resolve() == SOURCE / 'src-tauri/src/lib.rs'):
            artifacts.append(Path(item['executable']).resolve())
    assert len(artifacts) == 1, artifacts
    binary = artifacts[0]
    assert binary.is_relative_to((OUT / 'target').resolve()) and binary.is_file()
    binary_hash = digest(binary)
    inventory = run([str(binary), '--list', '--format', 'terse'], 'inventory', 60)
    names = parse_inventory(inventory)
    for i, name in enumerate(sorted(EXPECTED)):
        verify_hash(digest(binary), binary_hash)
        result = run([str(binary), name, '--exact', '--test-threads=1', '--format', 'pretty',
                      '--color', 'never'], 'test-' + str(i), 60)
        parse_result(result, name)
    verify_hash(digest(binary), binary_hash)
    assert not run(['git', 'diff', '--exit-code', 'HEAD', '--'], 'source-unchanged', 10).strip()
    assert not any((SOURCE / 'dist').iterdir()), 'compile fixture acquired unexpected content'
    (SOURCE / 'dist').rmdir()  # Only an empty directory created by this driver is removed.
    FIXTURE_CREATED = False
    assert not run(['git', 'status', '--porcelain', '--untracked-files=all', '--ignored'], 'clean-after', 10).strip()
    (OUT / 'receipt.json').write_text(json.dumps({'control_sha': control_sha, 'source_sha': SHA, 'binary': str(binary),
        'binary_sha256': binary_hash, 'tests': sorted(EXPECTED), 'inventory_count': len(names),
        'frontend_fixture': 'empty dist directory for Tauri compile context, removed; NO frontend build or UI validation',
        'scope': 'full-dependency Rust lib build; seven synthetic-input parser tests; not GUI/native UI/API'}, indent=2))
    print('Verified exact source and single compiled binary; 7 parser tests passed.')


if __name__ == '__main__':
    SOURCE = Path(sys.argv[1]).resolve()
    OUT = Path(sys.argv[2]).resolve()
    OUT.mkdir(parents=True, exist_ok=False)
    CARGO = os.path.abspath(shutil.which('cargo'))
    RUSTUP_HOME = os.environ.get('RUSTUP_HOME', str(Path.home() / '.rustup'))
    ENV = dict(os.environ, RUSTUP_HOME=RUSTUP_HOME, CARGO_BUILD_JOBS='2', CARGO_PROFILE_DEV_DEBUG='0',
               CARGO_PROFILE_TEST_DEBUG='0', CARGO_INCREMENTAL='0', RUST_BACKTRACE='0')
    FIXTURE_CREATED = False
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        validate()
    except BaseException as exc:
        (OUT / 'failure.json').write_text(json.dumps({'error': str(exc), 'type': type(exc).__name__,
            'classification': 'unclassified validation failure; NOT product RED',
            'control_sha': os.environ.get('GITHUB_SHA'), 'source_sha': SHA, 'rust_regressions_passed': False}))
        raise
    finally:
        if FIXTURE_CREATED:
            try:
                (SOURCE / 'dist').rmdir()
            except OSError as cleanup_error:
                (OUT / 'fixture-cleanup.json').write_text(json.dumps({
                    'cleanup': 'uncertain; refused to remove nonempty/changed dist',
                    'error': str(cleanup_error)}))
