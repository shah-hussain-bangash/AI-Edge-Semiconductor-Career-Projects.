"""Service-plan checks only: no user LaunchAgent is installed or loaded."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import plistlib,tempfile,unittest
from unittest.mock import patch
import mac_service


class ServicePlanTests(unittest.TestCase):
    def test_plan_starts_only_dashboard_with_no_usb_connect_or_secrets(self):
        plan=plistlib.loads(mac_service.render('/Users/fixture/edgeops home'))
        self.assertNotIn('--connect',plan['ProgramArguments']);self.assertNotIn('--reconnect',plan['ProgramArguments'])
        self.assertEqual(plan['ProgramArguments'][-1],'8878');self.assertTrue(plan['RunAtLoad'])
        self.assertEqual(plan['KeepAlive'],{'SuccessfulExit':False})
        self.assertEqual(set(plan['EnvironmentVariables']),{'PYTHONDONTWRITEBYTECODE'})
        self.assertIn('edgeops home',plan['WorkingDirectory'])
    def test_different_checkouts_have_distinct_labels_and_files_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';other=Path(tmp)/'other'
            self.assertNotEqual(mac_service.job(root)['Label'],mac_service.job(other)['Label'])
            path=Path(tmp)/'service.plist';path.write_bytes(mac_service.render(root));mac_service.checked_file(path,root)
            before=path.read_bytes()
            with self.assertRaises(ValueError):mac_service.checked_file(path,other)
            self.assertEqual(path.read_bytes(),before)
    def test_non_mac_actions_refused_before_launchctl_or_file_changes(self):
        with patch('mac_service.sys.platform','win32'),patch('mac_service.run_launchctl') as run:
            with self.assertRaises(ValueError):mac_service.main(['install'])
            run.assert_not_called()

if __name__=='__main__':unittest.main()
