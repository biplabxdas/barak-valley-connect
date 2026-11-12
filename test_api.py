"""API integration checks against an isolated, temporary SQLite database."""

import os
import csv
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "api-test.db")
os.environ["ADMIN_PASSWORD"] = "test-owner-password"
os.environ["SESSION_SECRET"] = "test-session-secret-for-local-checks"

from fastapi.testclient import TestClient
import main


REALISTIC_QUERY_CASES = [
    ("fan not working", 1), ("fix broken switch", 1), ("light wiring issue", 1),
    ("electrician for house", 1), ("repair socket", 1), ("leaking kitchen tap", 2),
    ("water pipe leak", 2), ("blocked bathroom drain", 2), ("faucet leak", 2),
    ("pipe fitting problem", 2), ("handyman for damaged wall", 3),
    ("fix cracks in wall", 3), ("home maintenance help", 3), ("broken door repair", 3),
    ("trim grass lawn", 4), ("prune garden plants", 4),
    ("landscaping for backyard", 4), ("help with planting", 4),
    ("clean dusty house", 5), ("deep cleaning for office", 5),
    ("mop floors and clean room", 5), ("repair wooden cabinet", 6),
    ("furniture assembly and shelves", 6), ("custom woodwork door", 6),
    ("typo fan not wokring", 1), ("typo leeking pipe", 2),
    ("faucet drips", 2), ("toilet pipe issue", 2),
    ("typo wodworker needed", 6), ("wedding photographer", None),
    ("tax filing assistance", None),
]


