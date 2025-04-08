#!/usr/bin/python3
import sys
from os.path import abspath, dirname, join
from unittest import mock

import pytest

TEST_DIR = dirname(abspath(__file__))
PROJECT_ROOT_DIR = dirname(dirname(TEST_DIR))
CHARM_DIR = join(PROJECT_ROOT_DIR, "src")
LIB_DIR = join(CHARM_DIR, "lib")
sys.path.append(LIB_DIR)


# If layer options are used, add this to sysconfig
# and import layer in lib_sysconfig
@pytest.fixture
def mock_layers(monkeypatch):
    import sys

    sys.modules["charms.layer"] = mock.Mock()
    sys.modules["reactive"] = mock.Mock()
    # Mock any functions in layers that need to be mocked here

    def options(layer):
        # mock options for layers here
        if layer == "example-layer":
            options = {"port": 9999}
            return options
        else:
            return None

    monkeypatch.setattr("lib_sysconfig.layer.options", options)


@pytest.fixture
def mock_hookenv_config(monkeypatch):
    import yaml

    def mock_config():
        cfg = {}
        yml = yaml.safe_load(open(join(CHARM_DIR, "./config.yaml")))

        # Load all defaults
        for key, value in yml["options"].items():
            cfg[key] = value["default"]

        # Manually add cfg from other layers
        # cfg['my-other-layer'] = 'mock'
        return cfg

    monkeypatch.setattr("lib_sysconfig.hookenv.config", mock_config)


@pytest.fixture
def mock_remote_unit(monkeypatch):
    monkeypatch.setattr("lib_sysconfig.hookenv.remote_unit", lambda: "unit-mock/0")


@pytest.fixture
def mock_charm_dir(monkeypatch):
    monkeypatch.setattr("lib_sysconfig.hookenv.charm_dir", lambda: "/mock/charm/dir")


@pytest.fixture
def sysconfig(tmpdir, mock_hookenv_config, mock_charm_dir, monkeypatch):
    from lib_sysconfig import SysConfigHelper

    helper = SysConfigHelper()

    # Any other functions that load helper will get this version
    monkeypatch.setattr("lib_sysconfig.SysConfigHelper", lambda: helper)

    return helper
