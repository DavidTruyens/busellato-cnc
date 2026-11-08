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


if __name__ == "__main__":
    unittest.main()
