import unittest

from helpers import put_bit
from nesting.settings import Settings, SettingsError
from nesting.tools import HeadError


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
        s = Settings.from_dict({"router": {"clearance": 5}, "bogus": 1})
        self.assertEqual(s.router.clearance, 5)
        self.assertEqual(s.router.tool, 66)
        self.assertEqual(s.panel.length, 2440)
        self.assertEqual(Settings.from_dict({}), Settings.default())

    def test_gap_follows_the_bit(self):
        s = Settings.default()
        self.assertEqual(s.gap, 12)
        put_bit(s, 66, diameter=12)
        self.assertEqual(s.gap, 16)

    def test_settings_carry_the_default_table(self):
        s = Settings()
        self.assertEqual(s.router_bit.diameter, 8)
        self.assertEqual(s.router_bit.depth_per_pass, 9)
        self.assertEqual(s.fix_bit.diameter, 6)
        self.assertEqual(s.screw_bit.diameter, 3)
        d = Settings().to_dict()
        self.assertNotIn("tools", d)
        self.assertNotIn("diameter", d["router"])
        for section in ("drill_fix", "drill_screw"):
            self.assertNotIn("diameter", d[section])
            self.assertNotIn("feed", d[section])

    def test_from_dict_takes_a_table(self):
        s = Settings()
        put_bit(s, 66, diameter=10)
        t = Settings.from_dict({"router": {"clearance": 2}}, s.tools)
        self.assertEqual((t.router_bit.diameter, t.gap), (10, 12))
        self.assertEqual(Settings.from_dict({}, None).router_bit.diameter, 8)

    def test_old_router_fields_are_ignored(self):
        s = Settings.from_dict({"router": {"diameter": 12, "tool": 66}})
        self.assertEqual(s.router_bit.diameter, 8)     # the table, not the old field
        s = Settings.from_dict({"tools": {"bits": [], "heads": {}}})
        self.assertEqual(s.tools, Settings.default().tools)    # the table is passed apart

    def test_router_head_errors(self):
        s = Settings.default()
        s.router.tool = 65
        with self.assertRaises(HeadError) as cm:
            s.validate()
        self.assertEqual(cm.exception.field, "router.tool")
        self.assertEqual(cm.exception.message, "router: head T65 holds no bit")
        s = Settings.default()
        s.drill_fix.tool = 60
        with self.assertRaises(HeadError) as cm:
            s.validate()
        self.assertEqual(cm.exception.field, "drill_fix.tool")
        self.assertIn("programs do not use T60", cm.exception.message)
        self.assertIn("fixing drill", cm.exception.message)
        s = Settings.default()
        s.drill_screw.tool = 66
        with self.assertRaises(HeadError) as cm:
            s.validate()
        self.assertEqual(cm.exception.field, "drill_screw.tool")
        self.assertIn("screw drill", cm.exception.message)
        s = Settings.default()
        s.pockets.tool = 1
        with self.assertRaises(SettingsError) as cm:
            s.validate()
        self.assertEqual(cm.exception.field, "pockets.tool")
        self.assertIn("T1", cm.exception.message)
        self.assertIn("T65 or T66", cm.exception.message)

    def test_empty_pocket_default_head_is_not_an_error_here(self):
        # R2: only the head number is checked; that it holds a bit counts when a pocket uses it
        s = Settings.default()
        s.pockets.tool = 65
        s.validate()

    def test_validate_checks_the_table(self):
        s = Settings.default()
        s.tools.bit("b1").diameter = 0
        with self.assertRaises(SettingsError) as cm:
            s.validate()
        self.assertEqual(cm.exception.field, "tools.bits.b1.diameter")

    def test_defaults_validate(self):
        Settings.default().validate()

    def test_shapes_per_must_be_a_whole_number_of_one_or_more(self):
        for value in (1.5, 0, -2, True, "2", 2.0):
            with self.subTest(value=value):
                s = Settings.default()
                s.blank.shapes_per = value
                with self.assertRaises(SettingsError) as cm:
                    s.validate()
                self.assertEqual(cm.exception.field, "blank.shapes_per")
        s = Settings.default()
        s.blank.shapes_per = 3
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
            s = Settings.default()          # another whole number of an allowed head
            head = 65 if field == "router.tool" else 7
            put_bit(s, head)
            _set(s, field, head)
            s.validate()

    def test_rejected(self):
        cases = [
            ("heights.scrap", -1),
            ("origin", "G56"),
            ("blank.group_by", "x"),
            ("machine.frame_x", 0),
            ("machine.frame_y", -5),
            ("panel.kerf", -1),
            ("panel.thickness", 0),
        ]
        for field, value in cases:
            with self.subTest(field=field):
                s = Settings.default()
                _set(s, field, value)
                with self.assertRaises(SettingsError) as cm:
                    s.validate()
                self.assertEqual(cm.exception.field, field)

    def test_non_finite_numbers_rejected(self):
        fields = ["panel.length", "heights.into_scrap",
                  "drill_screw.depth", "router.clearance", "machine.frame_x",
                  "machine.frame_y", "panel.kerf", "panel.edge", "panel.thickness"]
        for field in fields:
            for value in (float("inf"), float("-inf"), float("nan")):
                with self.subTest(field=field, value=value):
                    s = Settings.default()
                    _set(s, field, value)
                    with self.assertRaises(SettingsError) as cm:
                        s.validate()
                    self.assertEqual(cm.exception.field, field)


