import unittest

from app.worker_config import validate_external_delivery


class WorkerConfigurationTests(unittest.TestCase):
    def test_missing_secrets_and_local_fallback_are_rejected(self):
        for values in [{}, {"DATABASE_URL": "sqlite:///approval.db", "NTFY_TOPIC": "a" * 48}, {"DATABASE_URL": "postgresql://user:password@db.example/app"}]:
            with self.subTest(values=list(values)):
                with self.assertRaises(ValueError):
                    validate_external_delivery(values)

    def test_one_external_destination_is_required(self):
        base = {"DATABASE_URL": "postgresql+psycopg://user:password@db.example/app"}
        validate_external_delivery(base | {"NTFY_TOPIC": "a" * 48})
        validate_external_delivery(base | {"OUTBOX_WEBHOOK_URL": "https://notify.example/hook"})
        for destination in [{"NTFY_TOPIC": "short"}, {"NTFY_TOPIC": "a" * 48, "OUTBOX_WEBHOOK_URL": "https://notify.example/hook"}, {"OUTBOX_WEBHOOK_URL": "http://notify.example/hook"}, {"OUTBOX_WEBHOOK_URL": "https://user:secret@notify.example/hook"}]:
            with self.subTest(destination=list(destination)):
                with self.assertRaises(ValueError):
                    validate_external_delivery(base | destination)

    def test_credentials_are_not_in_validation_errors(self):
        with self.assertRaises(ValueError) as result:
            validate_external_delivery({"DATABASE_URL": "sqlite:///secret-password.db"})
        self.assertNotIn("secret-password", str(result.exception))
