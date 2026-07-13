import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.utils.dynamic_registry import (
    DYNAMIC_LOCATION_BLOCK_END,
    DYNAMIC_LOCATION_BLOCK_START,
    DYNAMIC_LOCATION_INCLUDE,
    DynamicServiceGroup,
    _write_dynamic_files,
    render_dynamic_nginx_config,
)


class DynamicRegistryConfigTests(unittest.TestCase):
    def _rendered_config(self):
        group = DynamicServiceGroup(
            service_name="orders",
            route_prefix="/orders",
            description=None,
            instances=[
                SimpleNamespace(
                    instance_id="orders-1",
                    target_url="http://127.0.0.1:9000",
                )
            ],
        )
        registry_config = SimpleNamespace(domain_suffix=None)
        with patch(
            "app.utils.dynamic_registry.get_config",
            return_value=SimpleNamespace(dynamic_registry=registry_config),
        ):
            return render_dynamic_nginx_config([group])

    def test_path_location_uses_prefix_priority(self):
        rendered = self._rendered_config()

        self.assertIn("location = /orders {", rendered["locations/orders.conf"])
        self.assertIn("location ^~ /orders/ {", rendered["locations/orders.conf"])

    def test_dynamic_locations_are_inlined_idempotently_and_removed(self):
        rendered = self._rendered_config()
        with tempfile.TemporaryDirectory() as temp_dir:
            conf_dir = Path(temp_dir)
            conf_d_dir = conf_dir / "conf.d"
            conf_d_dir.mkdir(parents=True)
            unrelated = conf_d_dir / "10-unrelated.conf"
            unrelated.write_text(
                "server {\n"
                "    listen 80;\n"
                "    server_name unrelated.test;\n"
                "    location / { return 204; }\n"
                "}\n",
                encoding="utf-8",
            )
            webui = conf_d_dir / "20-webui.conf"
            webui.write_text(
                "server {\n"
                "    listen 80;\n"
                "    server_name _;\n"
                "    location / { try_files $uri /index.html; }\n"
                "    location /api/ { proxy_pass http://127.0.0.1:8001; }\n"
                f"    {DYNAMIC_LOCATION_INCLUDE}\n"
                "}\n",
                encoding="utf-8",
            )

            _write_dynamic_files(conf_dir, rendered)
            first_content = webui.read_text(encoding="utf-8")

            self.assertNotIn(DYNAMIC_LOCATION_INCLUDE, first_content)
            self.assertIn(DYNAMIC_LOCATION_BLOCK_START, first_content)
            self.assertIn(DYNAMIC_LOCATION_BLOCK_END, first_content)
            self.assertIn("location = /orders {", first_content)
            self.assertIn("location ^~ /orders/ {", first_content)
            self.assertNotIn(
                DYNAMIC_LOCATION_BLOCK_START,
                unrelated.read_text(encoding="utf-8"),
            )

            _write_dynamic_files(conf_dir, rendered)
            second_content = webui.read_text(encoding="utf-8")

            self.assertEqual(second_content.count(DYNAMIC_LOCATION_BLOCK_START), 1)
            self.assertEqual(second_content.count("location = /orders {"), 1)
            self.assertEqual(second_content.count("location ^~ /orders/ {"), 1)

            _write_dynamic_files(conf_dir, {"upstreams": "# empty\n"})
            removed_content = webui.read_text(encoding="utf-8")

            self.assertNotIn(DYNAMIC_LOCATION_BLOCK_START, removed_content)
            self.assertNotIn("location = /orders {", removed_content)
            self.assertEqual(
                list((conf_d_dir / "webui-dynamic" / "locations").glob("*.conf")),
                [],
            )


if __name__ == "__main__":
    unittest.main()
