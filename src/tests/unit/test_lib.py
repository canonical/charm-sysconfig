#!/usr/bin/python3
"""Unit tests for SysConfigHelper and BootResourceState classes."""
import subprocess
import unittest
import unittest.mock as mock
from datetime import datetime, timedelta, timezone
from tempfile import NamedTemporaryFile
from unittest.mock import Mock

import lib_sysconfig
import pytest


@mock.patch("filecmp.cmp")
@mock.patch("lib_sysconfig.subprocess.check_output")
def test_check_update_grub_error(check_output, cmp_file):
    """Test check_update_grub function when error occurs."""
    tmp_output = "/tmp/tmp_grub.cfg"

    check_output.side_effect = subprocess.CalledProcessError(1, "grub-mkconfig")
    update_available, message = lib_sysconfig.check_update_grub(tmp_output)
    assert update_available is False
    assert "Unable to check update-grub" in message


class TestCheckUpdateGrub(unittest.TestCase):
    @mock.patch(
        "builtins.open", new_callable=mock.mock_open, read_data="original grub content"
    )
    @mock.patch("lib_sysconfig.subprocess.check_output")
    @mock.patch("lib_sysconfig._replace_refs_with_device_names")
    def test_check_update_grub(
        self,
        replace_refs_with_device_names,
        check_output,
        mock_open,
    ):
        """Test check_update_grub function when grub update is available."""
        tmp_output = "/tmp/tmp_grub.cfg"

        def replace_refs(content):
            content = content.replace(
                "root=UUID=b5d8d38f-33ef-49e0-81f1-f30060511872",
                "root=DEVICE=nvme0n1p2",
            )
            content = content.replace(
                "root=LABEL=cloudimg-rootfs",
                "root=DEVICE=nvme0n1p2",
            )
            return content

        replace_refs_with_device_names.side_effect = replace_refs

        mock_open.side_effect = [
            mock.mock_open(
                read_data=(
                    "linux /boot/vmlinuz-5.15.0-91-generic\n"
                    "root=UUID=b5d8d38f-33ef-49e0-81f1-f30060511872\n"
                    "ro console=tty1 console=ttyS0\n"
                    "initrd /boot/initrd.img-5.15.0-91-generic"
                )
            ).return_value,
            mock.mock_open(
                read_data=(
                    "linux /boot/vmlinuz-5.15.0-91-generic\n"
                    "root=LABEL=cloudimg-rootfs ro console=tty1 console=ttyS0\n"
                    "initrd /boot/initrd.img-5.15.0-91-generic"
                )
            ).return_value,
            mock.mock_open().return_value,
        ]

        update_available, message = lib_sysconfig.check_update_grub(tmp_output)
        self.assertTrue(update_available)
        self.assertIn("Found available grub updates.", message)

    @mock.patch(
        "builtins.open", new_callable=mock.mock_open, read_data="original grub content"
    )
    @mock.patch("subprocess.check_output")
    @mock.patch("os.readlink", return_value="/dev/nvme0n1p2")
    @mock.patch("os.path.basename", return_value="nvme0n1p2")
    def test_check_update_grub_no_update(
        self, mock_basename, mock_readlink, mock_check_output, mock_open
    ):
        """Test check_update_grub function when no grub update is available."""
        tmp_output = "/tmp/tmp_grub.cfg"

        mock_open.side_effect = [
            mock.mock_open(
                read_data=(
                    "linux /boot/vmlinuz-5.15.0-91-generic\n"
                    "root=UUID=b5d8d38f-33ef-49e0-81f1-f30060511872\n"
                    "ro console=tty1 console=ttyS0\n"
                    "initrd /boot/initrd.img-5.15.0-91-generic"
                )
            ).return_value,
            mock.mock_open(
                read_data=(
                    "linux /boot/vmlinuz-5.15.0-91-generic\n"
                    "root=LABEL=cloudimg-rootfs\n"
                    "ro console=tty1 console=ttyS0\n"
                    "initrd /boot/initrd.img-5.15.0-91-generic"
                )
            ).return_value,
        ]

        update_available, message = lib_sysconfig.check_update_grub(tmp_output)
        self.assertFalse(update_available)
        self.assertIn("No available grub updates found.", message)

    @mock.patch("os.readlink", return_value="/dev/nvme0n1p2")
    @mock.patch("os.path.basename", return_value="nvme0n1p2")
    def test_replace_refs_with_device_names_uuid(self, mock_basename, mock_readlink):
        """Test _replace_refs_with_device_names helper function for UUID."""
        content = (
            "linux /boot/vmlinuz-5.15.0-91-generic\n"
            "root=UUID=b5d8d38f-33ef-49e0-81f1-f30060511872\n"
            "ro console=tty1 console=ttyS0\n"
            "initrd /boot/initrd.img-5.15.0-91-generic"
        )

        result = lib_sysconfig._replace_refs_with_device_names(content)

        expected_result = (
            "linux /boot/vmlinuz-5.15.0-91-generic\n"
            "root=DEVICE=nvme0n1p2\n"
            "ro console=tty1 console=ttyS0\n"
            "initrd /boot/initrd.img-5.15.0-91-generic"
        )

        self.assertEqual(result, expected_result)

    @mock.patch("os.readlink", return_value="/dev/nvme0n1p2")
    @mock.patch("os.path.basename", return_value="nvme0n1p2")
    def test_replace_refs_with_device_names_label(self, mock_basename, mock_readlink):
        """Test _replace_refs_with_device_names helper function for LABEL."""
        content = (
            "linux /boot/vmlinuz-5.15.0-91-generic\n"
            "root=LABEL=cloudimg-rootfs\n"
            "ro console=tty1 console=ttyS0\n"
            "initrd /boot/initrd.img-5.15.0-91-generic"
        )

        result = lib_sysconfig._replace_refs_with_device_names(content)

        expected_result = (
            "linux /boot/vmlinuz-5.15.0-91-generic\n"
            "root=DEVICE=nvme0n1p2\n"
            "ro console=tty1 console=ttyS0\n"
            "initrd /boot/initrd.img-5.15.0-91-generic"
        )

        self.assertEqual(result, expected_result)


