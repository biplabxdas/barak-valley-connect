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
        self.assertTrue(any("fan" in reason for reason in matches[0]["reasons"]))

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

    def test_recommendations_explain_category_skills_location_and_availability(self):
        providers = [
            {"id": 1, "name": "Tarapur Electrical", "category": "Electrical", "area": "Tarapur",
             "description": "Electrical wiring for ceiling fans", "skills": "fan repair, wiring",
             "availability": "Busy"},
            {"id": 2, "name": "Silchar Electrical", "category": "Electrical", "area": "Silchar",
             "description": "Electrical wiring for ceiling fans", "skills": "fan repair, wiring",
             "availability": "Available"},
            {"id": 3, "name": "Tarapur Electric Demo", "category": "Electrical", "area": "Tarapur",
             "description": "Electrical wiring for ceiling fans", "skills": "fan repair, wiring",
             "availability": "Available"},
        ]
        matches = rank_providers("Please fix a fan wiring issue in Tarapur", providers)
        self.assertEqual(matches[0]["id"], 3)
        self.assertEqual(matches[0]["feature_scores"]["location"], 1.0)
        self.assertEqual(matches[1]["id"], 1)
        self.assertGreater(matches[0]["feature_scores"]["availability"], matches[1]["feature_scores"]["availability"])
        self.assertTrue(any("Category" in reason for reason in matches[0]["reasons"]))
        self.assertTrue(any("Skills" in reason for reason in matches[0]["reasons"]))
        self.assertTrue(any("Tarapur" in reason for reason in matches[0]["reasons"]))

    def test_urgent_requirement_prefers_listed_available_provider(self):
        providers = [
            {"id": 1, "name": "Busy Electrical", "category": "Electrical", "area": "Silchar",
             "description": "Fan wiring and electrical repair", "skills": "fan repair, wiring", "availability": "Busy"},
            {"id": 2, "name": "Available Electrical", "category": "Electrical", "area": "Silchar",
             "description": "Fan wiring and electrical repair", "skills": "fan repair, wiring", "availability": "Available"},
        ]
        matches = rank_providers("Urgent fan wiring repair in Silchar today", providers)
        self.assertEqual(matches[0]["id"], 2)
        self.assertTrue(any("available" in reason.lower() for reason in matches[0]["reasons"]))


if __name__ == "__main__":
    unittest.main()
