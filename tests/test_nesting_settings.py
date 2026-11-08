import unittest

from nesting.settings import Settings, SettingsError


def _set(s, path, value):
    obj = s
    parts = path.split(".")
    for p in parts[:-1]:
        obj = getattr(obj, p)
    setattr(obj, parts[-1], value)


class SettingsTests(unittest.TestCase):
    def test_defaults_roundtrip_through_dict(self):
        s = Settings.default()
        self.assertEqual(Settings.from_dict(s.to_dict()), s)

    def test_missing_keys_default(self):
        s = Settings.from_dict({"router": {"diameter": 12}, "bogus": 1})
        self.assertEqual(s.router.diameter, 12)
        self.assertEqual(s.router.tool, 66)
        self.assertEqual(s.panel.length, 2440)
        self.assertEqual(Settings.from_dict({}), Settings.default())

    def test_gap_is_diameter_plus_clearance(self):
        s = Settings.default()
        self.assertEqual(s.gap, 12)
        s.router.diameter = 12
        self.assertEqual(s.gap, 16)

    def test_defaults_validate(self):
        Settings.default().validate()

    def test_shapes_per_must_be_a_whole_number_of_one_or_more(self):
        for value in (1.5, 0, -2, True, "2", 2.0):
            with self.subTest(value=value):
                s = Settings.default()
                s.template.shapes_per = value
                with self.assertRaises(SettingsError) as cm:
                    s.validate()
                self.assertEqual(cm.exception.field, "template.shapes_per")
        s = Settings.default()
        s.template.shapes_per = 3
        s.validate()

    def test_tool_numbers_must_be_whole(self):
        for field in ("router.tool", "drill_fix.tool", "drill_screw.tool"):
            for value in (66.5, True, "66", 0, -1, 2.0):
                with self.subTest(field=field, value=value):
                    s = Settings.default()
                    _set(s, field, value)
                    with self.assertRaises(SettingsError) as cm:
                        s.validate()
                    self.assertEqual(cm.exception.field, field)
            s = Settings.default()
            _set(s, field, 7)
            s.validate()

    def test_rejected(self):
        cases = [
            ("router.depth_per_pass", 0),
            ("router.diameter", 0),
            ("heights.scrap", -1),
            ("origin", "G56"),
            ("template.mode", "x"),
        ]
        for field, value in cases:
            with self.subTest(field=field):
                s = Settings.default()
                _set(s, field, value)
                with self.assertRaises(SettingsError) as cm:
                    s.validate()
                self.assertEqual(cm.exception.field, field)

    def test_non_finite_numbers_rejected(self):
        fields = ["router.cut_feed", "panel.length", "heights.into_template",
                  "template.fixed_width", "drill_screw.depth", "router.clearance"]
        for field in fields:
            for value in (float("inf"), float("-inf"), float("nan")):
                with self.subTest(field=field, value=value):
                    s = Settings.default()
                    _set(s, field, value)
                    with self.assertRaises(SettingsError) as cm:
                        s.validate()
                    self.assertEqual(cm.exception.field, field)


class CupDepthTests(unittest.TestCase):
    """C1: no written depth may reach the top of the vacuum cups (stack top)."""

    def rejected(self, field, value, mode=None):
        s = Settings.default()
        if mode:
            s.template.mode = mode
        _set(s, field, value)
        with self.assertRaises(SettingsError) as cm:
            s.validate()
        self.assertEqual(cm.exception.field, field)
        self.assertIn("cups", cm.exception.message)
        return cm.exception

    def test_reviewer_examples_rejected(self):
        e = self.rejected("heights.into_scrap", 20)
        self.assertIn("heights.scrap", e.message)
        self.assertIn("18", e.message)
        self.rejected("heights.fix_into_scrap", 20)
        e = self.rejected("drill_screw.depth", 40)
        self.assertIn("36", e.message)          # scrap 18 + template stock 18

    def test_equal_to_the_limit_is_rejected(self):
        self.rejected("heights.into_scrap", 18)
        self.rejected("heights.fix_into_scrap", 18)
        self.rejected("drill_screw.depth", 36)
        self.rejected("heights.into_template", 18)

    def test_into_template_must_stay_in_the_template_stock(self):
        e = self.rejected("heights.into_template", 19)
        self.assertIn("heights.template_stock", e.message)

    def test_screw_depth_without_template_counts_the_scrap_only(self):
        e = self.rejected("drill_screw.depth", 18, mode="none")
        self.assertIn("18", e.message)
        s = Settings.default()
        s.template.mode = "none"
        s.drill_screw.depth = 17.9
        s.validate()

    def test_just_below_the_limits_is_fine(self):
        s = Settings.default()
        s.heights.into_scrap = 17.9
        s.heights.fix_into_scrap = 17.9
        s.heights.into_template = 17.9
        s.drill_screw.depth = 35.9
        s.validate()


if __name__ == "__main__":
    unittest.main()
