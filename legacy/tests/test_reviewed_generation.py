from copy import deepcopy
import unittest

import test_evidence_consistency as fixtures
from quality.integration import QualityBlocked
from quality.reviewed_generation import generate_reviewed


class ReviewedGeneration(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.EvidenceConsistency()
        self.f.setUp()

    def test_corrects_missing_evidence_then_final_guard_sends_once(self):
        feedback = []
        def writer(previous):
            feedback.append(previous)
            return dict(message=deepcopy(self.f.message), review=self.f.review(claims=['invented'] if previous is None else ['c1']))
        candidate = generate_reviewed(writer, self.f.guard)
        self.f.fake.send_message.assert_not_called()
        self.assertFalse(feedback[1]['passed'])
        self.f.guard.send_message(candidate['message'], review=candidate['review'])
        self.assertEqual(self.f.fake.send_message.call_count, 1)

    def test_exhaustion_is_bounded_and_never_sends(self):
        attempts = []
        with self.assertRaises(QualityBlocked):
            generate_reviewed(lambda previous: {}, self.f.guard, max_attempts=2, audit=attempts.append)
        self.assertEqual(len(attempts), 2)
        self.f.fake.send_message.assert_not_called()

    def test_model_failure_propagates_and_cannot_be_called_success(self):
        def writer(previous):
            raise TimeoutError('Synthetic model overload')
        with self.assertRaises(TimeoutError): generate_reviewed(writer, self.f.guard)
        self.f.fake.send_message.assert_not_called()
