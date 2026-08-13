import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import installer_launcher


class InstallerRecoveryTests(unittest.TestCase):
    def test_install_preserves_previous_version_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            install = root / "install"
            data = root / "data"
            install.mkdir()
            destination = install / installer_launcher.APP_EXE
            destination.write_bytes(b"versao-anterior")
            source = root / "novo.exe"
            source.write_bytes(b"versao-nova")
            setup_source = root / "setup.exe"
            setup_source.write_bytes(b"instalador")
            environment = {
                "VENDAS_PRO_INSTALL_DIR": str(install),
                "VENDAS_PRO_DATA_DIR": str(data),
                "VENDAS_PRO_SKIP_SHORTCUTS": "1",
                "VENDAS_PRO_SKIP_STOP": "1",
            }
            with patch.dict(os.environ, environment, clear=False), patch(
                "installer_launcher.bundled_file", return_value=source
            ), patch("installer_launcher.sys.executable", str(setup_source)), patch(
                "installer_launcher.verify_application"
            ) as verify_application:
                installer_launcher.perform_install(launch=False)
                self.assertEqual(b"versao-nova", destination.read_bytes())
                self.assertEqual(b"versao-anterior", (install / installer_launcher.ROLLBACK_EXE).read_bytes())
                self.assertTrue(data.is_dir())
                installer_launcher.perform_rollback(silent=True, launch=False)
                self.assertEqual(b"versao-anterior", destination.read_bytes())
                self.assertEqual(b"versao-nova", (install / installer_launcher.FAILED_EXE).read_bytes())
                verify_application.assert_called_once_with(source)

    def test_invalid_new_version_is_rejected_before_replacing_the_old_one(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            install = root / "install"
            install.mkdir()
            destination = install / installer_launcher.APP_EXE
            destination.write_bytes(b"versao-estavel")
            source = root / "novo-com-defeito.exe"
            source.write_bytes(b"versao-com-defeito")
            environment = {
                "VENDAS_PRO_INSTALL_DIR": str(install),
                "VENDAS_PRO_DATA_DIR": str(root / "data"),
                "VENDAS_PRO_SKIP_SHORTCUTS": "1",
                "VENDAS_PRO_SKIP_STOP": "1",
            }
            with patch.dict(os.environ, environment, clear=False), patch(
                "installer_launcher.bundled_file", return_value=source
            ), patch(
                "installer_launcher.verify_application",
                side_effect=RuntimeError("executável inválido"),
            ):
                with self.assertRaisesRegex(RuntimeError, "inválido"):
                    installer_launcher.perform_install(launch=False)
            self.assertEqual(b"versao-estavel", destination.read_bytes())
            self.assertFalse((install / installer_launcher.ROLLBACK_EXE).exists())

    def test_tampered_rollback_is_rejected_without_touching_current_version(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            install = root / "install"
            install.mkdir()
            destination = install / installer_launcher.APP_EXE
            destination.write_bytes(b"versao-anterior")
            source = root / "novo.exe"
            source.write_bytes(b"versao-nova")
            setup_source = root / "setup.exe"
            setup_source.write_bytes(b"instalador")
            environment = {
                "VENDAS_PRO_INSTALL_DIR": str(install),
                "VENDAS_PRO_DATA_DIR": str(root / "data"),
                "VENDAS_PRO_SKIP_SHORTCUTS": "1",
                "VENDAS_PRO_SKIP_STOP": "1",
            }
            with patch.dict(os.environ, environment, clear=False), patch(
                "installer_launcher.bundled_file", return_value=source
            ), patch("installer_launcher.sys.executable", str(setup_source)), patch(
                "installer_launcher.verify_application"
            ):
                installer_launcher.perform_install(launch=False)
                rollback = install / installer_launcher.ROLLBACK_EXE
                rollback.write_bytes(b"conteudo-adulterado")
                with self.assertRaisesRegex(RuntimeError, "integridade"):
                    installer_launcher.perform_rollback(silent=True, launch=False)
            self.assertEqual(b"versao-nova", destination.read_bytes())


if __name__ == "__main__":
    unittest.main()
