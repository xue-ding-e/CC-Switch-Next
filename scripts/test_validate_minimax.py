"""Synthetic parser controls only; never invoke Cargo or product driver."""
import importlib.util
from pathlib import Path
import unittest
import tempfile
import os

spec = importlib.util.spec_from_file_location('control', Path(__file__).with_name('validate-minimax.py'))
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class Gates(unittest.TestCase):
    def setUp(self):
        self.name = sorted(control.EXPECTED)[0]
        self.good = ('running 1 test\ntest ' + self.name + ' ... ok\n'
                     'test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 100 filtered out; finished in 0.00s\n')
        self.inventory = '\n'.join(n + ': test' for n in sorted(control.EXPECTED))

    def test_positive(self):
        control.parse_result(self.good, self.name)
        self.assertEqual(len(control.parse_inventory(self.inventory)), 7)
        control.verify_hash('a' * 64, 'a' * 64)

    def test_missing_case(self):
        with self.assertRaises(AssertionError):
            control.parse_inventory('\n'.join(self.inventory.splitlines()[1:]))

    def test_ignored_is_not_pass(self):
        with self.assertRaises(AssertionError):
            control.parse_result(self.good.replace(' ... ok', ' ... ignored'), self.name)

    def test_empty_match(self):
        with self.assertRaises(AssertionError):
            control.parse_result('running 0 tests\ntest result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 100 filtered out; finished in 0.00s', self.name)

    def test_duplicate_summary(self):
        with self.assertRaises(AssertionError):
            control.parse_result(self.good + self.good.splitlines()[-1], self.name)

    def test_wrong_hash(self):
        with self.assertRaises(AssertionError):
            control.verify_hash('a' * 64, 'b' * 64)

    def test_wrong_case(self):
        with self.assertRaises(AssertionError):
            control.parse_result(self.good.replace(self.name, 'other::test'), self.name)

    def test_duplicate_inventory(self):
        with self.assertRaises(AssertionError):
            control.parse_inventory(self.inventory + '\n' + self.name + ': test')

    def test_missing_summary(self):
        with self.assertRaises(AssertionError):
            control.parse_result('\n'.join(self.good.splitlines()[:-1]), self.name)

    def test_exact_generated_schema_allowlist(self):
        status = '\n'.join('!! ' + n for n in sorted(control.GENERATED_SCHEMAS))
        self.assertEqual(set(control.generated_schema_paths(status)), control.GENERATED_SCHEMAS)

    def test_extra_ignored_is_rejected(self):
        status = '\n'.join('!! ' + n for n in sorted(control.GENERATED_SCHEMAS))
        with self.assertRaises(AssertionError):
            control.generated_schema_paths(status + '\n!! unexpected.json')

    def test_tracked_schema_change_is_rejected(self):
        status = '\n'.join('!! ' + n for n in sorted(control.GENERATED_SCHEMAS))
        with self.assertRaises(AssertionError):
            control.generated_schema_paths(status.replace('!! ', ' M ', 1))

    def test_missing_schema_is_rejected(self):
        with self.assertRaises(AssertionError):
            control.generated_schema_paths('')

    def schema_fixture(self, source):
        for name in control.GENERATED_SCHEMAS:
            p = source / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('{}')
        return '\n'.join('!! ' + n for n in sorted(control.GENERATED_SCHEMAS))

    def test_schema_cleanup_positive(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            source = Path(tmp).resolve()
            created = control.schema_preflight(source)
            status = self.schema_fixture(source)
            records = control.clean_generated_schemas(source, status)
            self.assertEqual(len(records), 4)
            for d in created:
                d.rmdir()
            self.assertEqual(list(source.iterdir()), [])

    def test_preexisting_schema_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            source = Path(tmp).resolve()
            self.schema_fixture(source)
            with self.assertRaises(AssertionError):
                control.schema_preflight(source)

    def test_dangling_schema_symlink_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            source = Path(tmp).resolve()
            p = source / sorted(control.GENERATED_SCHEMAS)[0]
            p.parent.mkdir(parents=True)
            p.symlink_to('absent')
            with self.assertRaises(AssertionError):
                control.schema_preflight(source)

    def test_schema_parent_symlink_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            source = Path(tmp).resolve()
            (source / 'src-tauri').symlink_to('absent-dir')
            with self.assertRaises(AssertionError):
                control.schema_preflight(source)

    def test_invalid_json_rejected_without_removal(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            source = Path(tmp).resolve()
            status = self.schema_fixture(source)
            (source / sorted(control.GENERATED_SCHEMAS)[-1]).write_text('{bad')
            with self.assertRaises(ValueError):
                control.clean_generated_schemas(source, status)
            self.assertTrue(all((source / n).exists() for n in control.GENERATED_SCHEMAS))

    def test_oversized_schema_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            source = Path(tmp).resolve()
            status = self.schema_fixture(source)
            with open(source / sorted(control.GENERATED_SCHEMAS)[0], 'wb') as f:
                f.truncate(10 * 1024 * 1024 + 1)
            with self.assertRaises(AssertionError):
                control.clean_generated_schemas(source, status)


if __name__ == '__main__':
    unittest.main()
