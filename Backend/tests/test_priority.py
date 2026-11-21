import unittest

from Backend.core.priority_engine import calculate_priority


class PriorityTests(unittest.TestCase):
    def test_score_and_label_thresholds(self):
        cases = (
            ((0, 0, 0, 0), (0, "Low")),
            ((2, 2, 0, 0), (28, "Low")),
            ((3, 1, 0, 0), (30, "Medium")),
            ((3, 3, 1, 2), (49, "Medium")),
            ((4, 3, 0, 0), (50, "High")),
            ((4, 4, 4, 1), (70, "Critical")),
        )
        for factors, expected in cases:
            with self.subTest(factors=factors):
                self.assertEqual(calculate_priority(*factors), expected)

    def test_maximum_impact_requires_confirmed_evidence_for_critical_score(self):
        self.assertEqual(calculate_priority(5, 5, 5, 4), (69, "High"))
        self.assertEqual(
            calculate_priority(5, 5, 5, 4, evidence_status="confirmed"),
            (93, "Critical"),
        )

    def test_age_bonus_increases_every_four_hours_up_to_five_points(self):
        for age, expected in ((0, 0), (3.99, 0), (4, 1), (19.99, 4), (20, 5), (100, 5)):
            with self.subTest(age=age):
                self.assertEqual(calculate_priority(0, 0, 0, 0, age_hours=age), (expected, "Low"))
        self.assertEqual(calculate_priority(5, 5, 5, 5, 100, "confirmed"), (100, "Critical"))

    def test_invalid_factors_are_rejected(self):
        for field in ("impact", "urgency", "affected_scope", "sla_risk"):
            for value in (-1, 6, 3.0, "3", True):
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, field):
                    factors = dict(impact=0, urgency=0, affected_scope=0, sla_risk=0)
                    factors[field] = value
                    calculate_priority(**factors)

    def test_invalid_age_and_evidence_are_rejected(self):
        for age in (-0.1, float("inf"), float("nan"), "4", True):
            with self.subTest(age=age), self.assertRaisesRegex(ValueError, "age_hours"):
                calculate_priority(0, 0, 0, 0, age_hours=age)
        for evidence in ("", " ", None):
            with self.subTest(evidence=evidence), self.assertRaisesRegex(ValueError, "evidence_status"):
                calculate_priority(0, 0, 0, 0, evidence_status=evidence)
