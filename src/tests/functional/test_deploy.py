"""Functional tests for sysconfig charm."""

import asyncio
import re

import pytest
import tenacity
import websockets

# Treat all tests as coroutines
pytestmark = pytest.mark.asyncio

TIMEOUT = 600
MODEL_ACTIVE_TIMEOUT = 10
GRUB_DEFAULT = "Advanced options for Ubuntu>Ubuntu, with Linux {}"
PRINCIPAL_APP_NAME = "ubuntu-{}"
RETRY = tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, max=60),
    reraise=True,
    stop=tenacity.stop_after_attempt(4),
)


# Uncomment for re-using the current model, useful for debugging functional tests
# @pytest_asyncio.fixture(scope="module")
# async def model():
#     from juju.model import Model
#     model = Model()
#     await model.connect()
#     yield model
#     await model.disconnect()


@pytest.mark.skip(reason="false grub reboot notification. check issue #40")
async def test_app_deploy(model, app):
    """Verify if the sysconfig app has been successfully deployed."""
    try:
        await model.block_until(lambda: app.status == "active", timeout=TIMEOUT)
    except asyncio.exceptions.TimeoutError:
        assert False, "Sysconfig app should have active status."


async def test_app_with_config_deploy(model, app_with_config):
    """Check if status of sysconfig app is "blocked" if deployed along with config."""
    try:
        await model.block_until(
            lambda: app_with_config.status == "blocked", timeout=TIMEOUT
        )
    except asyncio.exceptions.TimeoutError:
        assert False, "Sysconfig app with config should have blocked status."


async def test_cpufrequtils_intalled(app, jujutools):
    """Verify cpufrequtils pkg is installed."""
    unit = app.units[0]
    cmd = "dpkg -l | grep cpufrequtils"
    results = await jujutools.run_command(cmd, unit)
    assert results["return-code"] == 0


async def test_default_config(app, jujutools):
    """Test default configuration for grub, systemd and cpufrequtils."""
    unit = app.units[0]
    not_expected_contents_grub = [
        "isolcpus",
        "hugepages",
        "hugepagesz",
        "raid",
        "pti=off",
        "intel_iommu",
        "tsx=on",
        "GRUB_DEFAULT",
        "default_hugepagesz",
    ]
    grub_path = "/etc/default/grub.d/90-sysconfig.cfg"
    RETRY(
        await jujutools.check_file_contents(
            grub_path, unit, not_expected_contents_grub, assert_in=False
        )
    )

    sysctl_path = "/etc/sysctl.d/90-charm-sysconfig.conf"
    sysctl_exists = await jujutools.file_exists(sysctl_path, unit)
    assert sysctl_exists

    systemd_path = "/etc/systemd/system.conf"
    systemd_content = await jujutools.file_contents(systemd_path, unit)
    systemd_valid = True
    for line in systemd_content:
        if line.startswith("CPUAffinity="):
            systemd_valid = False
    assert systemd_valid

    cpufreq_path = "/etc/default/cpufrequtils"
    cpufreq_content = await jujutools.file_contents(cpufreq_path, unit)
    assert "GOVERNOR" not in cpufreq_content

    irqbalance_path = "/etc/default/irqbalance"
    irqbalance_content = await jujutools.file_contents(irqbalance_path, unit)
    irqbalance_valid = True
    for line in irqbalance_content:
        if line.startswith("IRQBALANCE_BANNED_CPUS"):
            irqbalance_valid = False
    assert irqbalance_valid


