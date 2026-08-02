import unittest

from trading_wfo.robustness import generate_parameter_variations


class ParameterVariationTest(unittest.TestCase):
    def test_generates_cartesian_offsets_and_inserts_center(self):
        generated = generate_parameter_variations(
            {"fast": 10, "slow": 40, "lot": 0.01},
            {"fast": [-2, 2], "slow": [-5, 0, 5]},
        )

        self.assertEqual(len(generated), 9)
        centers = [item for item in generated if item[2]]
        self.assertEqual(len(centers), 1)
        self.assertEqual(centers[0][0], {"fast": 10, "slow": 40, "lot": 0.01})

    def test_rejects_unknown_non_numeric_and_excessive_variations(self):
        with self.assertRaisesRegex(ValueError, "unknown parameter"):
            generate_parameter_variations({"fast": 10}, {"slow": [-1, 0, 1]})
        with self.assertRaisesRegex(TypeError, "numeric center"):
            generate_parameter_variations({"mode": "fast"}, {"mode": [-1, 1]})
        with self.assertRaisesRegex(ValueError, "max_variations=4"):
            generate_parameter_variations(
                {"fast": 10, "slow": 40},
                {"fast": [-1, 0, 1], "slow": [-1, 0, 1]},
                max_variations=4,
            )


if __name__ == "__main__":
    unittest.main()
