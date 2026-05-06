"""
Tests for summer_program constants
"""
import unittest
from tap_lms.summer_program.constants import (
    collection_label,
    ALL_ARCHETYPES,
    ALL_ARMS,
    ARM_A,
    ARM_B,
    ARCHETYPE_DORMANT,
    ARCHETYPE_SUBMITTER,
    ACTION_FLOW_FIELD_MAP,
    COLLECTION_ACTIONS,
    PER_STUDENT_ACTIONS,
    BPR_STATUS_FLOW,
)


class TestConstants(unittest.TestCase):

    def test_collection_label_format(self):
        label = collection_label("BT001", ARCHETYPE_DORMANT, ARM_A)
        self.assertEqual(label, "SP_BT001_dormant_arm_a")

    def test_collection_label_submitter_arm_b(self):
        label = collection_label("BT002", ARCHETYPE_SUBMITTER, ARM_B)
        self.assertEqual(label, "SP_BT002_submitter_arm_b")

    def test_all_archetypes_count(self):
        self.assertEqual(len(ALL_ARCHETYPES), 4)

    def test_all_arms_count(self):
        self.assertEqual(len(ALL_ARMS), 3)  # default, arm_a, arm_b

    def test_action_flow_field_map_covers_all_actions(self):
        all_actions = COLLECTION_ACTIONS + PER_STUDENT_ACTIONS
        for action in all_actions:
            self.assertIn(action, ACTION_FLOW_FIELD_MAP)

    def test_bpr_status_flow_order(self):
        self.assertEqual(BPR_STATUS_FLOW[0], "draft")
        self.assertEqual(BPR_STATUS_FLOW[-1], "completed")

    def test_8_collections_generated(self):
        """4 archetypes × 2 arms = 8 archetype collections"""
        labels = set()
        for arch in ALL_ARCHETYPES:
            for arm in [ARM_A, ARM_B]:
                labels.add(collection_label("TEST", arch, arm))
        self.assertEqual(len(labels), 8)


if __name__ == "__main__":
    unittest.main()
