#!/usr/bin/python3

"""
A set of unit tests for the storpool-block layer.
"""

import os
import sys
import testtools

import mock

from charmhelpers.core import hookenv

root_path = os.path.realpath('.')
if root_path not in sys.path:
    sys.path.insert(0, root_path)

lib_path = os.path.realpath('unit_tests/lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

from spcharms import repo as sprepo
from spcharms import status as spstatus
from spcharms import utils as sputils


class MockReactive(object):
    def r_clear_states(self):
        self.states = set()

    def __init__(self):
        self.r_clear_states()

    def set_state(self, name):
        self.states.add(name)

    def remove_state(self, name):
        if name in self.states:
            self.states.remove(name)

    def is_state(self, name):
        return name in self.states

    def r_get_states(self):
        return set(self.states)

    def r_set_states(self, states):
        self.states = set(states)


initializing_config = None


class MockConfig(object):
    def r_clear_config(self):
        global initializing_config
        saved = initializing_config
        initializing_config = self
        self.override = {}
        self.changed_attrs = {}
        self.config = {}
        initializing_config = saved

    def __init__(self):
        self.r_clear_config()

    def r_set(self, key, value, changed):
        self.override[key] = value
        self.changed_attrs[key] = changed

    def get(self, key, default):
        return self.override.get(key, self.config.get(key, default))

    def changed(self, key):
        return self.changed_attrs.get(key, False)

    def __getitem__(self, name):
        # Make sure a KeyError is actually thrown if needed.
        if name in self.override:
            return self.override[name]
        else:
            return self.config[name]

    def __getattr__(self, name):
        return self.config.__getattribute__(name)

    def __setattr__(self, name, value):
        if initializing_config == self:
            return super(MockConfig, self).__setattr__(name, value)

        raise AttributeError('Cannot override the MockConfig '
                             '"{name}" attribute'.format(name=name))


r_state = MockReactive()
r_config = MockConfig()

# Do not give hookenv.config() a chance to run at all
hookenv.config = lambda: r_config


def mock_reactive_states(f):
    def inner1(inst, *args, **kwargs):
        @mock.patch('charms.reactive.set_state', new=r_state.set_state)
        @mock.patch('charms.reactive.remove_state', new=r_state.remove_state)
        @mock.patch('charms.reactive.helpers.is_state', new=r_state.is_state)
        def inner2(*args, **kwargs):
            return f(inst, *args, **kwargs)

        return inner2()

    return inner1


from reactive import storpool_block as testee

INSTALLED_STATE = 'storpool-block.package-installed'
STARTED_STATE = 'storpool-block.block-started'


class TestStorPoolBlock(testtools.TestCase):
    """
    Test various aspects of the storpool-block layer.
    """
    def setUp(self):
        """
        Clean up the reactive states information between tests.
        """
        super(TestStorPoolBlock, self).setUp()
        r_state.r_clear_states()

    @mock_reactive_states
    def test_install_package(self):
        """
        Test that the layer attempts to install packages correctly.
        """
        count_in_lxc = sputils.check_in_lxc.call_count
        count_npset = spstatus.npset.call_count
        count_install = sprepo.install_packages.call_count
        count_record = sprepo.record_packages.call_count

        # First, make sure it does nothing in a container.
        r_state.r_set_states(set())
        sputils.check_in_lxc.return_value = True
        testee.install_package()
        self.assertEquals(count_in_lxc + 1, sputils.check_in_lxc.call_count)
        self.assertEquals(count_npset, spstatus.npset.call_count)
        self.assertEquals(count_install, sprepo.install_packages.call_count)
        self.assertEquals(count_record, sprepo.record_packages.call_count)
        self.assertEquals(set([INSTALLED_STATE]), r_state.r_get_states())

        # Check that it doesn't do anything without a StorPool version
        r_state.r_set_states(set())
        r_config.r_clear_config()
        sputils.check_in_lxc.return_value = False
        testee.install_package()
        self.assertEquals(count_in_lxc + 2, sputils.check_in_lxc.call_count)
        self.assertEquals(count_npset + 1, spstatus.npset.call_count)
        self.assertEquals(count_install, sprepo.install_packages.call_count)
        self.assertEquals(count_record, sprepo.record_packages.call_count)
        self.assertEquals(set(), r_state.r_get_states())

        # Okay, now let's give it something to install... and fail.
        r_config.r_set('storpool_version', '0.1.0', False)
        sprepo.install_packages.return_value = ('oops', [])
        testee.install_package()
        self.assertEquals(count_in_lxc + 3, sputils.check_in_lxc.call_count)
        self.assertEquals(count_npset + 3, spstatus.npset.call_count)
        self.assertEquals(count_install + 1,
                          sprepo.install_packages.call_count)
        self.assertEquals(count_record, sprepo.record_packages.call_count)
        self.assertEquals(set(), r_state.r_get_states())

        # Right, now let's pretend that there was nothing to install
        sprepo.install_packages.return_value = (None, [])
        testee.install_package()
        self.assertEquals(count_in_lxc + 4, sputils.check_in_lxc.call_count)
        self.assertEquals(count_npset + 6, spstatus.npset.call_count)
        self.assertEquals(count_install + 2,
                          sprepo.install_packages.call_count)
        self.assertEquals(count_record, sprepo.record_packages.call_count)
        self.assertEquals(set([INSTALLED_STATE]), r_state.r_get_states())

        # And now for the most common case, something to install...
        r_state.r_set_states(set())
        sprepo.install_packages.return_value = (None, ['storpool-beacon'])
        testee.install_package()
        self.assertEquals(count_in_lxc + 5, sputils.check_in_lxc.call_count)
        self.assertEquals(count_npset + 9, spstatus.npset.call_count)
        self.assertEquals(count_install + 3,
                          sprepo.install_packages.call_count)
        self.assertEquals(count_record + 1, sprepo.record_packages.call_count)
        self.assertEquals(set([INSTALLED_STATE]), r_state.r_get_states())

    @mock_reactive_states
    @mock.patch('charmhelpers.core.host.service_resume')
    def test_enable_and_start(self, service_resume):
        """
        Test that the layer enables the system startup service.
        """
        count_in_lxc = sputils.check_in_lxc.call_count
        count_cgroups = sputils.check_cgroups.call_count

        # First, make sure it does nothing in a container.
        r_state.r_set_states(set())
        sputils.check_in_lxc.return_value = True
        testee.enable_and_start()
        self.assertEquals(count_in_lxc + 1, sputils.check_in_lxc.call_count)
        self.assertEquals(count_cgroups, sputils.check_cgroups.call_count)
        self.assertEquals(set([STARTED_STATE]), r_state.r_get_states())

        # Now make sure it doesn't start if it can't find its control group.
        r_state.r_set_states(set())
        sputils.check_in_lxc.return_value = False
        sputils.check_cgroups.return_value = False
        testee.enable_and_start()
        self.assertEquals(count_in_lxc + 2, sputils.check_in_lxc.call_count)
        self.assertEquals(count_cgroups + 1, sputils.check_cgroups.call_count)
        self.assertEquals(set(), r_state.r_get_states())

        # And now let it run.
        sputils.check_in_lxc.return_value = False
        sputils.check_cgroups.return_value = True
        testee.enable_and_start()
        self.assertEquals(count_in_lxc + 3, sputils.check_in_lxc.call_count)
        self.assertEquals(count_cgroups + 2, sputils.check_cgroups.call_count)
        service_resume.assert_called_once_with('storpool_block')
        self.assertEquals(set([STARTED_STATE]), r_state.r_get_states())
