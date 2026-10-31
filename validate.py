#!/usr/bin/env python3
"""Reviewed Linux Cargo/libtest driver. No work executes on import."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_result(text, name, red=None):
    assert text.splitlines().count('running 1 test') == 1, 'test count mismatch'
    state = 'FAILED' if red else 'ok'
    identities = [line for line in text.splitlines() if line.startswith('test ') and ' ... ' in line]
    assert identities == [f'test {name} ... {state}'], 'wrong/duplicate test identity/status'
    summaries = [s for s in text.splitlines() if s.startswith('test result:')]
    pattern = (r'test result: FAILED\. 0 passed; 1 failed; 0 ignored; 0 measured; \d+ filtered out; finished in [0-9.]+s'
               if red else r'test result: ok\. 1 passed; 0 failed; 0 ignored; 0 measured; \d+ filtered out; finished in [0-9.]+s')
    assert len(summaries) == 1 and re.fullmatch(pattern, summaries[0]), 'not exact one-test result'
    if red:
        assert text.count('panicked at ') == 1, 'multiple/setup panic'
        assert red['location'] in text, 'wrong assertion location'
        assert all(marker in text for marker in red['markers']), 'wrong assertion diagnostic'
        for forbidden in ['Address already in use', 'Permission denied', 'Connection refused',
                          'failed to bind', 'failed to lookup address', 'error[E', 'HTTP 502']:
            assert forbidden not in text, 'environment/fixture error is not RED'


def group_rss(group):
    total = 0
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            if int((p / 'stat').read_text().rsplit(')', 1)[1].split()[2]) == group:
                for line in (p / 'status').read_text().splitlines():
                    if line.startswith('VmRSS:'):
                        total += int(line.split()[1])
        except (FileNotFoundError, ProcessLookupError):
            pass
    return total


def main():
    control, source, out = map(lambda s: Path(s).resolve(), sys.argv[1:4])
    plan = json.loads((control / 'plan.json').read_text())
    hashes = json.loads((control / 'file-hashes.json').read_text())
    signatures = json.loads((control / 'red-signatures.json').read_text())
    assert set(signatures) == set(plan['expectedRedFailures']) and len(signatures) == 7
    assert len(plan['controlPassBoth']) == 10
    assert plan['reviewedSourceSHA'] == plan['candidate']['commitSha'], 'unbound candidate SHA'
    candidate = Path(os.environ['CANDIDATE_DIR']).resolve()
    def candidate_git(*args):
        return subprocess.check_output(['git', '-C', str(candidate), *args], text=True).strip()
    assert candidate_git('rev-parse', 'HEAD') == plan['reviewedSourceSHA']
    assert candidate_git('rev-parse', 'HEAD^{tree}') == plan['candidate']['treeSha']
    assert candidate_git('status', '--porcelain') == '', 'dirty candidate checkout'
    assert set(candidate_git('diff', '--name-only', plan['baseline']['sha'], 'HEAD').splitlines()) == set(hashes)
    for file, values in hashes.items():
        assert digest(candidate / file) == values['green'], 'candidate file mismatch'
    assert digest(candidate / 'src-tauri/Cargo.lock') == plan['baseline']['cargoLockSha256']
    assert digest(candidate / 'pnpm-lock.yaml') == plan['baseline']['pnpmLockSha256']
    assert re.fullmatch('[0-9a-f]{40}', os.environ.get('EXPECTED_CONTROL_SHA', '')), 'control SHA missing'
    assert subprocess.check_output(['git', '-C', str(control), 'rev-parse', 'HEAD'], text=True).strip() == os.environ['EXPECTED_CONTROL_SHA']
    assert subprocess.check_output(['git', '-C', str(control), 'status', '--porcelain'], text=True) == '', 'dirty control checkout'
    assert not out.exists(), 'evidence output must be new'
    out.mkdir(parents=True)
    env = os.environ.copy()
    # Keep HOME and toolchain homes unchanged; tests use the repository-supported isolation.
    env.update(CC_SWITCH_TEST_HOME=str(out / 'test-home'), XDG_CONFIG_HOME=str(out / 'xdg'),
               CARGO_BUILD_JOBS='2', CARGO_PROFILE_DEV_DEBUG='0', CARGO_PROFILE_TEST_DEBUG='0',
               CARGO_TARGET_DIR=str(out / 'target'), RUSTUP_TOOLCHAIN='1.95', CARGO_TERM_COLOR='never',
               RUST_BACKTRACE='0')
    records = []
    deadline = time.monotonic() + 65 * 60

    def run(argv, label, seconds):
        log = out / (label + '.log')
        start = time.monotonic()
        proc = None
        code = None
        peak_rss = 0
        try:
            with log.open('wb') as f:
                proc = subprocess.Popen(argv, cwd=source, env=env, stdout=f, stderr=subprocess.STDOUT,
                                        start_new_session=True)
                while proc.poll() is None:
                    assert time.monotonic() < min(deadline, start + seconds), 'budget_exceeded: timeout'
                    assert log.stat().st_size <= 8 * 1024**2, 'budget_exceeded: output'
                    assert shutil.disk_usage(out).free >= 2 * 1024**3, 'budget_exceeded: disk'
                    peak_rss = max(peak_rss, group_rss(proc.pid))
                    assert peak_rss <= 6 * 1024**2, 'budget_exceeded: sampled RSS'
                    time.sleep(.2)
                code = proc.returncode
            assert log.stat().st_size <= 8 * 1024**2, 'budget_exceeded: final output'
            return code, log.read_text(errors='replace')
        finally:
            failure = sys.exc_info()[1]
            cleanup_error = None
            previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in [signal.SIGTERM, signal.SIGINT]}
            try:
                if proc is not None:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait(timeout=10)
                    code = proc.returncode
            except BaseException as error:
                cleanup_error = str(error)
                raise
            finally:
                receipt = dict(label=label, argv=argv, exit=code, seconds=time.monotonic()-start,
                               sha256=digest(log) if log.exists() else None,
                               bytes=log.stat().st_size if log.exists() else 0,
                               error=str(failure) if failure else None,
                               cleanup_error=cleanup_error, peak_group_rss_kib=peak_rss)
                records.append(receipt)
                (out / (label+'-receipt.json')).write_text(json.dumps(receipt,indent=2))
                (out / 'processes.json').write_text(json.dumps(records, indent=2))
                for sig, handler in previous.items():
                    signal.signal(sig, handler)

    def must(argv, label, seconds=60):
        code, text = run(argv, label, seconds)
        assert code == 0, f'{label}: nonzero exit {code}; not expected RED'
        return text

    def locks():
        assert digest(source / 'src-tauri/Cargo.lock') == plan['baseline']['cargoLockSha256']
        assert digest(source / 'pnpm-lock.yaml') == plan['baseline']['pnpmLockSha256']

    def phase_hashes(phase):
        for file, values in hashes.items():
            assert digest(source / file) == values[phase], f'{phase} hash mismatch: {file}'
        locks()

    def compile_phase(phase):
        text = must(['cargo', 'test', '--locked', '--manifest-path', 'src-tauri/Cargo.toml',
                     '--lib', '--no-run', '--message-format=json'], phase+'-compile', 28*60)
        binaries = set()
        for line in text.splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get('reason') == 'compiler-artifact' and row.get('profile', {}).get('test') and row.get('executable'):
                binaries.add(row['executable'])
        assert len(binaries) == 1, 'compile_failure: ambiguous lib test binary'
        binary = Path(binaries.pop()).resolve()
        assert binary.is_relative_to(out / 'target') and binary.is_file(), 'unexpected executable'
        sha = digest(binary)
        inventory = must([str(binary), '--list'], phase+'-inventory')
        names = [line[:-6] for line in inventory.splitlines() if line.endswith(': test')]
        assert len(names) == len(set(names)), 'duplicate inventory'
        tests = plan['expectedRedFailures'] + plan['controlPassBoth']
        assert len(tests) == 17 and len(set(tests)) == 17 and set(tests) <= set(names), 'missing tests'
        (out / (phase+'-binary.json')).write_text(json.dumps(dict(path=str(binary),sha256=sha,tests=tests),indent=2))
        for index, name in enumerate(tests):
            assert digest(binary) == sha, 'test executable changed'
            code, text = run([str(binary), '--exact', name, '--test-threads=1'],
                             f'{phase}-{index:02}', 60)
            red = signatures[name] if phase == 'red' and name in signatures else None
            assert code == (101 if red else 0), 'wrong libtest exit; not an expected assertion'
            parse_result(text, name, red)
        phase_hashes(phase)

    try:
        assert shutil.disk_usage(out).free >= 10 * 1024**3, 'environment_blocked: disk preflight'
        assert int(re.search(r'MemTotal:\s+(\d+)', Path('/proc/meminfo').read_text())[1]) >= 8*1024**2, 'environment_blocked: memory'
        assert must(['git','rev-parse','HEAD'],'base-sha').strip() == plan['baseline']['sha']
        assert must(['git','rev-parse','HEAD^{tree}'],'base-tree').strip() == plan['baseline']['tree']
        assert must(['git','status','--porcelain'],'clean') == '', 'dirty baseline'
        phase_hashes('base')
        for key in ['red', 'green']:
            assert digest(control / plan['patches'][key]) == plan['patches'][key+'Sha256']
        assert 'rustc 1.95.' in must(['rustc','--version'],'rustc-version')
        must(['rustfmt','--version'],'rustfmt-version')
        (source / 'dist').mkdir(exist_ok=True)
        (out / 'test-home').mkdir()
        for phase in ['red','green']:
            patch = str(control / plan['patches'][phase])
            must(['git','apply','--check',patch],phase+'-apply-check')
            must(['git','apply',patch],phase+'-apply')
            phase_hashes(phase)
            compile_phase(phase)
        # Format only a disposable full tracked-source copy; never repair the candidate silently.
        fmt = out / 'fmt-source'
        fmt.mkdir()
        tracked = must(['git','ls-files','-z'],'tracked-files').split('\0')
        for relative in filter(None, tracked):
            src = source / relative
            assert not src.is_symlink(), 'symlink requires explicit review'
            dst = fmt / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src,dst)
        code, _ = run(['cargo','fmt','--check','--manifest-path',str(fmt/'src-tauri/Cargo.toml')], 'fmt-check', 60)
        if code:
            must(['cargo','fmt','--manifest-path',str(fmt/'src-tauri/Cargo.toml')], 'fmt-proposal', 60)
            import difflib
            proposal = ''
            for relative in filter(None, tracked):
                if not relative.endswith('.rs'):
                    continue
                a,b = (source/relative).read_text(),(fmt/relative).read_text()
                if a != b:
                    proposal += ''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile='a/'+relative,tofile='b/'+relative))
            (out/'fmt-proposal.patch').write_text(proposal)
            raise AssertionError('needs_format_review: actual rustfmt proposal retained')
        phase_hashes('green')
        changed = set(must(['git','diff','--name-only'],'final-paths').splitlines())
        assert changed == set(hashes), 'unexpected tracked changes'
        must(['git','status','--porcelain','--untracked-files=all','--ignored'], 'final-generated-files')
        (out/'result.json').write_text(json.dumps(dict(status='qualified',red_failures=7,red_controls=10,green_pass=17)))
    except BaseException as error:
        (out/'result.json').write_text(json.dumps(dict(status='not_qualified',error=str(error),type=type(error).__name__)))
        raise


if __name__ == '__main__':
    def cancelled(signum, frame):
        raise RuntimeError(f'cancelled: signal {signum}')
    signal.signal(signal.SIGTERM, cancelled)
    main()
