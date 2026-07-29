import gzip
import json
import struct
import tempfile
import unittest
from pathlib import Path

import bench


def write_nifti(path, dimensions=(2, 3, 4, 5), voxel=(2.0, 2.5, 3.0)):
    header = bytearray(352)
    struct.pack_into("<I", header, 0, 348)
    struct.pack_into("<8h", header, 40, 4, *dimensions, 1, 1, 1)
    struct.pack_into("<h", header, 70, 16)
    struct.pack_into("<h", header, 72, 32)
    struct.pack_into("<8f", header, 76, 1.0, *voxel, 1.0, 0.0, 0.0, 0.0)
    struct.pack_into("<f", header, 108, 352.0)
    header[344:348] = b"n+1\0"
    payload = bytes(header) + bytes(4 * dimensions[0] * dimensions[1] * dimensions[2] * dimensions[3])
    if path.name.endswith(".gz"):
        with gzip.open(path, "wb") as stream:
            stream.write(payload)
    else:
        path.write_bytes(payload)


def write_sidecar(path, echo):
    path.write_text(
        json.dumps(
            {
                "EchoTime": 0.01 * echo,
                "TotalReadoutTime": 0.02,
                "PhaseEncodingDirection": "j-",
            }
        )
    )


def add_echo(root, stem, echo, parts=("mag", "phase")):
    for part in parts:
        image = root / ("%s_echo-%d_part-%s_bold.nii.gz" % (stem, echo, part))
        write_nifti(image)
        write_sidecar(image.with_name(image.name[:-7] + ".json"), echo)


class DatasetValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.stem = "sub-01_task-test_run-1"

    def tearDown(self):
        self.temp.cleanup()

    def test_complete_run_metadata(self):
        add_echo(self.root, self.stem, 1)
        add_echo(self.root, self.stem, 2)
        run = bench.validate_selected_run(self.root, self.stem, [1, 2])
        self.assertEqual(run["echoes"], [1, 2])
        self.assertEqual(run["tes"], [10.0, 20.0])
        self.assertEqual(run["header"]["frames"], 5)
        self.assertEqual(run["header"]["spatial_dimensions"], [2, 3, 4])
        self.assertEqual(run["ped"], "j-")

    def test_magnitude_phase_echo_mismatch_fails(self):
        add_echo(self.root, self.stem, 1)
        add_echo(self.root, self.stem, 2, parts=("mag",))
        with self.assertRaisesRegex(bench.BenchmarkError, "magnitude echoes"):
            bench.validate_selected_run(self.root, self.stem)

    def test_missing_exact_sidecar_fails(self):
        add_echo(self.root, self.stem, 1)
        add_echo(self.root, self.stem, 2)
        missing = self.root / ("%s_echo-2_part-phase_bold.json" % self.stem)
        missing.unlink()
        with self.assertRaisesRegex(bench.BenchmarkError, "missing selected-run"):
            bench.validate_selected_run(self.root, self.stem)

    def test_ambiguous_duplicate_fails(self):
        add_echo(self.root, self.stem, 1)
        add_echo(self.root, self.stem, 2)
        duplicate = self.root / ("%s_echo-1_part-mag_bold.nii" % self.stem)
        write_nifti(duplicate)
        with self.assertRaisesRegex(bench.BenchmarkError, "ambiguous duplicate"):
            bench.validate_selected_run(self.root, self.stem)


class ProvenanceAndReportingTests(unittest.TestCase):
    def test_peak_rss_units(self):
        self.assertEqual(bench.rss_to_bytes(2048, "Darwin"), 2048.0)
        self.assertEqual(bench.rss_to_bytes(2048, "Linux"), 2048.0 * 1024.0)

    def test_result_can_render_markdown(self):
        payload = {
            "schema_version": 2,
            "status": "complete",
            "started_at": "2026-01-01T00:00:00+00:00",
            "machine": {
                "label": "test-machine",
                "operating_system": "TestOS",
                "os_version": "1",
                "kernel_version": "1",
                "architecture": "test64",
                "cpu_manufacturer": "Test",
                "cpu_model": "CPU",
                "physical_cores": 2,
                "logical_cpus": 2,
                "performance_cores": "unavailable",
                "efficiency_cores": "unavailable",
                "total_ram_bytes": 1024,
            },
            "software": {
                "python": {"version": "3", "executable": "/python"},
                "warpkit": {"version": "1.4.1", "executables": {}},
                "niimath": {"version": "v1", "source_commit": "abc"},
                "medic_bench": {"commit": "def", "dirty": False},
            },
            "threads": [1],
            "results": {
                "sample": {
                    "dataset": {"echo_count": 2, "frame_count": 5},
                    "runs": {"1": {}},
                    "agreement": {},
                }
            },
        }
        rendered = bench.render_payload(payload)
        self.assertIn("# MEDIC benchmark — test-machine", rendered)
        self.assertIn("### sample — 2 echoes, 5 frames", rendered)


if __name__ == "__main__":
    unittest.main()
