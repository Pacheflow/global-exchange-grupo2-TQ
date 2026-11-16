"""Pruebas del validador: fallos y evidencia, sin contactar Docker ni SSH."""
import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("production_validator", Path(__file__).with_name("validate-production.py"))
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class ProductionValidationTests(unittest.TestCase):
    def result(self, output="", code=0):
        return subprocess.CompletedProcess([], code, output, "secreto-no-publicar")

    def test_static_success_is_not_runtime_evidence(self):
        with patch.object(validator, "run", return_value=self.result("commit")):
            result = validator.validate("env", "compose")
        self.assertTrue(result["ok"])
        self.assertFalse(result["validacion_productiva_completa"])
        self.assertNotIn("secreto-no-publicar", str(result))

    def test_invalid_compose_prevents_runtime_checks(self):
        with patch.object(validator, "run", side_effect=[self.result("commit"), self.result(), self.result(code=1)]) as run:
            result = validator.validate("env", "compose", True)
        self.assertFalse(result["ok"])
        self.assertFalse(result["validacion_productiva_completa"])
        self.assertEqual(run.call_count, 3)

    def test_timeout_is_recorded_as_failure(self):
        with patch.object(validator, "run", side_effect=[self.result("commit"), subprocess.TimeoutExpired("bash", 120), self.result()]):
            result = validator.validate("env", "compose")
        self.assertFalse(result["ok"])

    def test_missing_container_fails_runtime(self):
        def run(args):
            if args[:2] == ["git", "rev-parse"]:
                return self.result("commit")
            return self.result()
        with patch.object(validator, "run", side_effect=run):
            result = validator.validate("env", "compose", True)
        self.assertFalse(result["validacion_productiva_completa"])
        self.assertEqual(sum(not c["ok"] for c in result["checks"]), 5)

    def test_revision_mismatch_fails(self):
        def run(args):
            if args[0] == "git":
                return self.result("commit")
            if "ps" in args:
                return self.result("container")
            if "inspect" in args:
                return self.result("old" if "Labels" in args[3] else "running healthy")
            if "wget" in args:
                return self.result("ok")
            return self.result()
        with patch.object(validator, "run", side_effect=run):
            result = validator.validate("env", "compose", True)
        self.assertFalse(result["validacion_productiva_completa"])
        self.assertFalse(next(c for c in result["checks"] if c["nombre"] == "imagen_commit")["ok"])

    def test_runtime_success_requires_all_checks(self):
        def run(args):
            if args[0] == "git":
                return self.result("commit")
            if "ps" in args:
                return self.result("container")
            if "inspect" in args:
                return self.result("commit" if "Labels" in args[3] else "running healthy")
            if "wget" in args:
                return self.result("ok")
            return self.result()
        with patch.object(validator, "run", side_effect=run):
            result = validator.validate("env", "compose", True)
        self.assertTrue(result["validacion_productiva_completa"])
        self.assertEqual(len(result["checks"]), 10)


if __name__ == "__main__":
    unittest.main()
