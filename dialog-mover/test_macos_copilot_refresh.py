import unittest
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from core import copilot_refresh_macos as native


class MacCopilotRefreshTests(unittest.TestCase):
    def test_fixture_mode_does_not_reenter_when_entry_module_is_imported(self):
        root=Path(__file__).resolve().parents[1]
        script="import sys;from pathlib import Path;p=Path(sys.argv[1]);sys.path[:0]=[str(p/'macos'),str(p/'dialog-mover'),str(p/'dialog-mover/vendor'),str(p/'auto-resume/src')];sys.argv=['fixture','--copilot-refresh-child','not-a-fixture'];import entry;print('import-only')"
        result=subprocess.run([sys.executable,'-c',script,str(root)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'import-only')
    def test_a_closed_app_needs_no_accessibility_or_process_restart(self):
        with patch.object(native,'_application',return_value=None),patch.object(native,'Accessibility') as ax:
            self.assertEqual(native.refresh(busy=lambda:'idle'),'not-running')
            ax.assert_not_called()

    def test_only_explicit_reload_labels_are_accepted(self):
        for name in ('Retry response','Restart app','Run task','Reload MCP servers','Reload current skill'):
            ax=Mock();ax.walk.return_value=[(1,'AXButton',())];ax.label.return_value=name
            self.assertIsNone(native._reload_command(ax,0))
        for name in ('Reload Window','Reload App','重新加载窗口'):
            ax=Mock();ax.walk.return_value=[(1,'AXMenuItem',())];ax.label.return_value=name
            self.assertEqual(native._reload_command(ax,0),1)

    def test_recent_document_titles_cannot_masquerade_as_native_commands(self):
        ax=Mock();ax.children.return_value=[1,2]
        ax.label.side_effect=lambda element:{1:'Apple',2:'File'}[element]
        self.assertIsNone(native._reload_menu(ax,0))
        self.assertIsNone(native._palette_menu(ax,0))
        ax.walk.assert_not_called()

    def test_an_unreadable_menu_never_supplies_a_command(self):
        ax=Mock();ax.children.return_value=[1,2];ax.label.side_effect=lambda element:{1:'View',2:'Developer'}[element]
        with patch.object(native,'_reload_command',side_effect=[native.Unavailable(),9]):
            self.assertEqual(native._reload_menu(ax,0),9)
        with patch.object(native,'_reload_command',side_effect=native.Unavailable()):
            self.assertIsNone(native._reload_menu(ax,0))

    def test_drafts_and_unreadable_editors_fail_closed_without_reading_history(self):
        for value,expected in (('synthetic draft',True),('',False),(None,None)):
            ax=Mock();ax.walk.return_value=[(1,'AXWebArea',()),(2,'AXStaticText',()),(3,'AXTextArea',())]
            ax.attribute.side_effect=lambda element,name: value if element==3 and name=='AXValue' else self.fail('History text must not be read')
            ax.text.side_effect=lambda item:item
            if expected is None:
                with self.assertRaises(native.Unavailable):native._draft(ax,0)
            else:self.assertEqual(native._draft(ax,0),expected)

    def test_an_unsent_attachment_is_not_treated_as_an_empty_draft(self):
        ax=Mock();ax.walk.return_value=[(1,'AXWebArea',()),(2,'AXButton',())]
        ax.label.return_value='Remove attachment'
        self.assertTrue(native._draft(ax,0))

    def test_native_text_editor_is_a_leaf_even_when_webkit_rejects_children(self):
        ax=native.Accessibility.__new__(native.Accessibility)
        ax.attribute=lambda element,name:'AXTextArea' if name=='AXRole' else self.fail('No editor child query')
        ax.text=lambda value:value
        ax.children=Mock(side_effect=native.Unavailable('attribute_AXChildren_-25200'))
        self.assertEqual(list(ax.walk(1)),[(1,'AXTextArea',())]);ax.children.assert_not_called()

    def fake(self):
        ax=Mock();ax.__enter__=Mock(return_value=ax);ax.__exit__=Mock(return_value=False)
        ax.owned=[];ax.ax.AXIsProcessTrusted.return_value=True;ax.children.return_value=[1]
        app=Mock();app.processIdentifier.return_value=123;app.isTerminated.return_value=False
        front=SimpleNamespace(processIdentifier=lambda:123)
        kit=SimpleNamespace(NSWorkspace=SimpleNamespace(sharedWorkspace=lambda:SimpleNamespace(frontmostApplication=lambda:front)))
        return ax,app,kit

    def test_permission_draft_and_busy_never_press_any_command(self):
        for trusted,draft,state,expected in ((False,False,'idle','permission-required'),
                (True,True,'idle','draft'),(True,False,'busy','busy'),(True,False,'unavailable','unavailable')):
            ax,app,kit=self.fake();ax.ax.AXIsProcessTrusted.return_value=trusted
            with patch.object(native,'Accessibility',return_value=ax),patch.object(native,'_application',return_value=app), \
                    patch.object(native,'_draft',return_value=draft):
                self.assertEqual(native.refresh(busy=lambda:state),expected)
            ax.press.assert_not_called();ax.set_text.assert_not_called();app.activateWithOptions_.assert_not_called()

    def test_a_draft_or_task_appearing_after_activation_blocks_reload(self):
        for drafts,states,expected in (([False,True],['idle'],'draft'),([False,False],['idle','busy'],'busy')):
            ax,app,kit=self.fake()
            with patch.object(native,'Accessibility',return_value=ax),patch.object(native,'_application',return_value=app), \
                    patch.object(native,'_draft',side_effect=drafts),patch.object(native,'_reload_menu',return_value=9), \
                    patch.dict('sys.modules',{'AppKit':kit}):
                self.assertEqual(native.refresh(busy=Mock(side_effect=states)),expected)
            ax.press.assert_not_called()

    def test_verified_empty_idle_window_uses_named_native_action_once(self):
        ax,app,kit=self.fake()
        with patch.object(native,'Accessibility',return_value=ax),patch.object(native,'_application',return_value=app), \
                patch.object(native,'_draft',return_value=False),patch.object(native,'_reload_menu',return_value=9), \
                patch.dict('sys.modules',{'AppKit':kit}):
            self.assertEqual(native.refresh(busy=lambda:'idle'),'requested')
        ax.press.assert_called_once_with(9);ax.set_text.assert_not_called()


if __name__=='__main__':unittest.main()
