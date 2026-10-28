"""Synthetic parser controls only; never invoke Cargo or product driver."""
import importlib.util
from pathlib import Path
import unittest

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


if __name__ == '__main__':
    unittest.main()
