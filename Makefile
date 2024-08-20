# This is a template `Makefile` file for reactive charms
# This file is managed by bootstack-charms-spec and should not be modified
# within individual charm repos. https://launchpad.net/bootstack-charms-spec

PYTHON := /usr/bin/python3

PROJECTPATH=$(dir $(realpath $(MAKEFILE_LIST)))
CHARM_BUILD_DIR:=${PROJECTPATH}.build
CHARM_LAYERS_DIR:=${PROJECTPATH}/layers
CHARM_INTERFACES_DIR:=${PROJECTPATH}/interfaces
RELEASE_CHANNEL:=edge
METADATA_FILE="src/metadata.yaml"
CHARM_NAME=$(shell cat ${PROJECTPATH}/${METADATA_FILE} | grep -E '^name:' | awk '{print $$2}')

help:
	@echo "This project supports the following targets"
	@echo ""
	@echo " make help - show this text"
	@echo " make dev-environment - setup the development environment"
	@echo " make pre-commit - run pre-commit checks on all the files"
	@echo " make submodules - initialize, fetch, and checkout any nested submodules"
	@echo " make submodules-update - update submodules to latest changes on remote branch"
	@echo " make clean - remove unneeded files and clean charmcraft environment"
	@echo " make build - build the charm"
	@echo " make lint - run flake8, black --check and isort --check"
	@echo " make reformat - run black and isort and reformat files"
	@echo " make unittests - run the tests defined in the unittest subdirectory"
	@echo " make functional - run the tests defined in the functional subdirectory"
	@echo " make test - run lint, unittests and functional targets"
	@echo ""

dev-environment:
	@echo "Creating virtualenv with pre-commit installed"
	@tox -r -e dev-environment

pre-commit:
	@tox -e pre-commit

submodules:
	@echo "Cloning submodules"
	@git submodule update --init --recursive

submodules-update:
	@echo "Pulling latest updates for submodules"
	@git submodule update --init --recursive --remote --merge

clean:
	@echo "Cleaning files"
	@git clean -ffXd -e '!.idea' -e '!.vscode'
	@echo "Cleaning existing build"
	@rm -rf ${CHARM_BUILD_DIR}/${CHARM_NAME}
	@rm -rf ${PROJECTPATH}/${CHARM_NAME}*.charm
	@echo "Cleaning charmcraft"
	@charmcraft clean

build: clean
	@echo "Building charm"
	@charmcraft -v pack ${BUILD_ARGS}
	@bash -c ./rename.sh

lint:
	@echo "Running lint checks"
	@tox -e lint

reformat:
	@echo "Reformat files with black and isort"
	@tox -e reformat

unittests:
	@echo "Running unit tests"
	@tox -e unit -- ${UNIT_ARGS}

functional: build
	@echo "Executing functional tests with ${PROJECTPATH}/${CHARM_NAME}.charm"
	@CHARM_LOCATION=${PROJECTPATH} tox -e func -- ${FUNC_ARGS}

test: lint unittests functional
	@echo "Tests completed for charm ${CHARM_NAME}."

# The targets below don't depend on a file
.PHONY: help dev-environment pre-commit submodules submodules-update clean build lint reformat unittests functional
