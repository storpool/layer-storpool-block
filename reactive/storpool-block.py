from __future__ import print_function

import pwd
import os
import tempfile
import time
import subprocess

from charmhelpers.core import templating

from charms import reactive
from charms.reactive import helpers as rhelpers
from charmhelpers.core import hookenv, host

from spcharms import repo as sprepo

def rdebug(s):
	with open('/tmp/storpool-charms.log', 'a') as f:
		print('{tm} [block] {s}'.format(tm=time.ctime(), s=s), file=f)

@reactive.when('storpool-repo-add.available', 'storpool-common.config-written')
@reactive.when_not('storpool-block.package-installed')
@reactive.when_not('storpool-block.stopping')
def install_package():
	rdebug('the block repo has become available and the common packages have been configured')
	hookenv.status_set('maintenance', 'installing the StorPool block packages')
	(err, newly_installed) = sprepo.install_packages({
		'storpool-block': '16.02.25.744ebef-1ubuntu1',
	})
	if err is not None:
		rdebug('oof, we could not install packages: {err}'.format(err=err))
		rdebug('removing the package-installed state')
		return

	if newly_installed:
		rdebug('it seems we managed to install some packages: {names}'.format(names=newly_installed))
		sprepo.record_packages(newly_installed)
	else:
		rdebug('it seems that all the packages were installed already')

	rdebug('setting the package-installed state')
	reactive.set_state('storpool-block.package-installed')
	hookenv.status_set('maintenance', '')

@reactive.when('storpool-block.package-installed')
@reactive.when('storpool-beacon.beacon-started')
@reactive.when_not('storpool-block.block-started')
@reactive.when_not('storpool-block.stopping')
def enable_and_start():
	rdebug('enabling and starting the block service')
	host.service_resume('storpool_block')
	reactive.set_state('storpool-block.block-started')

@reactive.when('storpool-block.block-started')
@reactive.when_not('storpool-block.package-installed')
@reactive.when_not('storpool-block.stopping')
def restart():
	reactive.remove_state('storpool-block.block-started')

@reactive.when('storpool-block.block-started')
@reactive.when_not('storpool-beacon.beacon-started')
@reactive.when_not('storpool-block.stopping')
def restart_even_better():
	reactive.remove_state('storpool-block.block-started')

@reactive.when('storpool-block.package-installed')
@reactive.when_not('storpool-common.config-written')
@reactive.when_not('storpool-block.stopping')
def reinstall():
	reactive.remove_state('storpool-block.package-installed')

def reset_states():
	rdebug('state reset requested')
	reactive.remove_state('storpool-block.package-installed')
	reactive.remove_state('storpool-block.block-started')

@reactive.hook('upgrade-charm')
def remove_states_on_upgrade():
	rdebug('storpool-block.upgrade-charm invoked')
	reset_states()

@reactive.hook('stop')
def remove_leftovers():
	rdebug('storpool-block.stop invoked')
	reactive.set_state('storpool-block.stopping')
	reset_states()

	rdebug('stopping and disabling the storpool_block service')
	host.service_pause('storpool_block')
