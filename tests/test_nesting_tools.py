import copy
import unittest

from nesting.tools import (HEADS, ROUTER_HEADS, DRILL_HEADS, Bit, ToolTable, HeadError,
                           SettingsError, STEPOVER_MESSAGE)


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


if __name__ == '__main__':
    unittest.main()