@pytest.mark.parametrize(
    "config_flags, expected",
    [
        ("key1=val1,key2=val2", {"key1": "val1", "key2": "val2"}),
        # whitespace between key value pairs after comma
        ("key1=val1,  key2=val2", {"key1": "val1", "key2": "val2"}),
        # multiple values assigned to key
        ("key1=val1,val2,key2=val3", {"key1": "val1,val2", "key2": "val3"}),
        ("key1=val1 val2 val3", {"key1": "val1 val2 val3"}),
        # Subkey assigned to key has a single value (val) assigned with "="
        ('key="$key subkey=val"', {"key": '"$key subkey=val"'}),
        (
            'key1="subkey1=val1 val2",key2="$key2 val3"',
            {"key1": '"subkey1=val1 val2"', "key2": '"$key2 val3"'},
        ),
        # Subkey has multiple values (val1, val2) assigned each separated by comma
        (
            'key1="subkey1=val1,val2 subkey2=val3",key2=val4',
            {"key1": '"subkey1=val1,val2 subkey2=val3"', "key2": "val4"},
        ),
        (
            'key1="$key1 subkey1=val1,val2 subkey2=val3", key2=val4',
            {"key1": '"$key1 subkey1=val1,val2 subkey2=val3"', "key2": "val4"},
        ),
        (
            (
                'key1="$key1 subkey1=val1,val2 subkey2=val3", key2="$key2 '
                'subkey1=val1 subkey2=val2"'
            ),
            {
                "key1": '"$key1 subkey1=val1,val2 subkey2=val3"',
                "key2": '"$key2 subkey1=val1 subkey2=val2"',
            },
        ),
    ],
)
def test_parse_config_flags(config_flags, expected):
    """Test parsing function for config flags."""
    assert lib_sysconfig.parse_config_flags(config_flags) == expected


