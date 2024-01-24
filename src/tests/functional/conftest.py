#!/usr/bin/python3
"""Reusable pytest fixtures for functional testing.

Environment variables
---------------------

test_preserve_model:
if set, the testing model won't be torn down at the end of the testing session
"""

import asyncio
import os
import subprocess
import uuid

import pytest_asyncio
from juju.controller import Controller
from juju_tools import JujuTools

charm_location = os.getenv("CHARM_LOCATION", "..").rstrip("/")
charm_name = os.getenv("CHARM_NAME", "sysconfig")
series = ["jammy", "focal"]
sources = [("local", "{}/{}.charm".format(charm_location, charm_name))]

PRINCIPAL_APP_NAME = "ubuntu-{}"


@pytest_asyncio.fixture(scope="module")
def event_loop():
    """Override the default pytest event loop.

    Allow for fixtures using a broader scope.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_debug(True)
    yield loop
    loop.close()
    asyncio.set_event_loop(None)


@pytest_asyncio.fixture(scope="module")
async def controller():
    """Connect to the current controller."""
    _controller = Controller()
    await _controller.connect_current()
    yield _controller
    await _controller.disconnect()


@pytest_asyncio.fixture(scope="module")
async def model(controller):
    """Destroy the model at the end of the test."""
    model_name = "functest-{}".format(str(uuid.uuid4())[-12:])
    _model = await controller.add_model(
        model_name,
        cloud_name=os.getenv("PYTEST_CLOUD_NAME"),
        region=os.getenv("PYTEST_CLOUD_REGION"),
        credential_name=os.getenv("PYTEST_CLOUD_CREDENTIAL"),
    )
    # https://github.com/juju/python-libjuju/issues/267
    subprocess.check_call(["juju", "models"])
    while model_name not in await controller.list_models():
        await asyncio.sleep(1)
    yield _model
    await _model.disconnect()
    if not os.getenv("PYTEST_KEEP_MODEL"):
        await controller.destroy_model(model_name)
        while model_name in await controller.list_models():
            await asyncio.sleep(1)


@pytest_asyncio.fixture(scope="module", params=series)
def series(request):
    """Return ubuntu version (i.e. xenial) in use in the test."""
    return request.param


@pytest_asyncio.fixture(scope="module", params=sources, ids=[s[0] for s in sources])
def source(request):
    """Return source of the charm under test (i.e. local, cs)."""
    return request.param


@pytest_asyncio.fixture(scope="module", autouse=True)
async def app(model, series, source, request):
    """Deploy sysconfig app along with a principal ubuntu unit."""
    channel = "stable"
    sysconfig_app_name = "sysconfig-{}-{}".format(series, source[0])
    principal_app_name = PRINCIPAL_APP_NAME.format(series)

    # uncomment if app is already deployed while re-testing on same model
    # sysconfig_app = model.applications.get(sysconfig_app_name)
    # if sysconfig_app:
    #     return sysconfig_app

    await model.deploy(
        "ubuntu", application_name=principal_app_name, series=series, channel=channel
    )

    # If series is 'xfail' force install to allow testing against versions not in
    # metadata.yaml
    force = True if request.node.get_closest_marker("xfail") else False

    sysconfig_app = await model.deploy(
        source[1],
        application_name=sysconfig_app_name,
        series=series,
        force=force,
        num_units=0,
    )
    await asyncio.gather(
        sysconfig_app.add_relation(
            "juju-info", "{}:juju-info".format(principal_app_name)
        ),
        sysconfig_app.set_config({"enable-container": "true"}),
    )

    return sysconfig_app


@pytest_asyncio.fixture(scope="module", autouse=True)
async def app_with_config(model, series, source):
    """Deploy sysconfig app + config along with a principal ubuntu unit."""
    channel = "stable"
    sysconfig_app_with_config_name = "sysconfig-{}-{}-with-config".format(
        series, source[0]
    )
    principal_app_name = PRINCIPAL_APP_NAME.format(series)
    principal_app_with_config_name = principal_app_name + "-with-config"

    # uncomment if app is already deployed while re-testing on same model
    # sysconfig_app_with_config = model.applications.get(sysconfig_app_with_config_name)
    # if sysconfig_app_with_config:
    #     return sysconfig_app_with_config

    await model.deploy(
        "ubuntu",
        application_name=principal_app_with_config_name,
        series=series,
        channel=channel,
    )

    config = {
        "isolcpus": "1,2,3,4",
        "enable-pti": "on",
        "systemd-config-flags": "LogLevel=warning,DumpCore=no",
        "governor": "powersave",
    }
    sysconfig_app_with_config = await model.deploy(
        source[1],
        application_name=sysconfig_app_with_config_name,
        series=series,
        num_units=0,
        config=config,
    )
    await asyncio.gather(
        sysconfig_app_with_config.add_relation(
            "juju-info", "{}:juju-info".format(principal_app_with_config_name)
        ),
        sysconfig_app_with_config.set_config({"enable-container": "true"}),
    )

    return sysconfig_app_with_config


@pytest_asyncio.fixture(scope="module")
async def jujutools(controller, model):
    """Return JujuTools instance."""
    tools = JujuTools(controller, model)
    return tools
