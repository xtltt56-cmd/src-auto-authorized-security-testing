import unittest

from src_auto.scope import ScopeGuard, ScopePolicy


class BusinessLogicTests(unittest.TestCase):
    def _guard(self):
        return ScopeGuard(
            ScopePolicy.from_mapping(
                {
                    "target_id": "local-business-api",
                    "allowed_hosts": ["127.0.0.1"],
                    "allowed_ports": [8083],
                    "confirmed": True,
                    "allow_network_contact": True,
                }
            )
        )

    def test_requests_default_to_read_only_and_mutations_need_all_safety_gates(self):
        from src_auto.business_logic import BusinessLogicError, RequestTemplate, validate_request

        read = RequestTemplate("get-order", "GET", "http://127.0.0.1:8083/orders/order-a")
        self.assertEqual(validate_request(read, self._guard()).method, "GET")

        write = RequestTemplate("update-order", "PATCH", "http://127.0.0.1:8083/orders/order-a", body={"note": "test"})
        with self.assertRaisesRegex(BusinessLogicError, "mutation_not_approved"):
            validate_request(write, self._guard())
        with self.assertRaisesRegex(BusinessLogicError, "synthetic_object_required"):
            validate_request(write, self._guard(), allow_mutation=True, manual_confirmed=True)
        approved = validate_request(
            write,
            self._guard(),
            allow_mutation=True,
            manual_confirmed=True,
            synthetic_object=True,
        )
        self.assertEqual(approved.method, "PATCH")

        destructive = RequestTemplate("delete-order", "DELETE", "http://127.0.0.1:8083/orders/order-a")
        with self.assertRaisesRegex(BusinessLogicError, "destructive_method_blocked"):
            validate_request(
                destructive,
                self._guard(),
                allow_mutation=True,
                manual_confirmed=True,
                synthetic_object=True,
            )

    def test_response_comparison_flags_candidate_but_never_confirms_idor(self):
        from src_auto.business_logic import ResponseSnapshot, compare_authorization_responses

        owner = ResponseSnapshot(200, {"Content-Type": "application/json"}, {"id": "order-a", "owner": "buyer-a", "amount": 10, "updated_at": "one"})
        peer = ResponseSnapshot(200, {"Content-Type": "application/json"}, {"id": "order-a", "owner": "buyer-a", "amount": 10, "updated_at": "two"})
        anonymous = ResponseSnapshot(401, {}, {"error": "login required"})

        result = compare_authorization_responses(owner, peer, anonymous, volatile_fields={"updated_at"})

        self.assertEqual(result["disposition"], "candidate_broken_object_authorization")
        self.assertTrue(result["owner_peer_equivalent"])
        self.assertFalse(result["confirmed"])
        self.assertEqual(result["next_action"], "manual_review")
        self.assertNotIn("amount", str(result))
        self.assertNotIn("buyer-a", str(result))

    def test_denied_peer_response_is_recorded_as_enforced(self):
        from src_auto.business_logic import ResponseSnapshot, compare_authorization_responses

        owner = ResponseSnapshot(200, {}, {"id": "order-a"})
        peer = ResponseSnapshot(403, {}, {"error": "forbidden"})
        anonymous = ResponseSnapshot(401, {}, {"error": "login"})
        result = compare_authorization_responses(owner, peer, anonymous)
        self.assertEqual(result["disposition"], "authorization_enforced")
        self.assertFalse(result["confirmed"])

    def test_api_object_diff_reports_paths_without_secret_values(self):
        from src_auto.business_logic import compare_api_objects

        before = {"id": "1", "profile": {"name": "Alice", "token": "secret-a", "level": 1}}
        after = {"id": "1", "profile": {"name": "Alice", "token": "secret-b", "level": 2}, "admin": False}
        result = compare_api_objects(before, after, volatile_fields={"token"})
        self.assertEqual(result["added_paths"], ["$.admin"])
        self.assertEqual(result["changed_paths"], ["$.profile.level"])
        self.assertNotIn("secret-a", str(result))
        self.assertNotIn("secret-b", str(result))

    def test_matrix_keeps_each_case_separate_and_requires_manual_review(self):
        from src_auto.business_logic import AuthorizationCase, ResponseSnapshot, evaluate_authorization_matrix

        cases = [
            AuthorizationCase(
                name="read-own-order",
                expected_roles=("buyer",),
                owner=ResponseSnapshot(200, {}, {"id": "order-a"}),
                peer=ResponseSnapshot(200, {}, {"id": "order-a"}),
                anonymous=ResponseSnapshot(401, {}, {}),
            ),
            AuthorizationCase(
                name="admin-summary",
                expected_roles=("admin",),
                owner=ResponseSnapshot(200, {}, {"count": 1}),
                peer=ResponseSnapshot(403, {}, {}),
                anonymous=ResponseSnapshot(401, {}, {}),
            ),
        ]
        report = evaluate_authorization_matrix(cases)
        self.assertEqual(report["summary"]["candidate"], 1)
        self.assertEqual(report["summary"]["enforced"], 1)
        self.assertTrue(report["manual_review_required"])
        self.assertEqual([item["name"] for item in report["cases"]], ["read-own-order", "admin-summary"])


if __name__ == "__main__":
    unittest.main()