class NewModelSettingsTests(unittest.TestCase):
    """2026-11-09: blanks sawn from the panel, a machine work frame, a saw kerf."""

    def test_defaults(self):
        s = Settings.default()
        self.assertEqual((s.machine.frame_x, s.machine.frame_y), (3072, 787))
        self.assertEqual((s.panel.length, s.panel.width, s.panel.edge, s.panel.kerf),
                         (2440, 1220, 10, 4))
        self.assertEqual(s.panel.thickness, 18)
        self.assertEqual(s.stack, 36)
        self.assertEqual(s.blank.shapes_per, 2)
        d = s.to_dict()
        self.assertNotIn("template", d)
        for gone in ("template_stock", "into_template", "shape_thickness"):
            self.assertNotIn(gone, d["heights"])

    def test_old_project_settings_are_migrated(self):
        old = {"template": {"mode": "none", "shapes_per": 3, "margin_end": 50,
                            "fixed_width": 900},
               "heights": {"scrap": 16, "template_stock": 18, "shape_thickness": 19,
                           "into_template": 0.3}}
        s = Settings.from_dict(old)
        self.assertEqual((s.blank.shapes_per, s.blank.margin_end), (3, 50))
        self.assertEqual((s.heights.scrap, s.panel.thickness), (16, 19))
        s.validate()
        # a new-style key wins over the old one
        s = Settings.from_dict({"template": {"shapes_per": 3}, "blank": {"shapes_per": 1},
                                "heights": {"shape_thickness": 19}, "panel": {"thickness": 22}})
        self.assertEqual((s.blank.shapes_per, s.panel.thickness), (1, 22))

    def rejected(self, field, *needles, **values):
        s = Settings.default()
        for path, v in values.items():
            _set(s, path.replace("__", "."), v)
        with self.assertRaises(SettingsError) as cm:
            s.validate()
        self.assertEqual(cm.exception.field, field)
        for n in needles:
            self.assertIn(n, cm.exception.message)

    def test_edge_must_be_zero_or_at_least_the_kerf(self):
        self.rejected("panel.edge", "panel.kerf", "4", panel__edge=3)
        for edge in (0, 4, 10):
            s = Settings.default()
            s.panel.edge = edge
            s.validate()
        s = Settings.default()
        s.panel.kerf = 0            # a kerf of 0 is allowed (and then any trim)
        s.panel.edge = 1
        s.validate()

    def test_edge_must_leave_some_panel(self):
        self.rejected("panel.edge", "nothing", panel__edge=608, panel__width=1220)

    def test_frame_must_leave_room_between_the_margins(self):
        self.rejected("machine.frame_y", "blank.margin_side", "90", machine__frame_y=90)
        self.rejected("machine.frame_x", "blank.margin_end", "90", machine__frame_x=80)
        s = Settings.default()
        s.machine.frame_y = 91
        s.validate()

    def test_unverified_frame_values_are_plain_numbers(self):
        # numbers only: an unverified value is still a valid setting
        s = Settings.default()
        s.machine.frame_x, s.machine.frame_y = 5000, 1300
        s.validate()


class CupDepthTests(unittest.TestCase):
    """C1: no written depth may reach the top of the vacuum cups (stack top)."""

    def rejected(self, field, value):
        s = Settings.default()
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
        self.assertIn("heights.scrap (18", e.message)   # below the blank: into the scrap only

    def test_equal_to_the_limit_is_rejected(self):
        self.rejected("heights.into_scrap", 18)
        self.rejected("heights.fix_into_scrap", 18)
        self.rejected("drill_screw.depth", 18)

    def test_limit_follows_the_scrap_thickness(self):
        s = Settings.default()
        s.heights.scrap = 25
        s.heights.into_scrap = 24.9
        s.drill_screw.depth = 24.9
        s.validate()
        s.heights.scrap = 24.9
        with self.assertRaises(SettingsError):
            s.validate()

    def test_just_below_the_limits_is_fine(self):
        s = Settings.default()
        s.heights.into_scrap = 17.9
        s.heights.fix_into_scrap = 17.9
        s.drill_screw.depth = 17.9
        s.validate()


