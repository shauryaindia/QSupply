import unittest
from importlib.metadata import PackageNotFoundError
from types import SimpleNamespace
from unittest.mock import patch

from qsupply.backends import qiskit as qiskit_adapter
from qsupply.backends import qulacs as qulacs_adapter
from qsupply.backends.qiskit import QiskitBackend
from qsupply.backends.qulacs import QulacsBackend


class TestBackendVersionAvailability(unittest.TestCase):
    @staticmethod
    def _qiskit_import(name):
        modules = {
            "qiskit": SimpleNamespace(QuantumCircuit=object),
            "qiskit.circuit": SimpleNamespace(ParameterVector=object),
            "qiskit.primitives": SimpleNamespace(StatevectorSampler=object),
        }
        return modules[name]

    def test_qiskit_accepts_supported_versions_and_rejects_out_of_range_or_malformed(self):
        cases = (
            ("2.6.2", True),
            ("2.6.99", True),
            ("2.6.2.post1", True),
            ("2.6.1", False),
            ("2.7.0", False),
            ("3.0.0", False),
            ("2.6", False),
            ("not-a-version", False),
            ("2.6.2rc1", False),
        )
        for sdk_version, expected in cases:
            with self.subTest(version=sdk_version):
                with (
                    patch.object(
                        qiskit_adapter.importlib,
                        "import_module",
                        side_effect=self._qiskit_import,
                    ),
                    patch.object(qiskit_adapter, "version", return_value=sdk_version),
                ):
                    self.assertEqual(QiskitBackend.is_available(), expected)

    def test_qiskit_missing_package_or_metadata_is_unavailable(self):
        with patch.object(
            qiskit_adapter.importlib,
            "import_module",
            side_effect=ModuleNotFoundError("qiskit missing"),
        ):
            self.assertFalse(QiskitBackend.is_available())
        with (
            patch.object(
                qiskit_adapter.importlib,
                "import_module",
                side_effect=self._qiskit_import,
            ),
            patch.object(
                qiskit_adapter,
                "version",
                side_effect=PackageNotFoundError("qiskit"),
            ),
        ):
            self.assertFalse(QiskitBackend.is_available())
            self.assertIsNone(QiskitBackend.version())

    def test_qulacs_accepts_supported_versions_and_rejects_out_of_range_or_malformed(self):
        cases = (
            ("0.6.12", True),
            ("0.6.99", True),
            ("0.6.12.post1", True),
            ("0.6.11", False),
            ("0.7.0", False),
            ("1.0.0", False),
            ("0.6", False),
            ("unknown", False),
            ("0.6.12.dev1", False),
        )
        for sdk_version, expected in cases:
            with self.subTest(version=sdk_version):
                with (
                    patch.object(
                        qulacs_adapter.importlib,
                        "import_module",
                        return_value=object(),
                    ),
                    patch.object(qulacs_adapter, "version", return_value=sdk_version),
                ):
                    self.assertEqual(QulacsBackend.is_available(), expected)

    def test_qulacs_missing_package_or_metadata_is_unavailable(self):
        with patch.object(
            qulacs_adapter.importlib,
            "import_module",
            side_effect=ModuleNotFoundError("qulacs missing"),
        ):
            self.assertFalse(QulacsBackend.is_available())
        with (
            patch.object(
                qulacs_adapter.importlib,
                "import_module",
                return_value=object(),
            ),
            patch.object(
                qulacs_adapter,
                "version",
                side_effect=PackageNotFoundError("qulacs"),
            ),
        ):
            self.assertFalse(QulacsBackend.is_available())
            self.assertIsNone(QulacsBackend.version())


if __name__ == "__main__":
    unittest.main()
