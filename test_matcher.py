"""Small offline checks for the request-to-provider ranking."""

import unittest

from matcher import cosine_similarity, rank_providers


SAMPLE_PROVIDERS = [
    {"id": 1, "name": "QuickFix Electricals", "category": "Electrical", "area": "Silchar"},
    {"id": 2, "name": "Riya's Home Repair", "category": "Home repair", "area": "Silchar"},
    {"id": 3, "name": "Green Leaf Garden Care", "category": "Gardening", "area": "Silchar"},
]


class RecommendationTests(unittest.TestCase):
    def test_cosine_similarity_known_vectors_and_empty_vectors(self):
        self.assertAlmostEqual(cosine_similarity({"fan": 1, "repair": 1}, {"fan": 1, "repair": 1}), 1.0)
        self.assertEqual(cosine_similarity({"fan": 1}, {"water": 1}), 0.0)
        self.assertEqual(cosine_similarity({}, {"fan": 1}), 0.0)

    def test_everyday_electrical_request_ranks_electrician_first(self):
        matches = rank_providers("My ceiling fan stopped working", SAMPLE_PROVIDERS)
        self.assertEqual(matches[0]["id"], 1)
        self.assertIn("fan", matches[0]["reasons"])

    def test_garden_request_ranks_gardener_first(self):
        matches = rank_providers("Please trim the lawn and garden", SAMPLE_PROVIDERS)
        self.assertEqual(matches[0]["id"], 3)

    def test_unrelated_request_returns_no_suggestion(self):
        self.assertEqual(rank_providers("I need astrophysics tutoring", SAMPLE_PROVIDERS), [])

    def test_empty_directory_returns_no_suggestions(self):
        self.assertEqual(rank_providers("Fix a fan", []), [])

    def test_results_are_limited(self):
        matches = rank_providers("repair garden fan home", SAMPLE_PROVIDERS, limit=2)
        self.assertLessEqual(len(matches), 2)


if __name__ == "__main__":
    unittest.main()
