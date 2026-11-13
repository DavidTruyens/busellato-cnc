import copy
import unittest

from nesting.tools import (HEADS, ROUTER_HEADS, DRILL_HEADS, Bit, ToolTable, HeadError,
                           SettingsError, STEPOVER_MESSAGE, migrate, OBSOLETE_GROUP_FIELDS)


def table(**over):
    d = ToolTable.default().to_dict()
    d.update(over)
    return d


def field_of(test, d):
    with test.assertRaises(SettingsError) as cm:
        ToolTable.from_dict(d).validate()
    return cm.exception


class Heads(unittest.TestCase):
    def test_heads_list(self):
        self.assertEqual(sorted(HEADS), list(range(1, 31)) + [53, 56, 60, 61, 65, 66])
        self.assertEqual(HEADS[66].allows, ('router',))
        self.assertEqual(HEADS[1].allows, ('drill',))
        self.assertEqual(HEADS[60].allows, ('drill', 'blade'))
        self.assertEqual(ROUTER_HEADS, (65, 66))
        self.assertEqual(DRILL_HEADS, tuple(range(1, 31)))


class Table(unittest.TestCase):
    def test_default_table(self):
        t = ToolTable.default()
        self.assertEqual([b.id for b in t.bits], ['b1', 'b2', 'b3'])
        b1, b2, b3 = t.bits
        self.assertEqual((b1.name, b1.type, b1.diameter, b1.spindle_rpm, b1.plunge_feed,
                          b1.cut_feed, b1.depth_per_pass, b1.stepover_pct),
                         ('Router 8', 'router', 8, 18000, 1, 3, 9, 40))
        self.assertEqual((b2.name, b2.type, b2.diameter, b2.plunge_feed), ('Drill 6', 'drill', 6, 1))
        self.assertEqual((b3.name, b3.type, b3.diameter, b3.plunge_feed), ('Drill 3', 'drill', 3, 1))
        self.assertIsNone(b2.spindle_rpm)
        self.assertEqual(t.heads, {66: 'b1', 1: 'b2', 2: 'b3'})
        t.validate()

    def test_roundtrip(self):
        t = ToolTable.default()
        d = t.to_dict()
        self.assertEqual(ToolTable.from_dict(d), t)
        self.assertEqual(d['heads'], {'T1': 'b2', 'T2': 'b3', 'T66': 'b1'})
        self.assertEqual(list(d['heads']), ['T1', 'T2', 'T66'])
        drill = d['bits'][1]
        for k in ('cut_feed', 'depth_per_pass', 'stepover_pct', 'spindle_rpm'):
            self.assertNotIn(k, drill)

    def test_bad_tables_are_refused_naming_the_head(self):
        base = ToolTable.default().to_dict()

        def with_heads(**h):
            d = copy.deepcopy(base)
            d['heads'] = h
            return d

        e = field_of(self, with_heads(T66='b9'))
        self.assertEqual(e.field, 'tools.heads.T66')
        self.assertIn('b9', str(e))
        e = field_of(self, with_heads(T1='b1'))
        self.assertEqual(e.field, 'tools.heads.T1')
        self.assertIn('T1', str(e))
        self.assertIn('router', str(e))
        e = field_of(self, with_heads(T70='b1'))
        self.assertEqual(e.field, 'tools.heads.T70')
        self.assertIn('not a machine head', str(e))
        d = copy.deepcopy(base)
        d['bits'] = {}
        self.assertEqual(field_of(self, d).field, 'tools.bits')
        self.assertEqual(field_of(self, []).field, 'tools')
        d = copy.deepcopy(base)
        d['heads'] = []
        self.assertEqual(field_of(self, d).field, 'tools.heads')
        d = copy.deepcopy(base)
        d['bits'].append(dict(d['bits'][1]))
        self.assertEqual(field_of(self, d).field, 'tools.bits')

    def test_bit_values_checked(self):
        def bad(index, **over):
            d = ToolTable.default().to_dict()
            d['bits'][index].update(over)
            return field_of(self, d)

        self.assertEqual(bad(0, diameter=0).field, 'tools.bits.b1.diameter')
        e = bad(0, stepover_pct=5)
        self.assertEqual(e.field, 'tools.bits.b1.stepover_pct')
        self.assertEqual(e.message, STEPOVER_MESSAGE)
        d = ToolTable.default().to_dict()
        del d['bits'][1]['plunge_feed']
        self.assertEqual(field_of(self, d).field, 'tools.bits.b2.plunge_feed')
        d = ToolTable.default().to_dict()
        d['bits'][1]['spindle_rpm'] = 12000
        ToolTable.from_dict(d).validate()
        self.assertEqual(bad(1, spindle_rpm=0).field, 'tools.bits.b2.spindle_rpm')
        self.assertEqual(bad(0, name='').field, 'tools.bits.b1.name')
        self.assertEqual(bad(0, name='x' * 41).field, 'tools.bits.b1.name')
        self.assertEqual(bad(0, type='saw').field, 'tools.bits.b1.type')
        self.assertEqual(bad(0, diameter=True).field, 'tools.bits.b1.diameter')
        self.assertEqual(bad(0, cut_feed=float('nan')).field, 'tools.bits.b1.cut_feed')
        self.assertEqual(bad(0, cut_feed=float('inf')).field, 'tools.bits.b1.cut_feed')
        d = ToolTable.default().to_dict()
        d['bits'][0]['id'] = 'b 1'
        d['heads']['T66'] = 'b 1'
        self.assertEqual(field_of(self, d).field, 'tools.bits.b 1.id')

    def test_unhashable_json_values_are_field_errors(self):
        d = ToolTable.default().to_dict()
        d['bits'][0]['id'] = {}
        self.assertEqual(field_of(self, d).field, 'tools.bits')
        d = ToolTable.default().to_dict()
        d['bits'][0]['type'] = []
        self.assertEqual(field_of(self, d).field, 'tools.bits.b1.type')
        d = ToolTable.default().to_dict()
        d['bits'][0]['id'] = []
        self.assertEqual(field_of(self, d).field, 'tools.bits')
        t = ToolTable([Bit({}, 'x', 'drill', 6, plunge_feed=1)], {})
        with self.assertRaises(SettingsError) as cm:
            t.validate()
        self.assertEqual(cm.exception.field, 'tools.bits')
        t = ToolTable([Bit('b1', 'x', [], 6)], {})
        with self.assertRaises(SettingsError) as cm:
            t.validate()
        self.assertEqual(cm.exception.field, 'tools.bits.b1.type')
        t.to_dict()

    def test_blade_optional_fields(self):
        t = ToolTable([Bit('k1', 'Blade', 'blade', 100)], {60: 'k1'})
        t.validate()
        self.assertEqual(ToolTable.from_dict(t.to_dict()), t)

    def test_resolve(self):
        t = ToolTable.default()
        self.assertEqual(t.resolve(66, 'router', 'router.tool', 'router').id, 'b1')
        with self.assertRaises(HeadError) as cm:
            t.resolve(65, 'router', 'router.tool', 'router')
        self.assertEqual(cm.exception.field, 'router.tool')
        self.assertEqual(cm.exception.message, 'router: head T65 holds no bit')
        with self.assertRaises(HeadError) as cm:
            t.resolve(1, 'router', 'router.tool', 'router')
        self.assertIn('T1', cm.exception.message)
        self.assertIn('router uses T65 or T66', cm.exception.message)
        with self.assertRaises(HeadError) as cm:
            t.resolve(53, 'fixing drill', 'drill_fix.tool', 'drill')
        self.assertIn('programs do not use T53', cm.exception.message)
        with self.assertRaises(HeadError) as cm:
            t.resolve(40, 'fixing drill', 'drill_fix.tool', 'drill')
        self.assertIn('T40 is not a machine head', cm.exception.message)
        with self.assertRaises(HeadError) as cm:
            t.resolve(65, 'fixing drill', 'drill_fix.tool', 'drill')
        self.assertIn('drills use T1 to T30', cm.exception.message)
        self.assertTrue(cm.exception.message.startswith('fixing drill: '))
        self.assertEqual(t.resolve(2, 'screw drill', 'drill_screw.tool', 'drill').id, 'b3')

    def test_resolve_wrong_type(self):
        t = ToolTable.default()
        t.heads[65] = 'b2'   # not validated: resolve still checks the bit type
        with self.assertRaises(HeadError) as cm:
            t.resolve(65, 'router', 'router.tool', 'router')
        self.assertIn('holds drill bit Drill 6; the router needs a router bit',
                      cm.exception.message)

    def test_label_and_used_in(self):
        t = ToolTable.default()
        self.assertEqual(t.label(66), 'T66 Router 8')
        self.assertEqual(t.label(65), 'T65 (empty)')
        self.assertEqual(t.heads_of('b1'), [66])
        self.assertEqual(t.new_id(), 'b4')
        self.assertEqual(t.bit('b2').name, 'Drill 6')
        self.assertIsNone(t.bit('zz'))
        self.assertEqual(t.bit_in(1).id, 'b2')
        self.assertIsNone(t.bit_in(65))
        t.bits.pop(0)
        self.assertEqual(t.new_id(), 'b1')


