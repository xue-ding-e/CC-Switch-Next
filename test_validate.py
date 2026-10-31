"""Offline parser fixtures only. Never starts Cargo or a socket."""
import unittest
from validate import parse_result

NAME = 'proxy::tests::exact'
RED = {'location': 'src/test.rs:42:', 'markers': ['assertion failed: missing', 'EXPECTED_404']}
GOOD = f'running 1 test\ntest {NAME} ... ok\ntest result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 9 filtered out; finished in 0.01s\n'
BAD = f"running 1 test\nthread '{NAME}' panicked at src/test.rs:42:9:\nassertion failed: missing\nEXPECTED_404\ntest {NAME} ... FAILED\ntest result: FAILED. 0 passed; 1 failed; 0 ignored; 0 measured; 9 filtered out; finished in 0.01s\n"


class ParserTests(unittest.TestCase):
    def test_accept_green(self):
        parse_result(GOOD, NAME)

    def test_accept_exact_assertion_red(self):
        parse_result(BAD, NAME, RED)

    def test_reject_zero_tests(self):
        with self.assertRaises(AssertionError):
            parse_result(GOOD.replace('running 1 test', 'running 0 tests'), NAME)

    def test_reject_ignored(self):
        with self.assertRaises(AssertionError):
            parse_result(GOOD.replace(' ... ok', ' ... ignored'), NAME)

    def test_reject_wrong_panic_location(self):
        with self.assertRaises(AssertionError):
            parse_result(BAD.replace(':42:', ':43:'), NAME, RED)

    def test_reject_missing_expected_rejection(self):
        with self.assertRaises(AssertionError):
            parse_result(BAD.replace('EXPECTED_404', ''), NAME, RED)

    def test_reject_socket_setup_failure(self):
        with self.assertRaises(AssertionError):
            parse_result(BAD + 'Permission denied', NAME, RED)

    def test_reject_compile_failure(self):
        with self.assertRaises(AssertionError):
            parse_result('error[E0063]: missing fields', NAME, RED)

    def test_reject_multiple_panics(self):
        with self.assertRaises(AssertionError):
            parse_result(BAD + 'panicked at setup', NAME, RED)

    def test_reject_duplicate_identity(self):
        with self.assertRaises(AssertionError):
            parse_result(GOOD + f'test {NAME} ... ok\n', NAME)


if __name__ == '__main__':
    unittest.main()