class TestBootResourceState:
    """Test BootResourceState class."""

    @property
    def datetime(self):
        """Return a datetime object."""
        return datetime(2019, 1, 1, tzinfo=timezone.utc)

    def boot_resource(self):
        """Mock unitdata.kv()."""
        db = mock.MagicMock()

        def fake_db_get(key):
            if key.endswith("sha256sum"):
                return "1234"
            else:
                return self.datetime.timestamp()

        db.get.side_effect = fake_db_get
        return lib_sysconfig.BootResourceState(db=db)

    @mock.patch("lib_sysconfig.datetime")
    def test_set_resource(self, mock_datetime):
        """Test updating resource entry in the db."""
        test_time = self.datetime
        mock_datetime.now.return_value = test_time
        boot_resource = self.boot_resource()
        boot_resource.set_resource("foofile")
        assert boot_resource.db.set.call_count == 1
        set_args = boot_resource.db.set.call_args[0]
        assert set_args[0] == "sysconfig.boot_resource.foofile"
        dt = datetime.fromtimestamp(set_args[1], timezone.utc)
        assert dt == test_time

    def test_get_resource(self):
        """Test retrieving timestamp of last resource update."""
        test_time = self.datetime
        boot_resource = self.boot_resource()
        timestamp = boot_resource.get_resource_changed_timestamp("foofile")
        assert timestamp == test_time

    def test_get_unknown_resource(self):
        """Test retrieving timestamp of resource not in the db.

        time.now is returned.
        """
        boot_resource = self.boot_resource()
        boot_resource.db = dict()  # plant empty dataset
        timestamp = boot_resource.get_resource_changed_timestamp("unregfile")
        assert timestamp == datetime.min.replace(tzinfo=timezone.utc)

    @mock.patch("lib_sysconfig.boot_time")
    def test_resources_changed_since_dawn_of_time(self, mock_boot_time):
        """Test retrieving of resources changed since last boot."""
        mock_boot_time.return_value = datetime.min.replace(tzinfo=timezone.utc)
        boot_resource = self.boot_resource()
        with NamedTemporaryFile() as ftmp:
            changed = boot_resource.resources_changed_since_boot([ftmp.name])
            assert len(changed) == 1
            assert changed[0] == ftmp.name

    @mock.patch("lib_sysconfig.boot_time")
    def test_resources_not_changed(self, mock_boot_time):
        """Test resource is not changed since last boot."""
        mock_boot_time.return_value = self.datetime
        boot_resource = self.boot_resource()
        with NamedTemporaryFile() as ftmp:
            changed = boot_resource.resources_changed_since_boot([ftmp.name])
            assert not changed

    @mock.patch("lib_sysconfig.boot_time")
    def test_resources_time_changed_contents_no_change(self, mock_boot_time):
        """Test resource is not changed since last boot."""
        mock_boot_time.return_value = self.datetime - timedelta(1)
        boot_resource = self.boot_resource()
        with NamedTemporaryFile() as ftmp:
            with mock.patch.object(
                boot_resource, "calculate_resource_sha256sum"
            ) as mock_calc:
                mock_calc.return_value = "1234"
                changed = boot_resource.resources_changed_since_boot([ftmp.name])
                assert not changed

    @mock.patch("lib_sysconfig.boot_time")
    def test_resources_time_changed_contents_changed(self, mock_boot_time):
        """Test resource is not changed since last boot."""
        mock_boot_time.return_value = self.datetime - timedelta(1)
        boot_resource = self.boot_resource()
        with NamedTemporaryFile() as ftmp:
            with mock.patch.object(
                boot_resource, "calculate_resource_sha256sum"
            ) as mock_calc:
                mock_calc.return_value = "2345"
                changed = boot_resource.resources_changed_since_boot([ftmp.name])
                assert changed

    @mock.patch("lib_sysconfig.clear_notification_time")
    @mock.patch("lib_sysconfig.boot_time")
    def test_resources_changed_before_clear_notification(
        self, mock_boot_time, mock_clear_notification_time
    ):
        """Test resources change happened before `clear-notifications` action run."""
        mock_boot_time.return_value = self.datetime - timedelta(1)
        mock_clear_notification_time.return_value = self.datetime + timedelta(1)
        boot_resource = self.boot_resource()
        with NamedTemporaryFile() as ftmp:
            with mock.patch.object(
                boot_resource, "calculate_resource_sha256sum"
            ) as mock_calc:
                mock_calc.return_value = "2345"
                changed = boot_resource.resources_changed_since_boot([ftmp.name])
                assert not changed