async def test_config_changed(app, model, jujutools):
    """Test configuration changed for grub, systemd, cpufrqutils and kernel."""
    kernel_version = "4.15.0-38-generic"
    if "focal" in app.entity_id:
        # override the kernel_version for focal, we specify the oldest one ever
        # released, as normal installations
        # will updated to newest available
        kernel_version = "5.4.0-29-generic"
    elif "jammy" in app.entity_id:
        # similarly override kernel_version for jammy
        kernel_version = "5.15.0-25-generic"
    linux_pkg = "linux-image-{}".format(kernel_version)
    linux_modules_extra_pkg = "linux-modules-extra-{}".format(kernel_version)

    unit = app.units[0]

    # test if required kernel version is absent prior to setting the config
    for pkg in (linux_pkg, linux_modules_extra_pkg):
        cmd = "dpkg -l | grep {}".format(pkg)
        results = await jujutools.run_command(cmd, unit)
        assert results["return-code"] == 1

    await app.set_config(
        {
            "isolcpus": "1,2,3,4",
            "hugepages": "100",
            "hugepagesz": "1G",
            "default-hugepagesz": "1G",
            "raid-autodetection": "noautodetect",
            "enable-pti": "on",
            "enable-iommu": "false",
            "enable-tsx": "true",
            "kernel-version": kernel_version,
            "grub-config-flags": "GRUB_TIMEOUT=10",
            # config-flags are ignored when grub-config-flags are used
            "config-flags": '{"grub": "TEST=test"}',
            "systemd-config-flags": "LogLevel=warning,DumpCore=no",
            "governor": "powersave",
        }
    )
    await model.block_until(lambda: app.status == "blocked", timeout=TIMEOUT)
    assert app.status == "blocked"

    grub_path = "/etc/default/grub.d/90-sysconfig.cfg"
    expected_contents_grub = [
        "isolcpus=1,2,3,4",
        "hugepages=100",
        "hugepagesz=1G",
        "default_hugepagesz=1G",
        "raid=noautodetect",
        "pti=on",
        "tsx=on tsx_async_abort=off",
        'GRUB_DEFAULT="{}"'.format(GRUB_DEFAULT.format(kernel_version)),
        "GRUB_TIMEOUT=10",
    ]
    not_expected_contents_grub = [
        "intel_iommu=on iommu=pt",
        "TEST=test",
    ]
    RETRY(await jujutools.check_file_contents(grub_path, unit, expected_contents_grub))
    RETRY(
        await jujutools.check_file_contents(
            grub_path, unit, not_expected_contents_grub, assert_in=False
        )
    )

    # Reconfiguring reservation from isolcpus to affinity
    # isolcpus will be removed from grub and affinity added to systemd

    await app.set_config({"isolcpus": "", "cpu-affinity-range": "1,2,3,4"})

    await model.block_until(lambda: app.status == "blocked", timeout=TIMEOUT)
    assert app.status == "blocked"

    expected_contents_systemd = [
        "CPUAffinity=1,2,3,4",
        "LogLevel=warning",
        "DumpCore=no",
    ]

    not_expected_contents_grub = [
        "isolcpus",
    ]

    systemd_path = "/etc/systemd/system.conf"
    RETRY(
        await jujutools.check_file_contents(
            systemd_path, unit, expected_contents_systemd
        )
    )

    RETRY(
        await jujutools.check_file_contents(
            grub_path, unit, not_expected_contents_grub, assert_in=False
        )
    )

    cpufreq_path = "/etc/default/cpufrequtils"
    expected_cpufreq_content = ["GOVERNOR=powersave"]
    RETRY(
        await jujutools.check_file_contents(
            cpufreq_path, unit, expected_cpufreq_content
        )
    )

    # test new kernel installed
    for pkg in (linux_pkg, linux_modules_extra_pkg):
        cmd = "dpkg -l | grep {}".format(pkg)
        results = await jujutools.run_command(cmd, unit)
        assert results["return-code"] == 0

    # test irqbalance_banned_cpus
    await app.set_config({"irqbalance-banned-cpus": "3000030000300003"})
    await model.block_until(lambda: app.status == "blocked", timeout=TIMEOUT)
    assert app.status == "blocked"

    expected_irqbalance_content = ["IRQBALANCE_BANNED_CPUS=3000030000300003"]
    irqbalance_path = "/etc/default/irqbalance"
    RETRY(
        await jujutools.check_file_contents(
            irqbalance_path, unit, expected_irqbalance_content
        )
    )

    # test update-status show that update-grub and reboot is required, since
    # "grub-config-flags" is changed and "update-grub" is set to false by
    # default.
    assert "update-grub and reboot required." in unit.workload_status_message


async def test_check_update_grub(app):
    """Tests that check-update-grub action complete."""
    unit = app.units[0]
    action = await unit.run_action("check-update-grub")
    action = await action.wait()
    assert action.status == "completed"


async def test_clear_notification(app):
    """Tests that clear-notification action complete."""
    unit = app.units[0]
    action = await unit.run_action("clear-notification")
    action = await action.wait()
    assert action.status == "completed"


async def test_clear_notification_persist_after_update_status(app, model):
    """Tests that clear-notification action complete."""
    unit = app.units[0]
    action = await unit.run_action("clear-notification")
    action = await action.wait()
    action = await unit.run("JUJU_HOOK_NAME=update-status ./hooks/update-status")
    await model.block_until(lambda: app.status == "active", timeout=TIMEOUT)


# This may need to be removed at some point once the reservation
# variable gets removed
async def test_wrong_reservation(app, model):
    """Tests wrong reservation value is used.

    Expect application is blocked until correct value is set.
    """
    await app.set_config({"reservation": "changeme"})
    await model.block_until(lambda: app.status == "blocked", timeout=TIMEOUT)
    assert app.status == "blocked"

    await app.set_config({"reservation": "off"})
    await model.block_until(lambda: app.status == "blocked", timeout=TIMEOUT)


