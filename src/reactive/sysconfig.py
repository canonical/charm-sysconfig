# Copyright 2019 Canonical Ltd.
#
# This file is part of the CPUConfig Charm for Juju.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3, as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Reactive hooks for sysconfig charm."""

from charmhelpers.core import hookenv, host
from charms.reactive import (
    clear_flag,
    helpers,
    hook,
    is_flag_set,
    set_flag,
    when,
    when_none,
    when_not,
)
from lib_sysconfig import (
    CPUFREQUTILS,
    GRUB_CONF,
    IRQBALANCE_CONF,
    KERNEL,
    SYSTEMD_RESOLVED,
    SYSTEMD_SYSTEM,
    SysConfigHelper,
)


@when_none("sysconfig.installed", "sysconfig.unsupported")
@when("juju-info.connected")
def install_sysconfig():
    """Install the charm if it is not running on a container.

    Deploy can be forced using enable-container option only for testing.
    (Default: false).
    """
    syshelper = SysConfigHelper()

    # container not supported unless enable-container=true for testing purpose
    if host.is_container() and not syshelper.enable_container:
        hookenv.status_set("blocked", "containers are not supported")
        set_flag("sysconfig.unsupported")
        return

    if not syshelper.is_config_valid():
        hookenv.status_set("blocked", "configuration parameters not valid.")
        return

    if syshelper.install_cpufrequtils():
        set_flag("sysconfig.cpufrequtils-installed")

    syshelper.install_configured_kernel()

    if is_flag_set("sysconfig.cpufrequtils-installed"):
        syshelper.update_cpufreq()

    syshelper.update_grub_file()
    syshelper.update_systemd_system_file()
    syshelper.update_systemd_resolved()
    syshelper.update_irqbalance()
    syshelper.update_sysctl()
    set_flag("sysconfig.installed")
    update_status()


@when("sysconfig.installed")
@when_not("sysconfig.unsupported")
@when("config.changed")
def config_changed():
    """Apply configuration updates if the charm is installed."""
    syshelper = SysConfigHelper()
    hookenv.status_set("maintenance", "applying changes")

    if not syshelper.is_config_valid():
        hookenv.status_set("blocked", "configuration parameters not valid.")
        return

    # Kernel
    if syshelper.charm_config.changed("kernel-version"):
        syshelper.install_configured_kernel()

    # cpufreq
    if is_flag_set("sysconfig.cpufrequtils-installed") and (
        syshelper.charm_config.changed("governor") or helpers.any_file_changed([CPUFREQUTILS])
    ):
        syshelper.update_cpufreq()

    # GRUB
    if any(
        syshelper.charm_config.changed(flag)
        for flag in (
            "reservation",
            "hugepages",
            "hugepagesz",
            "default-hugepagesz",
            "raid-autodetection",
            "enable-pti",
            "enable-iommu",
            "grub-config-flags",
            "kernel-version",
            "update-grub",
            "config-flags",
            "cpu-range",
            "isolcpus",
        )
    ) or helpers.any_file_changed(
        [GRUB_CONF]
    ):  # noqa: W503
        syshelper.update_grub_file()

    # systemd
    if any(
        syshelper.charm_config.changed(flag)
        for flag in (
            "reservation",
            "systemd-config-flags",
            "cpu-range",
            "config-flags",
            "cpu-affinity-range",
        )
    ) or helpers.any_file_changed(
        [SYSTEMD_SYSTEM]
    ):  # noqa: W503
        syshelper.update_systemd_system_file()

    # systemd resolved
    if any(
        syshelper.charm_config.changed(flag) for flag in ("resolved-cache-mode",)
    ) or helpers.any_file_changed([SYSTEMD_RESOLVED]):
        syshelper.update_systemd_resolved()

    # sysctl
    if syshelper.charm_config.changed("sysctl"):
        syshelper.update_sysctl()

    # irqbalance
    if syshelper.charm_config.changed(
        "irqbalance-banned-cpus"
    ) or helpers.any_file_changed([IRQBALANCE_CONF]):
        syshelper.update_irqbalance()

    update_status()


@hook("upgrade-charm")
def upgrade_charm():
    """Extras to run when charm is upgraded."""
    # NOTE(hopem): do this for backwards compatibility to ensure that db
    # records of resources are updated with a sha256sum prior to config-changed
    # being run where they may be overwritten with no content change - see bug
    # 1864217 for context.
    update_status()


@hook("update-status")
def update_status():
    """Update the workload message checking if reboot is needed.

    Note: After the reboot use clear-notification action to clear the
    'reboot required' message.
    """
    if is_flag_set("sysconfig.unsupported"):
        return

    resources = [KERNEL, SYSTEMD_SYSTEM]
    boot_changes = SysConfigHelper.boot_resources.resources_changed_since_boot(
        resources
    )

    # This check compares the existing grub conf file with the
    # one newly generated using grub-mkconfig in order to
    # notify for a reboot if necessary
    grub_update_available = SysConfigHelper.boot_resources.check_grub_reboot()

    if grub_update_available:
        boot_changes.append(GRUB_CONF)

    config = hookenv.config()
    if config["update-grub"]:
        # if update-grub is set to true, then no need to check for grub update
        # since it will be applied automatically.
        grub_update_available = False

    status = "active"
    message = "ready"
    if boot_changes:
        status = "blocked"
        message = "reboot required. Changes in: {}".format(", ".join(boot_changes))
        # if update-grub is set to false and there is an update to grub config,
        # then add more info to the status message. (addressing #1895189)
        if grub_update_available:
            message = "update-grub and " + message
    hookenv.status_set(status, message)


@when("config.changed.enable-container")
@when_not("sysconfig.installed")
def enable_container_changed():
    """Trigger installation if enable-container option changed."""
    clear_flag("sysconfig.unsupported")


@when("sysconfig.installed")
@when_not("juju-info.available")
def remove_configuration():
    """Remove configuration applied by the charm if the juju-info relation is departed.

    For safety, kernels installed by the charm won't be removed.
    """
    hookenv.status_set("maintenance", "removing sysconfig configurations")
    syshelper = SysConfigHelper()

    if is_flag_set("sysconfig.cpufrequtils-installed"):
        syshelper.remove_cpufreq_configuration()

    syshelper.remove_grub_configuration()
    syshelper.remove_systemd_configuration()
    syshelper.remove_resolved_configuration()
    syshelper.remove_irqbalance_configuration()
    clear_flag("sysconfig.installed")
    clear_flag("sysconfig.unsupported")
