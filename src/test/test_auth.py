"""Authentication API integration tests.

Direct invocation targets localhost unless --target is provided. Discovery with
unittest skips these tests unless VACCINE_TEST_BASE_URL is set.
"""

import unittest

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
        for index, password in enumerate(passwords):
            with self.subTest(password_case=index):
                response = self.client.create("patient", self.name(f"weak{index}"), password)
                require_rejection(response, "register with a weak password")

    def test_missing_and_invalid_tokens_are_rejected(self):
        require_rejection(self.client.appointments(None), "request without a token", {400, 401, 403})
        require_rejection(self.client.appointments("invalid.token.value"),
                          "request with an invalid token", {400, 401, 403})

    def test_logout_invalidates_the_token(self):
        _, token = self.create_user("patient", "logout_patient")
        require_status(self.client.logout(token), 200, "logout")
        require_rejection(self.client.appointments(token), "reuse a token after logout", {400, 401, 403})


if __name__ == "__main__":
    run_module_cli()
