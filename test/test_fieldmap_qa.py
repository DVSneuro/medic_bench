import json
import tempfile
import unittest
from pathlib import Path

import nibabel as nib
import numpy as np

from scripts.fieldmap_qa import (
    compare_maps,
    discover_maps,
    filter_maps,
    matched_pairs,
    summarize_map,
)


class FieldmapQATests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "bench_out"
        self.affine = np.diag([2.0, 2.0, 2.5, 1.0])
        values = np.arange(4 * 5 * 6 * 3, dtype=np.float32).reshape((4, 5, 6, 3))
        self.warpkit_path = (
            self.root
            / "test-machine"
            / "echo2"
            / "warpkit"
            / "4"
            / "fmap_fieldmaps.nii"
        )
        self.niimath_path = (
            self.root
            / "test-machine"
            / "echo2"
            / "niimath"
            / "4"
            / "fmap_fieldmaps.nii"
        )
        self.warpkit_path.parent.mkdir(parents=True)
        self.niimath_path.parent.mkdir(parents=True)
        nib.save(nib.Nifti1Image(values, self.affine), self.warpkit_path)
        nib.save(nib.Nifti1Image(values * 2.0 + 1.0, self.affine), self.niimath_path)

    def tearDown(self):
        self.temporary.cleanup()

    def test_discovery_summary_and_pair_comparison(self):
        records = discover_maps(self.root)
        self.assertEqual(len(records), 2)
        niimath = filter_maps(records, tool="niimath")[0]
        self.assertEqual(niimath.machine, "test-machine")
        self.assertEqual(niimath.dataset, "echo2")
        self.assertEqual(niimath.threads, 4)
        self.assertEqual(niimath.kind, "fieldmaps")

        summary = summarize_map(niimath)
        self.assertEqual(summary["status"], "pass")
        self.assertEqual(summary["shape"], [4, 5, 6, 3])
        self.assertEqual(summary["sampled"]["frames"], [0, 1, 2])
        self.assertEqual(summary["sampled"]["finite_fraction_min"], 1.0)
        self.assertEqual(summary["orientation"], ["R", "A", "S"])

        pairs = matched_pairs(records)
        self.assertEqual(len(pairs), 1)
        comparison = compare_maps(*pairs[0])
        self.assertEqual(comparison["status"], "pass")
        self.assertAlmostEqual(comparison["sampled_comparison"]["correlation"], 1.0)
        self.assertGreater(comparison["sampled_comparison"]["root_mean_square_difference"], 0)

    def test_nonfinite_sample_warns(self):
        image = nib.load(self.niimath_path)
        data = np.asarray(image.dataobj).copy()
        data[0, 0, 0, 1] = np.nan
        nib.save(nib.Nifti1Image(data, self.affine), self.niimath_path)
        record = filter_maps(discover_maps(self.root), tool="niimath")[0]

        summary = summarize_map(record)

        self.assertEqual(summary["status"], "warn")
        self.assertIn("sampled_values_finite", summary["warnings"])

    def test_notebook_is_clean_and_calls_qa_helpers(self):
        notebook_path = Path(__file__).parents[1] / "notebooks" / "fieldmap_qa.ipynb"
        notebook = json.loads(notebook_path.read_text())
        self.assertEqual(notebook["nbformat"], 4)
        self.assertTrue(notebook["cells"])
        code = "\n".join(
            "".join(cell.get("source", []))
            for cell in notebook["cells"]
            if cell["cell_type"] == "code"
        )
        self.assertIn("discover_maps", code)
        self.assertIn("summarize_map", code)
        self.assertIn("compare_maps", code)
        self.assertIn("NiiVue", code)
        for cell in notebook["cells"]:
            if cell["cell_type"] == "code":
                self.assertIsNone(cell["execution_count"])
                self.assertEqual(cell["outputs"], [])


if __name__ == "__main__":
    unittest.main()
