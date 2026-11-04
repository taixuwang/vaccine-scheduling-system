"""Reservation, authorization, availability and inventory integration tests."""

from test_config import (
    IntegrationTestCase,
    empty_future_date,
    require_rejection,
    require_status,
    run_module_cli,
    schedule_sections,
)


class ReservationTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.caregiver_name, self.caregiver_token = self.create_user("caregiver", "res_cg")
        _, self.patient_token = self.create_user("patient", "res_patient")
        self.day = empty_future_date(self.client, self.patient_token)
        self.vaccine = self.name("res_vaccine")
        require_status(self.client.upload_availability(self.caregiver_token, self.day),
                       200, "upload availability")
        require_status(self.client.add_doses(self.caregiver_token, self.vaccine, 2),
                       200, "add test doses")
        caregivers, vaccines = schedule_sections(self.client.search(self.patient_token, self.day))
        self.assertEqual(caregivers, {self.caregiver_name},
                         "the selected date must contain only this test's caregiver")
        self.assertEqual(vaccines.get(self.vaccine), 2)

    def test_reserve_cancel_and_rebook_restores_capacity(self):
        appointment_id, caregiver = self.track_reservation(
            self.client.reserve(self.patient_token, self.day, self.vaccine), self.patient_token
        )
        self.assertEqual(caregiver, self.caregiver_name)
        appointments = require_status(self.client.appointments(self.patient_token), 200,
                                      "show appointments")["data"]
        self.assertTrue(any(item.split(" ", 1)[0] == appointment_id for item in appointments))

        _, other_token = self.create_user("patient", "other_patient")
        require_rejection(self.client.cancel(other_token, appointment_id),
                          "cancel another patient's appointment")
        self.cancel_tracked(appointment_id)
        require_rejection(self.client.cancel(self.patient_token, appointment_id),
                          "cancel an already-cancelled appointment", {400, 404, 409})
        appointments = require_status(self.client.appointments(self.patient_token), 200,
                                      "show appointments after cancellation")["data"]
        self.assertFalse(any(item.split(" ", 1)[0] == appointment_id for item in appointments))
        caregivers, vaccines = schedule_sections(self.client.search(self.patient_token, self.day))
        self.assertIn(self.caregiver_name, caregivers)
        self.assertEqual(vaccines.get(self.vaccine), 2)

        new_id, caregiver = self.track_reservation(
            self.client.reserve(self.patient_token, self.day, self.vaccine), self.patient_token
        )
        self.assertEqual(caregiver, self.caregiver_name)
        self.cancel_tracked(new_id)

    def test_unauthorized_reservations_and_inventory_updates_are_rejected(self):
        require_rejection(self.client.reserve(None, self.day, self.vaccine),
                          "reserve without authentication")
        require_rejection(self.client.reserve(self.caregiver_token, self.day, self.vaccine),
                          "reserve as caregiver")
        require_rejection(self.client.add_doses(self.patient_token, self.vaccine, 1),
                          "add doses as patient")

    def test_missing_doses_and_caregiver_are_rejected(self):
        require_rejection(self.client.reserve(self.patient_token, self.day, self.name("missing_vax")),
                          "reserve a nonexistent vaccine")
        empty_day = empty_future_date(self.client, self.patient_token)
        body = require_rejection(self.client.reserve(self.patient_token, empty_day, self.vaccine),
                                 "reserve with no caregiver")
        self.assertIn("caregiver", str(body.get("message", "")).lower())
        _, vaccines = schedule_sections(self.client.search(self.patient_token, self.day))
        self.assertEqual(vaccines.get(self.vaccine), 2)

    def test_invalid_date_does_not_consume_inventory(self):
        require_rejection(self.client.reserve(self.patient_token, "not-a-date", self.vaccine),
                          "reserve with an invalid date")
        appointment_id, caregiver = self.track_reservation(
            self.client.reserve(self.patient_token, self.day, self.vaccine), self.patient_token
        )
        self.assertEqual(caregiver, self.caregiver_name)
        self.cancel_tracked(appointment_id)

    def test_negative_dose_count_is_rejected(self):
        require_rejection(self.client.add_doses(self.caregiver_token, self.vaccine, -1),
                          "add a negative dose count", {400, 422})
        _, vaccines = schedule_sections(self.client.search(self.patient_token, self.day))
        self.assertEqual(vaccines.get(self.vaccine), 2)

    def test_reuploading_a_booked_date_does_not_prevent_cancellation(self):
        appointment_id, caregiver = self.track_reservation(
            self.client.reserve(self.patient_token, self.day, self.vaccine), self.patient_token
        )
        self.assertEqual(caregiver, self.caregiver_name)
        response = self.client.upload_availability(self.caregiver_token, self.day)
        if response.status_code == 200:
            require_status(response, 200, "reupload a booked date")
        else:
            require_rejection(response, "reupload a booked date", {400, 409, 422})
        self.cancel_tracked(appointment_id)


if __name__ == "__main__":
    run_module_cli()