class TestLib:
    """Module to test SysConfigHelper lib."""

    def test_pytest(self):
        """Assert testing is carryied using pytest."""
        assert True

    def test_sysconfig(self, sysconfig):
        """See if the helper fixture works to load charm configs."""
        assert isinstance(sysconfig.charm_config, dict)

    @mock.patch("lib_sysconfig.subprocess.call")
    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.host.service_restart")
    @mock.patch("lib_sysconfig.render")
    def test_update_cpufreq(self, render, restart, config, check_call):
        """Set config governor=performance.

        Expect /etc/default/cpufrequtils is rendered
        and ondemand init script removed
        """
        expected = {"governor": "performance"}
        config.return_value = expected
        sysh = lib_sysconfig.SysConfigHelper()
        sysh.update_cpufreq()
        render.assert_called_with(
            source=lib_sysconfig.CPUFREQUTILS_TMPL,
            target=lib_sysconfig.CPUFREQUTILS,
            templates_dir="templates",
            context=expected,
        )
        check_call.assert_called_with(
            ["/bin/systemctl", "mask", "ondemand"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @mock.patch("lib_sysconfig.subprocess.call")
    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.host.service_restart")
    @mock.patch("lib_sysconfig.render")
    def test_update_cpufreq_governor_default(self, render, restart, config, check_call):
        """Set config governor=''.

        Expect /etc/default/cpufrequtils is rendered with no governor
        and ondemand init script is installed
        """
        expected = {"governor": ""}
        config.return_value = expected
        sysh = lib_sysconfig.SysConfigHelper()
        sysh.update_cpufreq()
        render.assert_called_with(
            source=lib_sysconfig.CPUFREQUTILS_TMPL,
            target=lib_sysconfig.CPUFREQUTILS,
            templates_dir="templates",
            context=expected,
        )
        restart.assert_called()
        check_call.assert_called_with(
            ["/bin/systemctl", "unmask", "ondemand"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @mock.patch("lib_sysconfig.subprocess.call")
    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.host.service_restart")
    @mock.patch("lib_sysconfig.render")
    def test_update_cpufreq_governor_not_available(
        self, render, restart, config, check_call
    ):
        """Set wrong governor.

        Expect /etc/default/cpufrequtils is not rendered
        """
        expected = {"governor": "wrong"}
        config.return_value = expected
        sysh = lib_sysconfig.SysConfigHelper()
        sysh.update_cpufreq()
        render.assert_not_called()
        restart.assert_not_called()
        check_call.assert_not_called()

    @mock.patch("lib_sysconfig.host.is_container")
    @mock.patch("lib_sysconfig.subprocess.check_call")
    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.hookenv.log")
    @mock.patch("lib_sysconfig.render")
    def test_update_grub_file(self, render, log, config, check_call, is_container):
        """Update /etc/default/grub.d/90-sysconfig.cfg and update-grub true.

        Expect file is rendered with correct config and updated-grub is called.
        """
        is_container.return_value = False
        config.return_value = {
            "reservation": "off",
            "isolcpus": "0-10",
            "hugepages": "400",
            "hugepagesz": "1G",
            "default-hugepagesz": "1G",
            "raid-autodetection": "noautodetect",
            "enable-pti": "on",
            "enable-iommu": True,
            "enable-tsx": True,
            "grub-config-flags": 'TEST_KEY="TEST VALUE, WITH COMMA", GRUB_TIMEOUT=0',
            "kernel-version": "4.15.0-38-generic",
            "update-grub": True,
        }

        expected = {
            "isolcpus": "0-10",
            "hugepages": "400",
            "hugepagesz": "1G",
            "default_hugepagesz": "1G",
            "raid": "noautodetect",
            "iommu": True,
            "enable_pti": "on",
            "tsx": True,
            "grub_config_flags": {
                "GRUB_TIMEOUT": "0",
                "TEST_KEY": '"TEST VALUE, WITH COMMA"',
            },
            "grub_default": "Advanced options for Ubuntu>Ubuntu, "
            "with Linux 4.15.0-38-generic",
        }

        sysh = lib_sysconfig.SysConfigHelper()
        sysh.update_grub_file()
        render.assert_called_with(
            source=lib_sysconfig.GRUB_CONF_TMPL,
            target=lib_sysconfig.GRUB_CONF,
            templates_dir="templates",
            context=expected,
        )
        check_call.assert_called()

    @mock.patch("lib_sysconfig.host.is_container")
    @mock.patch("lib_sysconfig.subprocess.check_call")
    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.hookenv.log")
    @mock.patch("lib_sysconfig.render")
    def test_grub_legacy_reservation(
        self, render, log, config, check_call, is_container
    ):
        """Update /etc/default/grub.d/90-sysconfig.cfg and update-grub true.

        Expect file is rendered with correct config and updated-grub is called.
        """
        is_container.return_value = False
        config.return_value = {
            "reservation": "isolcpus",
            "cpu-range": "0-10",
            "hugepages": "400",
            "hugepagesz": "1G",
            "default-hugepagesz": "1G",
            "raid-autodetection": "noautodetect",
            "enable-pti": "",
            "enable-iommu": True,
            "enable-tsx": True,
            "grub-config-flags": 'TEST_KEY="TEST VALUE, WITH COMMA", GRUB_TIMEOUT=0',
            "kernel-version": "4.15.0-38-generic",
            "update-grub": True,
            "isolcpus": "",
        }

        expected = {
            "isolcpus": "0-10",
            "hugepages": "400",
            "hugepagesz": "1G",
            "default_hugepagesz": "1G",
            "raid": "noautodetect",
            "iommu": True,
            "tsx": True,
            "grub_config_flags": {
                "GRUB_TIMEOUT": "0",
                "TEST_KEY": '"TEST VALUE, WITH COMMA"',
            },
            "grub_default": "Advanced options for Ubuntu>Ubuntu, "
            "with Linux 4.15.0-38-generic",
        }

        sysh = lib_sysconfig.SysConfigHelper()
        sysh.update_grub_file()
        render.assert_called_with(
            source=lib_sysconfig.GRUB_CONF_TMPL,
            target=lib_sysconfig.GRUB_CONF,
            templates_dir="templates",
            context=expected,
        )
        check_call.assert_called()

    @mock.patch("lib_sysconfig.host.is_container")
    @mock.patch("lib_sysconfig.subprocess.check_call")
    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.hookenv.log")
    @mock.patch("lib_sysconfig.render")
    def test_legacy_grub_config_flags(
        self, render, log, config, check_call, is_container
    ):
        """Update /etc/default/grub.d/90-sysconfig.cfg and update-grub true.

        Expect file is rendered with correct config and updated-grub is called.
        """
        is_container.return_value = False
        config.return_value = {
            "reservation": "off",
            "isolcpus": "",
            "hugepages": "",
            "hugepagesz": "",
            "default-hugepagesz": "",
            "raid-autodetection": "",
            "enable-pti": "",
            "enable-iommu": False,
            "enable-tsx": False,
            "config-flags": "{ 'grub': 'GRUB_TIMEOUT=0, "
            "TEST=line with space, and comma'}",
            "grub-config-flags": "",
            "kernel-version": "",
            "update-grub": True,
        }

        expected = {
            "grub_config_flags": {
                "GRUB_TIMEOUT": "0",
                "TEST": "line with space, and comma",
            }
        }

        sysh = lib_sysconfig.SysConfigHelper()
        sysh.update_grub_file()
        render.assert_called_with(
            source=lib_sysconfig.GRUB_CONF_TMPL,
            target=lib_sysconfig.GRUB_CONF,
            templates_dir="templates",
            context=expected,
        )
        check_call.assert_called()

    @mock.patch("lib_sysconfig.subprocess.check_call")
    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.hookenv.log")
    @mock.patch("lib_sysconfig.render")
    def test_update_grub_file_no_update_grub(self, render, log, config, check_call):
        """Update /etc/default/grub.d/90-sysconfig.cfg and update-grub false.

        Expect file is rendered with correct config and updated-grub is not called.
        """
        config.return_value = {
            "reservation": "off",
            "isolcpus": "0-10",
            "hugepages": "400",
            "hugepagesz": "1G",
            "default-hugepagesz": "1G",
            "raid-autodetection": "noautodetect",
            "enable-pti": "off",
            "enable-iommu": True,
            "enable-tsx": True,
            "grub-config-flags": 'GRUB_TIMEOUT=0, TEST="one,two,three, four"',
            "kernel-version": "4.15.0-38-generic",
            "update-grub": False,
        }

        expected = {
            "isolcpus": "0-10",
            "hugepages": "400",
            "hugepagesz": "1G",
            "default_hugepagesz": "1G",
            "raid": "noautodetect",
            "iommu": True,
            "tsx": True,
            "grub_config_flags": {"GRUB_TIMEOUT": "0", "TEST": '"one,two,three, four"'},
            "grub_default": "Advanced options for Ubuntu>Ubuntu, "
            "with Linux 4.15.0-38-generic",
            "enable_pti": "off",
        }

        sysh = lib_sysconfig.SysConfigHelper()
        sysh.update_grub_file()
        render.assert_called_with(
            source=lib_sysconfig.GRUB_CONF_TMPL,
            target=lib_sysconfig.GRUB_CONF,
            templates_dir="templates",
            context=expected,
        )
        check_call.assert_not_called()

    @mock.patch("lib_sysconfig.subprocess.check_call")
    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.hookenv.log")
    @mock.patch("lib_sysconfig.render")
    def test_update_grub_file_no_update_grub_deprecate(
        self, render, log, config, check_call
    ):
        """Update /etc/default/grub.d/90-sysconfig.cfg and update-grub false.

        Expect file is rendered with correct config and updated-grub is not called.
        """
        config.return_value = {
            "reservation": "isolcpus",
            "cpu-range": "0-5",
            "isolcpus": "0-10",
            "hugepages": "400",
            "hugepagesz": "1G",
            "default-hugepagesz": "1G",
            "raid-autodetection": "noautodetect",
            "enable-pti": "off",
            "enable-iommu": True,
            "enable-tsx": True,
            "grub-config-flags": 'GRUB_TIMEOUT=0, TEST="one,two,three, four"',
            "kernel-version": "4.15.0-38-generic",
            "update-grub": False,
        }

        expected = {
            "isolcpus": "0-10",
            "hugepages": "400",
            "hugepagesz": "1G",
            "default_hugepagesz": "1G",
            "raid": "noautodetect",
            "iommu": True,
            "tsx": True,
            "grub_config_flags": {"GRUB_TIMEOUT": "0", "TEST": '"one,two,three, four"'},
            "grub_default": "Advanced options for Ubuntu>Ubuntu, "
            "with Linux 4.15.0-38-generic",
            "enable_pti": "off",
        }

        sysh = lib_sysconfig.SysConfigHelper()
        sysh.update_grub_file()
        render.assert_called_with(
            source=lib_sysconfig.GRUB_CONF_TMPL,
            target=lib_sysconfig.GRUB_CONF,
            templates_dir="templates",
            context=expected,
        )

    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.hookenv.log")
    @mock.patch("lib_sysconfig.render")
    def test_update_systemd_system_file(self, render, log, config):
        """Update config and see whether /etc/systemd/system.conf is rendered.

        Expect file is rendered with correct config and updated-grub is not called.
        """
        config.return_value = {
            "reservation": "off",
            "cpu-affinity-range": "0-10",
            "systemd-config-flags": "DefaultLimitRTTIME=1,DefaultTasksMax=10",
        }

        expected = {
            "cpu_affinity_range": "0-10",
            "systemd_config_flags": {
                "DefaultLimitRTTIME": "1",
                "DefaultTasksMax": "10",
            },
        }

        sysh = lib_sysconfig.SysConfigHelper()
        update_available = Mock()
        update_available.return_value = True
        sysh._systemd_update_available = update_available

        sysh.update_systemd_system_file()
        render.assert_called_with(
            source=lib_sysconfig.SYSTEMD_SYSTEM_TMPL,
            target=lib_sysconfig.SYSTEMD_SYSTEM,
            templates_dir="templates",
            context=expected,
        )
        log.assert_called_with("systemd configuration updated")

    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.hookenv.log")
    @mock.patch("lib_sysconfig.render")
    def test_update_systemd_system_file_no_change(self, render, log, config):
        """Test whether /etc/systemd/system.conf is rendered if there are no changes."""
        config.return_value = {
            "cpu-affinity-range": "",
            "reservation": "off",
            "systemd-config-flags": "",
        }

        sysh = lib_sysconfig.SysConfigHelper()
        update_available = Mock()
        update_available.return_value = False
        sysh._systemd_update_available = update_available

        sysh.update_systemd_system_file()
        render.assert_not_called()
        log.assert_called_with("no systemd configuration changes, not rendering file")

    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.hookenv.log")
    @mock.patch("lib_sysconfig.render")
    def test_update_systemd_system_file_deprecate(self, render, log, config):
        """Update /etc/default/grub.d/90-sysconfig.cfg and update-grub false.

        Expect file is rendered with correct config and updated-grub is not called.
        """
        config.return_value = {
            "reservation": "affinity",
            "cpu-range": "0-5",
            "cpu-affinity-range": "0-10",
            "systemd-config-flags": "DefaultLimitRTTIME=1,DefaultTasksMax=10",
        }

        expected = {
            "cpu_affinity_range": "0-10",
            "systemd_config_flags": {
                "DefaultLimitRTTIME": "1",
                "DefaultTasksMax": "10",
            },
        }

        sysh = lib_sysconfig.SysConfigHelper()
        update_available = Mock()
        update_available.return_value = True
        sysh._systemd_update_available = update_available

        sysh.update_systemd_system_file()
        render.assert_called_with(
            source=lib_sysconfig.SYSTEMD_SYSTEM_TMPL,
            target=lib_sysconfig.SYSTEMD_SYSTEM,
            templates_dir="templates",
            context=expected,
        )

    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.hookenv.log")
    @mock.patch("lib_sysconfig.render")
    def test_update_systemd_system_legacy_reservation(self, render, log, config):
        """Update /etc/default/grub.d/90-sysconfig.cfg and update-grub false.

        Expect file is rendered with correct config and updated-grub is not called.
        """
        config.return_value = {
            "reservation": "affinity",
            "cpu-range": "0-10",
            "systemd-config-flags": "DefaultLimitRTTIME=1,DefaultTasksMax=10",
            "cpu-affinity-range": "",
        }

        expected = {
            "cpu_affinity_range": "0-10",
            "systemd_config_flags": {
                "DefaultLimitRTTIME": "1",
                "DefaultTasksMax": "10",
            },
        }

        sysh = lib_sysconfig.SysConfigHelper()
        update_available = Mock()
        update_available.return_value = True
        sysh._systemd_update_available = update_available

        sysh.update_systemd_system_file()
        render.assert_called_with(
            source=lib_sysconfig.SYSTEMD_SYSTEM_TMPL,
            target=lib_sysconfig.SYSTEMD_SYSTEM,
            templates_dir="templates",
            context=expected,
        )

    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.hookenv.log")
    @mock.patch("lib_sysconfig.render")
    def test_legacy_systemd_config_flags(self, render, log, config):
        """Update /etc/default/grub.d/90-sysconfig.cfg and update-grub false.

        Expect file is rendered with correct config and updated-grub is not called.
        """
        config.return_value = {
            "reservation": "off",
            "cpu-affinity-range": "0-10",
            "config-flags": "{'systemd': 'DefaultLimitRTTIME=1, DefaultTasksMax=10'}",
            "systemd-config-flags": "",
        }

        expected = {
            "cpu_affinity_range": "0-10",
            "systemd_config_flags": {
                "DefaultLimitRTTIME": "1",
                "DefaultTasksMax": "10",
            },
        }

        sysh = lib_sysconfig.SysConfigHelper()
        update_available = Mock()
        update_available.return_value = True
        sysh._systemd_update_available = update_available

        sysh.update_systemd_system_file()
        render.assert_called_with(
            source=lib_sysconfig.SYSTEMD_SYSTEM_TMPL,
            target=lib_sysconfig.SYSTEMD_SYSTEM,
            templates_dir="templates",
            context=expected,
        )

    @mock.patch("lib_sysconfig.apt_install")
    @mock.patch("lib_sysconfig.apt_update")
    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.running_kernel")
    @mock.patch("lib_sysconfig.hookenv.log")
    def test_install_configured_kernel_true(
        self, log, running_kernel, config, apt_update, apt_install
    ):
        """Set config kernel=4.15.0-38-generic and running kernel is different.

        Expect apt install is called twice.
        """
        config.return_value = {"kernel-version": "4.15.0-38-generic"}

        running_kernel.return_value = "4.4.0-38-generic"
        sysh = lib_sysconfig.SysConfigHelper()
        sysh.install_configured_kernel()

        apt_install.assert_any_call(
            "linux-modules-extra-{}".format("4.15.0-38-generic")
        )
        apt_install.assert_any_call("linux-image-{}".format("4.15.0-38-generic"))

    @mock.patch("lib_sysconfig.apt_install")
    @mock.patch("lib_sysconfig.apt_update")
    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.running_kernel")
    @mock.patch("lib_sysconfig.hookenv.log")
    def test_install_configured_kernel_false(
        self, log, running_kernel, config, apt_update, apt_install
    ):
        """Set config kernel=4.15.0-38-generic and running kernel is the same.

        Expect apt install is called once for linux-modules-extra.
        """
        kernel_version = "4.15.0-38-generic"
        config.return_value = {"kernel-version": kernel_version}

        running_kernel.return_value = "4.15.0-38-generic"
        sysh = lib_sysconfig.SysConfigHelper()
        sysh.install_configured_kernel()

        apt_install.assert_called_with(
            "linux-modules-extra-{}".format("4.15.0-38-generic")
        )

    @mock.patch("lib_sysconfig.apt_install")
    @mock.patch("lib_sysconfig.apt_update")
    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.running_kernel")
    @mock.patch("lib_sysconfig.hookenv.log")
    def test_install_configured_kernel_no_specified(
        self, log, running_kernel, config, apt_update, apt_install
    ):
        """Set config kernel=''.

        Expect apt install is not called.
        """
        config.return_value = {"kernel-version": ""}

        running_kernel.return_value = "4.15.0-38-generic"
        sysh = lib_sysconfig.SysConfigHelper()
        sysh.install_configured_kernel()

        apt_install.assert_not_called()

    @mock.patch("lib_sysconfig.host.service_restart")
    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.hookenv.log")
    @mock.patch("lib_sysconfig.render")
    def test_update_irqbalance_file(self, render, log, config, restart):
        """Update /etc/default/irqbalance.

        Expect file is rendered with correct config.
        """
        config.return_value = {
            "irqbalance-banned-cpus": "3000030000300003",
        }

        expected = {
            "irqbalance_banned_cpus": "3000030000300003",
        }

        sysh = lib_sysconfig.SysConfigHelper()
        sysh.update_irqbalance()
        render.assert_called_with(
            source=lib_sysconfig.IRQBALANCE_CONF_TMPL,
            target=lib_sysconfig.IRQBALANCE_CONF,
            templates_dir="templates",
            context=expected,
        )

        restart.assert_called()

    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.os.remove")
    @mock.patch("lib_sysconfig.hookenv.log")
    @mock.patch("lib_sysconfig.os.path.exists")
    def test_remove_grub_configuration_true(self, exists, log, os_remove, config):
        """Test remove grub configuration assuming file exists.

        Expect os.remove is called
        """
        config.return_value = {"update-grub": False}
        exists.return_value = True

        with NamedTemporaryFile() as ftmp:
            lib_sysconfig.GRUB_CONF = ftmp.name
            sysh = lib_sysconfig.SysConfigHelper()
            sysh.remove_grub_configuration()
            os_remove.assert_called_with(lib_sysconfig.GRUB_CONF)

    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.os.remove")
    @mock.patch("lib_sysconfig.hookenv.log")
    @mock.patch("lib_sysconfig.os.path.exists")
    def test_remove_grub_configuration_false(self, exists, log, os_remove, config):
        """Test remove grub configuration assuming file not exists.

        Expect os.remove is not called
        """
        config.return_value = {"update-grub": False}
        exists.return_value = False

        sysh = lib_sysconfig.SysConfigHelper()
        sysh.remove_grub_configuration()

        os_remove.assert_not_called()

    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.hookenv.log")
    @mock.patch("lib_sysconfig.render")
    def test_remove_systemd_configuration(self, render, log, config):
        """Test remove systemd configuration.

        Expect file is rendered with empty context.
        """
        sysh = lib_sysconfig.SysConfigHelper()
        sysh.remove_systemd_configuration()

        render.assert_called_with(
            source=lib_sysconfig.SYSTEMD_SYSTEM_TMPL,
            target=lib_sysconfig.SYSTEMD_SYSTEM,
            templates_dir="templates",
            context={},
        )

    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.render")
    @mock.patch("lib_sysconfig.host.service_restart")
    @mock.patch("lib_sysconfig.subprocess.call")
    @mock.patch("lib_sysconfig.hookenv.log")
    def test_remove_cpufreq_configuration_xenial(
        self, log, check_call, restart, render, config
    ):
        """Test remove cpufrequtlis configuration.

        Expect config is rendered with empty context.
        """
        sysh = lib_sysconfig.SysConfigHelper()
        sysh.remove_cpufreq_configuration()

        check_call.assert_called_with(
            ["/bin/systemctl", "unmask", "ondemand"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        render.assert_called_with(
            source=lib_sysconfig.CPUFREQUTILS_TMPL,
            target=lib_sysconfig.CPUFREQUTILS,
            templates_dir="templates",
            context={},
        )
        restart.assert_called()

    @pytest.mark.parametrize(
        "invalid_config_key",
        ["reservation", "raid-autodetection", "governor", "resolved-cache-mode"],
    )
    @mock.patch("lib_sysconfig.hookenv.config")
    def test_wrong_config(self, config, invalid_config_key):
        """Test wrong configuration value.

        Expect that is_config_valid() return false
        """
        return_value = {
            "reservation": "off",
            "raid-autodetection": "",
            "governor": "",
            "resolved-cache-mode": "",
            invalid_config_key: "wrong",  # Will override key with an invalid value
        }
        config.return_value = return_value
        sysh = lib_sysconfig.SysConfigHelper()
        assert not sysh.is_config_valid()

    @mock.patch("lib_sysconfig.hookenv.config")
    def test_enable_container(self, config):
        """Test enable container."""
        config.return_value = {"enable-container": True}
        sysh = lib_sysconfig.SysConfigHelper()

        assert sysh.enable_container

    @mock.patch("lib_sysconfig.any_file_changed")
    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.host.service_restart")
    @mock.patch("lib_sysconfig.render")
    def test_update_resolved_file_unchanged(
        self, render, restart, config, file_changed
    ):
        """systemd-resolved is not restarted when the config file is unchanged."""
        file_changed.return_value = False
        self._test_update_resolved_common(render, config)
        restart.assert_not_called()

    @mock.patch("lib_sysconfig.any_file_changed")
    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.host.service_restart")
    @mock.patch("lib_sysconfig.render")
    def test_update_resolved_file_changed(self, render, restart, config, file_changed):
        """systemd-resolved is restarted when the config file changes."""
        file_changed.return_value = True
        self._test_update_resolved_common(render, config)
        restart.assert_called()

    def _test_update_resolved_common(self, render, config):
        """Call the render function with specific parameters."""
        config.return_value = {"resolved-cache-mode": "no-negative"}
        sysh = lib_sysconfig.SysConfigHelper()
        sysh.update_systemd_resolved()
        render.assert_called_with(
            source=lib_sysconfig.SYSTEMD_RESOLVED_TMPL,
            target=lib_sysconfig.SYSTEMD_RESOLVED,
            templates_dir="templates",
            context={"cache": "no-negative"},
        )

    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("charmhelpers.core.sysctl.check_call")
    def test_update_sysctl(self, check_call, config):
        """Test updating sysctl config."""
        config.return_value = {
            "sysctl": """
            net.ipv4.ip_forward: 1
            vm.swappiness: 60"""
        }
        sysh = lib_sysconfig.SysConfigHelper()
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            sysh.update_sysctl()

        mock_file.assert_called_with(lib_sysconfig.SYSCTL_CONF, "w")
        handle = mock_file()
        handle.write.assert_has_calls(
            [mock.call("net.ipv4.ip_forward=1\n"), mock.call("vm.swappiness=60\n")]
        )
        check_call.assert_called_with(["sysctl", "-p", lib_sysconfig.SYSCTL_CONF])

    @mock.patch("lib_sysconfig.hookenv")
    def test_update_sysctl_invalid_yaml(self, hookenv):
        """Test updating sysctl config with invalid yaml."""
        hookenv.config.return_value = {"sysctl": "{invalid"}
        sysh = lib_sysconfig.SysConfigHelper()
        with pytest.raises(Exception):
            sysh.update_sysctl()
        hookenv.log.assert_called_once_with(
            "Error parsing sysctl YAML: {invalid", level=hookenv.ERROR
        )
        hookenv.status_set.assert_called_once_with(
            "blocked", "Error parsing sysctl YAML"
        )

    @mock.patch("lib_sysconfig.host.service_restart")
    @mock.patch("lib_sysconfig.hookenv.config")
    @mock.patch("lib_sysconfig.hookenv.log")
    @mock.patch("lib_sysconfig.render")
    def test_remove_irqbalance_configuration(self, render, log, config, restart):
        """Test remove irqbalance configuration.

        Expect file is rendered with empty context.
        """
        sysh = lib_sysconfig.SysConfigHelper()
        sysh.remove_irqbalance_configuration()

        render.assert_called_with(
            source=lib_sysconfig.IRQBALANCE_CONF_TMPL,
            target=lib_sysconfig.IRQBALANCE_CONF,
            templates_dir="templates",
            context={},
        )

        restart.assert_called()
