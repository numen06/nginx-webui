import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.utils import certbot


class RenewalWindowTests(unittest.TestCase):
    def test_defaults_to_15_days_and_preserves_explicit_override(self):
        with tempfile.TemporaryDirectory() as root, patch.object(
            certbot, "get_certbot_renewal_root", return_value=Path(root)
        ):
            conf = Path(root) / "hz-aitech.com.conf"
            conf.write_text("# renew_before_expiry = 30 days\n[renewalparams]\n", encoding="utf-8")
            self.assertTrue(certbot.ensure_default_renewal_window("hz-aitech.com"))
            self.assertEqual(conf.read_text(encoding="utf-8").splitlines()[0], "renew_before_expiry = 15 days")

            conf.write_text("renew_before_expiry = 7 days\n[renewalparams]\n", encoding="utf-8")
            self.assertFalse(certbot.ensure_default_renewal_window("hz-aitech.com"))
            self.assertEqual(conf.read_text(encoding="utf-8").splitlines()[0], "renew_before_expiry = 7 days")

            with self.assertRaises(ValueError):
                certbot.ensure_default_renewal_window("../hz-aitech.com")


if __name__ == "__main__":
    unittest.main()
