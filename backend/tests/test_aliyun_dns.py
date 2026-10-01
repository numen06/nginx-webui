import contextlib
import asyncio
import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.utils import aliyun_dns, certbot
from app.routers import certificates


class AliyunDnsTests(unittest.TestCase):
    def test_credentials_are_private_and_zone_is_checked(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"DATA_ROOT": root}):
            aliyun_dns.save_credentials("51JBM.CN", "test-id", "test-secret")
            path = aliyun_dns.credentials_path()
            self.assertEqual(path.parent, Path(root) / "letsencrypt")
            self.assertEqual(aliyun_dns.load_credentials()["zone"], "51jbm.cn")
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(aliyun_dns._record_name("*.51jbm.cn", "51jbm.cn"), "_acme-challenge.51jbm.cn")
            self.assertEqual(aliyun_dns._record_name("www.51jbm.cn", "51jbm.cn"), "_acme-challenge.www.51jbm.cn")
            with self.assertRaises(ValueError):
                aliyun_dns._record_name("51jbm.cn.evil.example", "51jbm.cn")

    def test_hook_cleans_only_the_record_it_created(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {
            "DATA_ROOT": root,
            "CERTBOT_DOMAIN": "*.51jbm.cn",
            "CERTBOT_VALIDATION": "new-value",
        }):
            aliyun_dns.save_credentials("51jbm.cn", "test-id", "test-secret")
            with patch.object(aliyun_dns, "_add_txt", return_value="12345") as add, \
                    patch.object(aliyun_dns, "_wait_for_txt", return_value=True), \
                    patch.object(aliyun_dns, "_delete_txt") as delete:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    aliyun_dns.run_hook("auth")
                self.assertEqual(output.getvalue().strip(), "12345")
                add.assert_called_once()
                self.assertEqual(add.call_args.args[1:], ("_acme-challenge.51jbm.cn", "new-value"))
                self.assert_not_contains_secret(output.getvalue())
                with patch.dict(os.environ, {"CERTBOT_AUTH_OUTPUT": output.getvalue()}):
                    aliyun_dns.run_hook("cleanup")
                delete.assert_called_once()
                self.assertEqual(delete.call_args.args[1], "12345")

    def test_txt_wait_uses_authoritative_nameservers(self):
        import dns.resolver

        server_a = SimpleNamespace(target="dns13.hichina.com.")
        server_b = SimpleNamespace(target="dns14.hichina.com.")
        answer = SimpleNamespace(strings=[b"new-", b"value"])
        resolver_a = SimpleNamespace(resolve=lambda *args, **kwargs: [answer])
        resolver_b = SimpleNamespace(resolve=lambda *args, **kwargs: [answer])
        with patch.object(dns.resolver, "resolve", return_value=[server_a, server_b]), \
                patch.object(dns.resolver, "Resolver", side_effect=[resolver_a, resolver_b]), \
                patch.object(aliyun_dns.socket, "gethostbyname", return_value="1.2.3.4"), \
                patch.object(aliyun_dns.time, "sleep") as sleep:
            self.assertTrue(aliyun_dns._wait_for_txt(
                "_acme-challenge.51jbm.cn", "new-value", "51jbm.cn", seconds=30
            ))
        sleep.assert_called_once_with(15)

    def test_config_api_never_returns_secret(self):
        with patch.object(certificates, "load_credentials", return_value={
            "zone": "51jbm.cn", "access_key_id": "test-id", "access_key_secret": "test-secret"
        }):
            result = asyncio.run(certificates.get_aliyun_dns_config(current_user=SimpleNamespace()))
        self.assertTrue(result["configured"])
        self.assertTrue(result["has_secret"])
        self.assertNotIn("test-secret", str(result))

    def assert_not_contains_secret(self, value):
        self.assertNotIn("test-secret", value)

    def test_certbot_uses_saved_dns_hooks_without_secrets_in_arguments(self):
        with tempfile.TemporaryDirectory() as root:
            executable = Path(root) / "certbot"
            executable.touch()
            config = SimpleNamespace(nginx=SimpleNamespace(certbot_path=str(executable), static_dir=root))
            captured = []

            def run(command, timeout):
                captured.extend(command)
                self.assertEqual(timeout, 1200)
                return {"success": True, "output": "issued"}

            with patch.object(certbot, "get_config", return_value=config), \
                    patch.object(certbot, "quarantine_broken_renewal_configs", return_value=[]), \
                    patch.object(certbot, "test_acme_directory_connectivity", return_value={"ok": True}), \
                    patch.object(certbot, "get_certbot_config_dir", return_value=Path(root)), \
                    patch.object(certbot, "get_certbot_live_root", return_value=Path(root)), \
                    patch.object(certbot, "_run_certbot", side_effect=run), \
                    patch.object(aliyun_dns, "load_credentials", return_value={
                        "zone": "51jbm.cn", "access_key_id": "test-id", "access_key_secret": "test-secret"
                    }):
                result = certbot.request_certificate(
                    ["51jbm.cn", "*.51jbm.cn"], "admin@example.com", "aliyun_dns"
                )

            self.assertTrue(result["success"])
            self.assertEqual(result["certbot_cert_name"], "51jbm.cn")
            self.assertIn("--manual-auth-hook", captured)
            self.assertIn("--manual-cleanup-hook", captured)
            self.assertIn("--force-renewal", captured)
            self.assertEqual(captured.count("-d"), 2)
            self.assertNotIn("test-secret", " ".join(captured))


if __name__ == "__main__":
    unittest.main()
