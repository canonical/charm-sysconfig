"""Helper class to run command in a unit under test."""

import base64
import pickle
import re

import juju


class JujuTools:
    """Helper class to run command in a unit under test.

    Permit to run command in a unit under tests (generic command, os.stat and
    cat <file>).
    """

    def __init__(self, controller, model):
        """Initialize controller and model under test."""
        self.controller = controller
        self.model = model

    async def run_command(self, cmd, target):
        """Run a command on a unit.

        :param cmd: Command to be run
        :param unit: Unit object or unit name string
        """
        unit = target if isinstance(target, juju.unit.Unit) else await self.get_unit(target)
        action = await unit.run(cmd)
        await action.wait()
        return action.results

    async def remote_object(self, imports, remote_cmd, target):
        """Run command on target machine and returns a python object of the result.

        :param imports: Imports needed for the command to run
        :param remote_cmd: The python command to execute
        :param target: Unit object or unit name string
        """
        python3 = "python3 -c '{}'"
        python_cmd = (
            "import pickle;"
            "import base64;"
            "{}"
            'print(base64.b64encode(pickle.dumps({})), end="")'.format(imports, remote_cmd)
        )
        cmd = python3.format(python_cmd)
        results = await self.run_command(cmd, target)
        return pickle.loads(base64.b64decode(bytes(results["stdout"][2:-1], "utf8")))

    async def file_stat(self, path, target):
        """Run stat on a file.

        :param path: File path
        :param target: Unit object or unit name string
        """
        imports = "import os;"
        python_cmd = 'os.stat("{}")'.format(path)
        print("Calling remote cmd: " + python_cmd)
        return await self.remote_object(imports, python_cmd, target)

    async def file_exists(self, path, target):
        """Run os.path.isfile() on a file.

        :param path: File path
        :param target: Unit object or unit name string
        """
        imports = "import os;"
        python_cmd = 'os.path.isfile("{}")'.format(path)
        print("Calling remote cmd: " + python_cmd)
        return await self.remote_object(imports, python_cmd, target)

    async def file_contents(self, path, target):
        """Return the contents of a file.

        :param path: File path
        :param target: Unit object or unit name string
        """
        cmd = "cat {}".format(path)
        result = await self.run_command(cmd, target)
        return result["stdout"]

    async def check_file_contents(self, path, target, expected_contents, assert_in=True):
        """Check if a file contains or not from what is expected.

        :param path: File path
        :param target: Unit object or unit name string
        :param expected_contents: List of expected contents
        :assert_in: Assert in by default.
        """
        content = await self.file_contents(path, target)
        for expected_content in expected_contents:
            if assert_in:
                assert expected_content in content
            else:
                assert expected_content not in content

    async def check_file_contents_re(self, path, target, regex):
        """Check if a file contains what is expected using regex.

        :param path: File path
        :param target: Unit object or unit name string
        :param expected_contents: List of expected contents
        :param regex: regular expression to search.
        """
        content = await self.file_contents(path, target)
        assert re.search(regex, content, re.MULTILINE)
