"""Authentication API integration tests.

Direct invocation targets localhost unless --target is provided. Discovery with
unittest skips these tests unless VACCINE_TEST_BASE_URL is set.
"""

import base64
import json

from test_config import (
    IntegrationTestCase,
    PASSWORD,
    require_rejection,
    require_status,
    run_module_cli,
)


class AuthenticationTests(IntegrationTestCase):
    def test_patient_and_caregiver_registration_and_login(self):
        for role in ("patient", "caregiver"):
            with self.subTest(role=role):
                username = self.name(f"auth_{role}")
                require_status(self.client.create(role, username), 200, f"create {role}")
                require_rejection(self.client.create(role, username), f"duplicate {role}")
                token = self.client.login(role, username)
                self.assertEqual(len(token.split(".")), 3, "login should return a JWT")
                require_rejection(
                    self.client.login_response(role, username, "WrongPass@1"),
                    f"login {role} with wrong password",
                )
                require_rejection(
                    self.client.login_response(role, self.name("missing"), PASSWORD),
                    f"login nonexistent {role}",
                )

    def test_weak_passwords_are_rejected(self):
        passwords = ("Ab1!", "abcdefg1!", "Abcdefg1", "Abcdefg!")
        for role in ("patient", "caregiver"):
            for index, password in enumerate(passwords):
                with self.subTest(role=role, password_case=index):
                    response = self.client.create(role, self.name(f"weak{index}"), password)
                    require_rejection(response, f"register {role} with a weak password")

    def test_missing_and_invalid_tokens_are_rejected(self):
        require_rejection(self.client.appointments(None), "request without a token", {400, 401, 403})
        require_rejection(self.client.appointments("invalid.token.value"),
                          "request with an invalid token", {400, 401, 403})

    def test_logout_invalidates_the_token(self):
        for role in ("patient", "caregiver"):
            with self.subTest(role=role):
                _, token = self.create_user(role, f"logout_{role}")
                require_status(self.client.logout(token), 200, f"logout {role}")
                require_rejection(self.client.appointments(token),
                                  f"reuse {role} token after logout", {400, 401, 403})

    def test_login_sessions_have_distinct_ids_and_independent_logout(self):
        for role in ("patient", "caregiver"):
            with self.subTest(role=role):
                username, first_token = self.create_user(role, f"sessions_{role}")
                second_token = self.client.login(role, username)
                self.assertNotEqual(first_token, second_token,
                                    "consecutive logins must create distinct sessions")
                # Check the session identifiers as well as the signed tokens:
                # this catches collisions even if the requests cross a second.
                session_ids = []
                for token in (first_token, second_token):
                    payload = token.split(".")[1]
                    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
                    self.assertTrue(claims.get("jti"), "login token must have a session ID")
                    session_ids.append(claims["jti"])
                self.assertNotEqual(*session_ids)

                require_status(self.client.logout(first_token), 200, "logout first session")
                require_rejection(self.client.appointments(first_token),
                                  "reuse first session after logout", {400, 401, 403})
                require_status(self.client.appointments(second_token), 200,
                               "use second session after first session logs out")
                require_status(self.client.logout(second_token), 200, "logout second session")


if __name__ == "__main__":
    run_module_cli()
