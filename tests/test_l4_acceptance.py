"""Acceptance distinguishes a complete evidence handoff from interrupted work."""
import unittest
from tools import validate_l4_business


class L4AcceptanceTests(unittest.TestCase):
    def finished(self, row):
        return validate_l4_business.execution_finished(row)

    def test_full_validated_handoff_is_finished_execution(self):
        row = dict(state='needs-human', reason='request_human_review', observations=[
            dict(reference=reference, validated=True) for reference in ('object-001', 'object-002', 'entry')])
        self.assertTrue(self.finished(row))

    def test_incomplete_handoff_is_not_finished(self):
        row = dict(state='needs-human', reason='request_human_review', observations=[
            dict(reference='object-001', validated=True)])
        self.assertFalse(self.finished(row))

    def test_unvalidated_or_resource_blocked_is_not_finished(self):
        observations = [dict(reference=reference, validated=True) for reference in ('object-001', 'object-002', 'entry')]
        self.assertFalse(self.finished(dict(state='needs-human', reason='resource_limit', observations=observations)))
        observations[2]['validated'] = False
        self.assertFalse(self.finished(dict(state='completed', observations=observations)))


if __name__ == '__main__': unittest.main()