class ApiIntegrationTests(unittest.TestCase):
    def setUp(self):
        Path(os.environ["DATABASE_PATH"]).unlink(missing_ok=True)
        self.client_context = TestClient(main.app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)

    def test_home_and_privacy_pages_load(self):
        home = self.client.get("/")
        privacy = self.client.get("/privacy")
        favicon = self.client.get("/static/favicon.svg")
        self.assertEqual(home.status_code, 200)
        self.assertIn("/static/favicon.svg", home.text)
        self.assertEqual(favicon.status_code, 200)
        self.assertIn("<svg", favicon.text)
        self.assertIn('id="match-form"', home.text)
        self.assertEqual(privacy.status_code, 200)
        self.assertIn("does not save that description", privacy.text)

    def test_production_requires_a_long_session_secret(self):
        valid_settings = {
            "APP_ENV": "production",
            "ADMIN_PASSWORD": "a-long-owner-password",
            "DATABASE_URL": "postgresql://user:pass@example.test/app",
            "SITE_OPERATOR_NAME": "Barak Valley Connect",
            "PRIVACY_CONTACT_EMAIL": "privacy@example.test",
            "REQUEST_RETENTION_DAYS": "30",
        }
        with patch.multiple(main, **valid_settings, SESSION_SECRET="s" * 31):
            with self.assertRaisesRegex(RuntimeError, "session secret of at least 32 characters"):
                main.validate_production_settings()
        with patch.multiple(main, **valid_settings, SESSION_SECRET="s" * 32):
            main.validate_production_settings()

    def test_csv_export_neutralizes_spreadsheet_formulas(self):
        created = self.client.post("/api/requests", json={
            "customer_name": "=1+1", "customer_phone": "+1234567890",
            "service_id": 1, "details": "@SUM(1,1)", "privacy_consent": True,
        })
        self.assertEqual(created.status_code, 201)
        self.client.post("/api/auth/admin-login", json={"password": "test-owner-password"})
        exported = self.client.get("/api/admin/requests.csv")
        self.assertEqual(exported.status_code, 200)
        row = next(csv.DictReader(StringIO(exported.text)))
        self.assertEqual(row["customer_name"], "'=1+1")
        self.assertEqual(row["customer_phone"], "'+1234567890")
        self.assertEqual(row["details"], "'@SUM(1,1)")
        self.assertEqual(main.spreadsheet_safe_value("  \t=2+2"), "'  \t=2+2")
        self.assertEqual(main.spreadsheet_safe_value("Ordinary request"), "Ordinary request")

    def test_public_provider_list_hides_phone_numbers(self):
        response = self.client.get("/api/providers")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 3)
        self.assertNotIn("phone", response.json()[0])
        self.assertTrue(all(provider["is_sample"] for provider in response.json()))
        categories = self.client.get("/api/categories")
        self.assertEqual({item["name"] for item in categories.json()}, {"Home repair", "Gardening", "Electrical"})
        profile = self.client.get(f"/api/providers/{response.json()[0]['id']}")
        self.assertEqual(profile.status_code, 200)
        self.assertNotIn("phone", profile.json())

    def test_recommendation_uses_seeded_database_listings(self):
        response = self.client.post(
            "/api/recommendations", json={"description": "My ceiling fan stopped working"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["matches"][0]["name"], "QuickFix Electricals")
        self.assertIn("fan", data["matches"][0]["reasons"])
        self.assertGreater(data["matches"][0]["score"], 0)
        self.assertLessEqual(data["matches"][0]["score"], 1)
        self.assertNotIn("phone", data["matches"][0])

    def test_31_realistic_queries_rank_database_providers_and_reject_unrelated_requests(self):
        provider_rows = [
            (1, "Silchar Electrical Works", "Electrical", "Household electrical repairs, wiring, lights, fans and switches", "fan installation, wiring, circuit repair"),
            (2, "Barak Plumbing Service", "Plumbing", "Repair leaking pipes, taps, drains, bathroom and kitchen fittings", "pipe repair, tap installation"),
            (3, "Riya Home Repair", "Home repair", "General household repairs, broken doors, walls, small maintenance jobs", "handyman, household fixing, repairs"),
            (4, "Green Leaf Garden Care", "Gardening", "Lawn and garden care, pruning, planting, landscaping", "grass cutting, plant care"),
            (5, "Clean Home Services", "Cleaning", "Home and office cleaning, dusting, mopping, deep clean", "house cleaning, office cleaning"),
            (6, "Silchar Woodcraft", "Carpentry", "Woodwork, furniture, doors, cabinets and shelves", "furniture repair, carpentry"),
        ]
        with main.connect_db() as db:
            db.execute("DELETE FROM service_requests")
            db.execute("DELETE FROM providers")
            for provider_id, name, category, description, skills in provider_rows:
                category_id = main.ensure_category(db, category)
                db.execute(
                    """INSERT INTO providers
                       (id, name, category, area, phone, description, skills, category_id, is_sample)
                       VALUES (?, ?, ?, 'Silchar', '9876500011', ?, ?, ?, 0)""",
                    (provider_id, name, category, description, skills, category_id),
                )

        for description, expected_id in REALISTIC_QUERY_CASES:
            with self.subTest(description=description):
                response = self.client.post("/api/recommendations", json={"description": description})
                self.assertEqual(response.status_code, 200)
                matches = response.json()["matches"]
                if expected_id is None:
                    self.assertEqual(matches, [])
                else:
                    self.assertTrue(matches)
                    self.assertEqual(matches[0]["id"], expected_id)
                    self.assertGreater(matches[0]["score"], 0)
                    self.assertLessEqual(matches[0]["score"], 1)
                    self.assertTrue(matches[0]["reasons"])
                    self.assertNotIn("phone", matches[0])

    def test_account_and_request_survive_reopening_the_application(self):
        self.client.post("/api/auth/register", json={
            "email": "persistent@example.com", "password": "persistent-customer-password",
            "role": "customer", "display_name": "Persistent Customer", "phone": "9876500081",
        })
        created = self.client.post("/api/requests", json={
            "customer_name": "unused", "customer_phone": "9999999999", "service_id": 3,
            "details": "Please repair a fan", "privacy_consent": True,
        })
        self.assertEqual(created.status_code, 201)
        self.client_context.__exit__(None, None, None)

        self.client_context = TestClient(main.app)
        self.client = self.client_context.__enter__()
        login = self.client.post("/api/auth/login", json={
            "email": "persistent@example.com", "password": "persistent-customer-password",
        })
        self.assertEqual(login.status_code, 200)
        history = self.client.get("/api/my/requests")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()[0]["provider_name"], "QuickFix Electricals")
        self.assertEqual(history.json()[0]["details"], "Please repair a fan")

    def test_unmatched_and_invalid_descriptions(self):
        unmatched = self.client.post(
            "/api/recommendations", json={"description": "I need astrophysics tutoring"}
        )
        invalid = self.client.post("/api/recommendations", json={"description": "x"})
        too_long = self.client.post("/api/recommendations", json={"description": "x" * 301})
        self.assertEqual(unmatched.status_code, 200)
        self.assertEqual(unmatched.json()["matches"], [])
        self.assertIn("couldn't find a close match", unmatched.json()["message"])
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(too_long.status_code, 422)

    def test_recommendation_endpoint_has_a_rate_limit(self):
        payload = {"description": "repair a fan"}
        for _ in range(60):
            self.assertEqual(self.client.post("/api/recommendations", json=payload).status_code, 200)
        limited = self.client.post("/api/recommendations", json=payload)
        self.assertEqual(limited.status_code, 429)

    def test_recommendation_rate_limit_is_shared_across_application_instances(self):
        payload = {"description": "repair a fan"}
        for _ in range(30):
            self.assertEqual(self.client.post("/api/recommendations", json=payload).status_code, 200)

        with TestClient(main.app) as another_instance:
            for _ in range(30):
                self.assertEqual(another_instance.post("/api/recommendations", json=payload).status_code, 200)
            self.assertEqual(another_instance.post("/api/recommendations", json=payload).status_code, 429)

    def test_existing_request_flow_still_requires_consent_and_persists(self):
        denied = self.client.post("/api/requests", json={
            "customer_name": "Test Visitor", "customer_phone": "9876500010",
            "service_id": 1, "details": "Please repair my fan", "privacy_consent": False,
        })
        accepted = self.client.post("/api/requests", json={
            "customer_name": "Test Visitor", "customer_phone": "9876500010",
            "service_id": 1, "details": "Please repair my fan", "privacy_consent": True,
        })
        self.assertEqual(denied.status_code, 400)
        self.assertEqual(accepted.status_code, 201)
        self.assertEqual(self.client.get("/api/requests").status_code, 401)
        login = self.client.post("/api/auth/admin-login", json={"password": "test-owner-password"})
        self.assertEqual(login.status_code, 200)
        requests = self.client.get("/api/requests")
        self.assertEqual(requests.status_code, 200)
        self.assertEqual(requests.json()[0]["customer_name"], "Test Visitor")
        request_id = requests.json()[0]["id"]
        updated = self.client.patch(
            f"/api/requests/{request_id}/status", json={"status": "Accepted"}
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "Accepted")

    def test_owner_provider_crud_and_category_filter(self):
        unauthorized = self.client.post("/api/providers", json={
            "name": "Valley Plumbing", "category": "Plumbing", "area": "Silchar", "phone": "9876500099",
        })
        self.assertEqual(unauthorized.status_code, 401)
        self.client.post("/api/auth/admin-login", json={"password": "test-owner-password"})
        created = self.client.post("/api/providers", json={
            "name": "Valley Plumbing", "category": "Plumbing", "area": "Silchar", "phone": "9876500099",
        })
        self.assertEqual(created.status_code, 201)
        provider_id = created.json()["id"]
        filtered = self.client.get("/api/providers?category=Plumbing")
        self.assertEqual([row["id"] for row in filtered.json()], [provider_id])
        updated = self.client.put(f"/api/providers/{provider_id}", json={
            "name": "Valley Pipe Works", "category": "Plumbing", "area": "Silchar", "phone": "9876500099",
        })
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "Valley Pipe Works")
        removed = self.client.delete(f"/api/providers/{provider_id}")
        self.assertEqual(removed.status_code, 204)

    def test_customer_registration_login_and_private_request_history(self):
        registered = self.client.post("/api/auth/register", json={
            "email": "customer@example.com", "password": "strong-customer-password",
            "role": "customer", "display_name": "Asha Das", "phone": "9876500088",
        })
        self.assertEqual(registered.status_code, 201)
        self.assertEqual(registered.json()["account"]["role"], "customer")
        self.assertNotIn("password_hash", registered.json()["account"])
        self.assertEqual(self.client.get("/api/my/requests").json(), [])
        request = self.client.post("/api/requests", json={
            "customer_name": "Ignored Guest Name", "customer_phone": "9999999999",
            "service_id": 3, "details": "Repair my ceiling fan", "privacy_consent": True,
        })
        self.assertEqual(request.status_code, 201)
        history = self.client.get("/api/my/requests")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()[0]["provider_name"], "QuickFix Electricals")
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/my/requests").status_code, 401)
        login = self.client.post("/api/auth/login", json={
            "email": "CUSTOMER@example.com", "password": "strong-customer-password",
        })
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["account"]["display_name"], "Asha Das")

    def test_provider_registration_creates_matchable_profile_and_role_scoped_access(self):
        registered = self.client.post("/api/auth/register", json={
            "email": "provider@example.com", "password": "strong-provider-password",
            "role": "provider", "display_name": "Valley Wiring Works", "phone": "9876500077",
            "category": "Electrical", "area": "Silchar", "description": "Home wiring and fan repairs",
            "skills": "fan repair, wiring, switches",
        })
        self.assertEqual(registered.status_code, 201)
        profile = self.client.get("/api/provider/profile")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["skills"], "fan repair, wiring, switches")
        service_request = self.client.post("/api/requests", json={
            "customer_name": "Test Visitor", "customer_phone": "9876500022",
            "service_id": profile.json()["id"], "details": "Please fix a ceiling fan", "privacy_consent": True,
        })
        self.assertEqual(service_request.status_code, 201)
        provider_requests = self.client.get("/api/provider/requests")
        self.assertEqual(provider_requests.status_code, 200)
        self.assertEqual(provider_requests.json()[0]["customer_name"], "Test Visitor")
        matches = self.client.post("/api/recommendations", json={"description": "Need help rewiring a ceiling fan"}).json()["matches"]
        self.assertEqual(matches[0]["name"], "Valley Wiring Works")
        self.assertEqual(self.client.get("/api/provider/requests").status_code, 200)
        self.assertEqual(self.client.get("/api/my/requests").status_code, 403)
        updated = self.client.put("/api/provider/profile", json={
            "name": "Valley Electrical Service", "category": "Electrical", "area": "Silchar",
            "phone": "9876500077", "description": "Fan and light repair", "skills": "fans, lights",
        })
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "Valley Electrical Service")
        searched = self.client.get("/api/providers?q=fan%20repair")
        self.assertEqual(searched.status_code, 200)
        self.assertIn("Valley Electrical Service", [row["name"] for row in searched.json()])

    def test_older_sqlite_database_is_migrated_without_losing_a_listing(self):
        legacy_path = Path(_TEMP_DIR.name) / "legacy.db"
        legacy_path.unlink(missing_ok=True)
        connection = sqlite3.connect(legacy_path)
        connection.executescript("""
          CREATE TABLE providers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            category TEXT NOT NULL, area TEXT NOT NULL, phone TEXT NOT NULL);
          CREATE TABLE service_requests (id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL, customer_phone TEXT NOT NULL,
            service_id INTEGER NOT NULL REFERENCES providers(id), details TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
          INSERT INTO providers (name, category, area, phone)
            VALUES ('Old Listing', 'Plumbing', 'Silchar', '9876500090');
        """)
        connection.commit()
        connection.close()

        original_path = main.DB_PATH
        main.DB_PATH = legacy_path
        try:
            with TestClient(main.app) as client:
                providers = client.get("/api/providers").json()
                self.assertEqual(providers[0]["name"], "Old Listing")
                self.assertEqual(providers[0]["category"], "Plumbing")
                self.assertFalse(providers[0]["is_sample"])
                self.assertIn("Plumbing", [item["name"] for item in client.get("/api/categories").json()])
        finally:
            main.DB_PATH = original_path


if __name__ == "__main__":
    unittest.main()
