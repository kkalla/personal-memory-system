"""Reviewed restoration commands must preserve a conflicting destination."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


class Restoration(unittest.TestCase):
    def test_plain_mv_is_rejected_for_collision_despite_exit_zero(self):
        from validate_memory_restoration import check_restoration
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'archive').mkdir()
            (root/'config').mkdir()
            (root/'archive/item').write_text('original')
            result=check_restoration(root, [['mv','archive/item','config/item']], 'archive/item','config/item')
            self.assertTrue(result['absent']['pass'])
            self.assertFalse(result['collision']['pass'])
            self.assertEqual((root/'archive/item').read_text(),'original')
            self.assertFalse((root/'config/item').exists())

    def test_no_clobber_and_parent_creation_restore_safely(self):
        from validate_memory_restoration import check_restoration
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'archive').mkdir();(root/'archive/item').write_text('original')
            result=check_restoration(root,[['mkdir','-p','config'],['mv','-n','archive/item','config/item']], 'archive/item','config/item')
            self.assertTrue(result['absent']['pass'])
            self.assertTrue(result['collision']['pass'])
            self.assertFalse((root/'config').exists())

    def test_absolute_workspace_paths_are_relocated_only_in_copy(self):
        from validate_memory_restoration import check_restoration
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'archive').mkdir();(root/'config').mkdir()
            (root/'archive/item').write_text('original')
            commands=[['mv','-n',str(root/'archive/item'),str(root/'config/item')]]
            result=check_restoration(root,commands,'archive/item','config/item',relocate_workspace=True)
            self.assertTrue(result['absent']['pass'])
            self.assertTrue(result['collision']['pass'])
            self.assertFalse((root/'config/item').exists())
            self.assertEqual((root/'archive/item').read_text(),'original')


if __name__=='__main__':unittest.main()