class PocketSettingsTests(unittest.TestCase):
    def test_pockets_defaults_present(self):
        s = Settings.default()
        p = s.pockets
        self.assertEqual((p.min_circle_diameter, p.min_floor, p.tool, p.depth, p.direction),
                         (8, 2, 66, 8, "cw"))
        self.assertEqual(set(s.to_dict()["pockets"]),
                         {"min_circle_diameter", "min_floor", "tool", "depth", "direction"})
        # diameter, speeds, feeds, depth per pass and stepover are the bit's in T66 (R4: the
        # router's 9 mm per pass, not the old pocket default's 4)
        b = s.tools.bit_in(p.tool)
        self.assertEqual((b.diameter, b.depth_per_pass, b.plunge_feed, b.cut_feed,
                          b.spindle_rpm, b.stepover_pct), (8, 9, 1, 3, 18000, 40))
        self.assertEqual(s.to_dict()["pockets"]["tool"], 66)
        self.assertEqual(Settings.from_dict(s.to_dict()), s)
        s.validate()

    def test_old_project_loads_pocket_defaults(self):
        s = Settings.from_dict({"router": {"diameter": 12}, "panel": {"thickness": 19}})
        self.assertEqual(s.pockets, Settings.default().pockets)
        s.validate()

    def test_pocket_depth_must_leave_floor(self):
        s = Settings.default()
        s.pockets.depth = 17
        with self.assertRaises(SettingsError) as cm:
            s.validate()
        self.assertEqual(cm.exception.field, "pockets.depth")
        s.pockets.depth = 16
        s.validate()

    def test_stepover_out_of_range(self):
        # the stepover is the bit's: checked with the tool table
        for value in (0, -5, 100.5, float("nan"), "40", True, 1e-9, 0.4, 9.99):
            with self.subTest(value=value):
                s = Settings.default()
                bit = s.tools.bit_in(s.pockets.tool)
                bit.stepover_pct = value
                with self.assertRaises(SettingsError) as cm:
                    s.validate()
                self.assertEqual(cm.exception.field, f"tools.bits.{bit.id}.stepover_pct")
        for value in (10, 100):
            s = Settings.default()
            s.tools.bit_in(s.pockets.tool).stepover_pct = value
            s.validate()

    def test_stepover_message_names_the_range(self):
        s = Settings.default()
        s.tools.bit_in(s.pockets.tool).stepover_pct = 0.4
        with self.assertRaises(SettingsError) as cm:
            s.validate()
        self.assertIn("between 10 and 100", cm.exception.message)

    def test_pocket_tool_must_be_whole_number(self):
        for value in (66.5, True, "66", 0, -1, 2.0):
            with self.subTest(value=value):
                s = Settings.default()
                s.pockets.tool = value
                with self.assertRaises(SettingsError) as cm:
                    s.validate()
                self.assertEqual(cm.exception.field, "pockets.tool")

    def test_pocket_numbers_and_direction_checked(self):
        for field in ("min_circle_diameter", "depth", "min_floor"):
            for value in (0, -1, float("inf"), "8"):
                with self.subTest(field=field, value=value):
                    s = Settings.default()
                    setattr(s.pockets, field, value)
                    with self.assertRaises(SettingsError) as cm:
                        s.validate()
                    self.assertEqual(cm.exception.field, "pockets." + field)
        s = Settings.default()
        s.pockets.direction = "up"
        with self.assertRaises(SettingsError) as cm:
            s.validate()
        self.assertEqual(cm.exception.field, "pockets.direction")

    def test_partial_pockets_section_keeps_other_defaults(self):
        s = Settings.from_dict({"pockets": {"tool": 5}})
        self.assertEqual(s.pockets.tool, 5)
        d = Settings.default().pockets
        self.assertEqual((s.pockets.depth, s.pockets.direction), (d.depth, d.direction))

    def test_old_pocket_numbers_are_ignored(self):
        old = {"pockets": {"diameter": 12, "depth_per_pass": 4, "plunge_feed": 2, "cut_feed": 5,
                           "spindle_rpm": 12000, "stepover_pct": 0.4}}
        s = Settings.from_dict(old)
        self.assertEqual(s.pockets, Settings.default().pockets)
        self.assertNotIn("diameter", s.to_dict()["pockets"])
        s.validate()


if __name__ == "__main__":
    unittest.main()