@pytest.mark.parametrize(
    "key,bad_value,good_value",
    [
        ("raid-autodetection", "changeme", ""),
        ("governor", "changeme", ""),
        ("resolved-cache-mode", "changeme", ""),
    ],
)
async def test_invalid_configuration_parameters(app, model, key, bad_value, good_value):
    """Tests wrong config value is used.

    Expect application is blocked until correct value is set.
    """
    await app.set_config({key: bad_value})
    await model.block_until(lambda: app.status == "blocked", timeout=TIMEOUT)
    assert app.status == "blocked"

    await app.set_config({key: good_value})
    await model.block_until(lambda: app.status == "blocked", timeout=TIMEOUT)


@pytest.mark.parametrize("cache_setting", ["yes", "no", "no-negative"])
async def test_set_resolved_cache(app, model, jujutools, cache_setting):
    """Tests resolved cache settings."""

    def is_model_settled():
        return (
            app.units[0].workload_status == "blocked"
            and app.units[0].agent_status == "idle"  # noqa: W503
        )

    await model.block_until(is_model_settled, timeout=TIMEOUT)

    await app.set_config({"resolved-cache-mode": cache_setting})
    # NOTE: app.set_config() doesn't seem to wait for the model to go to a
    # non-active/idle state.
    try:
        await model.block_until(
            lambda: not is_model_settled(), timeout=MODEL_ACTIVE_TIMEOUT
        )
    except websockets.ConnectionClosed:
        # It's possible (although unlikely) that we missed the charm transitioning from
        # idle to active and back.
        pass

    await model.block_until(is_model_settled, timeout=TIMEOUT)

    RETRY(
        await jujutools.check_file_contents_re(
            "/etc/systemd/resolved.conf",
            app.units[0],
            "^Cache={}$".format(cache_setting),
        )
    )


@pytest.mark.parametrize("sysctl", ["1", "0"])
async def test_set_sysctl(app, model, jujutools, sysctl):
    """Tests sysctl settings."""

    def is_model_settled():
        return (
            app.units[0].workload_status == "blocked"
            and app.units[0].agent_status == "idle"  # noqa: W503
        )

    await model.block_until(is_model_settled, timeout=TIMEOUT)

    await app.set_config({"sysctl": "net.ipv4.ip_forward: %s" % sysctl})
    # NOTE: app.set_config() doesn't seem to wait for the model to go to a
    # non-active/idle state.
    try:
        await model.block_until(
            lambda: not is_model_settled(), timeout=MODEL_ACTIVE_TIMEOUT
        )
    except websockets.ConnectionClosed:
        # It's possible (although unlikely) that we missed the charm transitioning from
        # idle to active and back.
        pass

    await model.block_until(is_model_settled, timeout=TIMEOUT)
    result = await jujutools.run_command("sysctl -a", app.units[0])
    content = result["stdout"]
    assert re.search("^net.ipv4.ip_forward = {}$".format(sysctl), content, re.MULTILINE)


async def test_uninstall(app, model, jujutools, series):
    """Test uninstall of the unit  by removing the subordinate relation."""
    # Apply systemd and cpufrequtils configuration to test that is deleted
    # after removing the relation with ubuntu
    await app.set_config(
        {
            "reservation": "affinity",
            "cpu-range": "1,2,3,4",
            "governor": "performance",
            "raid-autodetection": "",
        }
    )

    await model.block_until(lambda: app.status == "blocked", timeout=TIMEOUT)

    principal_app_name = PRINCIPAL_APP_NAME.format(series)
    principal_app = model.applications[principal_app_name]

    await app.destroy_relation("juju-info", "{}:juju-info".format(principal_app_name))

    await model.block_until(lambda: len(app.units) == 0, timeout=TIMEOUT)

    unit = principal_app.units[0]
    grub_path = "/etc/default/grub.d/90-sysconfig.cfg"
    cmd = "cat {}".format(grub_path)
    results = await jujutools.run_command(cmd, unit)
    assert results["return-code"] != 0

    systemd_path = "/etc/systemd/system.conf"
    systemd_content = await jujutools.file_contents(systemd_path, unit)
    assert "CPUAffinity=1,2,3,4" not in systemd_content

    resolved_path = "/etc/systemd/resolved.conf"
    resolved_content = await jujutools.file_contents(resolved_path, unit)
    assert not re.search("^Cache=", resolved_content, re.MULTILINE)

    cpufreq_path = "/etc/default/cpufrequtils"
    cpufreq_content = await jujutools.file_contents(cpufreq_path, unit)
    assert "GOVERNOR" not in cpufreq_content

    irqbalance_path = "/etc/default/irqbalance"
    irqbalance_content = await jujutools.file_contents(irqbalance_path, unit)
    assert "IRQBALANCE_BANNED_CPUS=3000030000300003" not in irqbalance_content