class Migrate(unittest.TestCase):
    def test_old_defaults_give_the_default_table(self):
        t, notes, ignored = migrate({}, {})
        self.assertEqual(t, ToolTable.default())
        self.assertEqual(ignored, [])
        self.assertEqual(len(notes), 1)
        self.assertIn('T66', notes[0])
        self.assertIn('depth per pass', notes[0])
        self.assertIn('9', notes[0])
        self.assertIn('4', notes[0])
        t.validate()

    def test_real_project_shape(self):
        settings = {
            'router': {'tool': 66, 'diameter': 8, 'spindle_rpm': 18000, 'plunge_feed': 1,
                       'cut_feed': 2, 'depth_per_pass': 9},
            'pockets': {'tool': 66, 'diameter': 8, 'cut_feed': 3, 'depth_per_pass': 4,
                        'stepover_pct': 40},
            'drill_fix': {'tool': 10, 'diameter': 5, 'feed': 1},
            'drill_screw': {'tool': 10, 'diameter': 5, 'feed': 1},
        }
        t, notes, ignored = migrate(settings, {})
        r = t.bit_in(66)
        self.assertEqual((r.name, r.type, r.diameter, r.cut_feed, r.depth_per_pass,
                          r.stepover_pct), ('Router 8', 'router', 8, 2, 9, 40))
        d = t.bit_in(10)
        self.assertEqual((d.name, d.type, d.diameter, d.plunge_feed), ('Drill 5', 'drill', 5, 1))
        self.assertIsNone(t.bit_in(1))
        self.assertIsNone(t.bit_in(2))
        self.assertEqual([b.id for b in t.bits], ['b1', 'b2'])
        self.assertEqual(len(notes), 1)
        n = notes[0]
        self.assertIn('T66', n)
        self.assertIn('cut feed 2', n)
        self.assertIn('cut feed 3', n)
        self.assertIn('depth per pass 9', n)
        self.assertIn('depth per pass 4', n)
        t.validate()

    def test_pocket_default_on_its_own_head(self):
        t, notes, _ = migrate({'pockets': {'tool': 65, 'diameter': 18, 'depth_per_pass': 5,
                                           'cut_feed': 2, 'stepover_pct': 30}}, {})
        b = t.bit_in(65)
        self.assertEqual((b.name, b.type, b.diameter, b.depth_per_pass, b.cut_feed,
                          b.stepover_pct), ('Router 18', 'router', 18, 5, 2, 30))
        self.assertEqual(t.bit_in(66).name, 'Router 8')
        self.assertEqual(t.bit_in(66).depth_per_pass, 9)
        self.assertEqual(notes, [])
        t.validate()

    def test_two_drills_one_head_disagree(self):
        t, notes, _ = migrate({'drill_fix': {'tool': 3, 'diameter': 6},
                               'drill_screw': {'tool': 3, 'diameter': 4}}, {})
        b = t.bit_in(3)
        self.assertEqual((b.name, b.diameter), ('Drill 6', 6))
        self.assertEqual(len([x for x in t.bits if x.type == 'drill']), 1)
        t3 = [n for n in notes if n.startswith('T3 ')]   # the other note is the T66 default
        self.assertEqual(len(t3), 1)
        self.assertIn('diameter 6', t3[0])
        self.assertIn('diameter 4', t3[0])
        t.validate()

    def test_unusable_head_is_not_placed(self):
        t, notes, _ = migrate({'pockets': {'tool': 7}}, {})
        self.assertIsNone(t.bit_in(7))
        self.assertEqual(sorted(t.heads), [1, 2, 66])
        self.assertEqual(len(t.bits), 4)
        self.assertEqual(t.bits[1].type, 'router')
        self.assertTrue(any("pocket default's head T7 cannot hold a router bit" in n
                            for n in notes))
        t.validate()
        t, notes, _ = migrate({'drill_fix': {'tool': 40}}, {})
        self.assertIsNone(t.bit_in(40))
        self.assertEqual(len(t.bits), 3)
        self.assertTrue(any('T40' in n and 'drill' in n for n in notes))
        t.validate()

    def test_ignored_overrides(self):
        _, _, ignored = migrate({}, {'k1': {'diameter': 12, 'depth': 6, 'tool': 65},
                                     'k2': 'junk', 'k3': None})
        self.assertEqual(ignored, [('k1', 'diameter', 12)])
        self.assertEqual(OBSOLETE_GROUP_FIELDS, ('diameter', 'depth_per_pass', 'plunge_feed',
                                                 'cut_feed', 'spindle_rpm', 'stepover_pct'))
        _, _, ign = migrate({}, 'not a dict')
        self.assertEqual(ign, [])

    def test_non_numeric_value_takes_default_and_says_so(self):
        t, notes, _ = migrate({'router': {'cut_feed': 'fast'}}, {})
        self.assertEqual(t.bit_in(66).cut_feed, 3)
        self.assertTrue(any('cut feed' in n and 'not a number' in n for n in notes))

    def test_migration_is_deterministic(self):
        s = {'router': {'cut_feed': 2}, 'pockets': {'tool': 7}, 'drill_fix': {'tool': 3}}
        p = {'k': {'diameter': 1}}
        a, b = migrate(copy.deepcopy(s), copy.deepcopy(p)), migrate(copy.deepcopy(s),
                                                                    copy.deepcopy(p))
        self.assertEqual(a, b)


if __name__ == '__main__':
    unittest.main()
