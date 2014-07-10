# vim:fileencoding=utf-8:et:ts=4:sw=4:sts=4
#
# Copyright (C) 2013 Intel Corporation <markus.lehtonen@linux.intel.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301, USA.
"""Unit tests for the repocache-adm command line tool"""

import mock
import os
import shutil
from nose.tools import assert_raises, eq_  # pylint: disable=E0611

from gbp_repocache import CachedRepo
from repocache_adm.adm import main as adm
from repocache_adm.common import SubcommandBase
from tests import UnitTestsBase

# Disable "Method could be a function"
#   pylint: disable=R0201
# Disable "Method 'main' is abstract in class 'XYZ' but is not overridden"
#   pylint: disable=W0223


class BadSubcommand(SubcommandBase):
    """Broken subcommand"""
    name = 'stat'

class TestRepocacheAdm(UnitTestsBase):
    """Test repocache-adm command line tool"""

    @classmethod
    def setup_class(cls):
        """Test class setup"""
        super(TestRepocacheAdm, cls).setup_class()

        # Create another orig repo for testing
        cls._template_repo2 = cls.create_orig_repo('orig2')

        # Create a reference cache
        cls._template_cache = os.path.abspath('cache')
        # Create cached repos - need to del instances to release the repo lock
        _cached = CachedRepo(cls._template_cache, cls._template_repo.path,
                             bare=False)
        del _cached
        _cached = CachedRepo(cls._template_cache, cls._template_repo2.path,
                             bare=True)
        del _cached

    def setup(self):
        """Test case setup"""
        super(TestRepocacheAdm, self).setup()

        # Create test-case specific cache
        shutil.copytree(self._template_cache, self.cachedir)

    @mock.patch('repocache_adm.adm.Stat', BadSubcommand)
    def test_not_implemented(self):
        """Test a badly written subcommand"""
        with assert_raises(NotImplementedError):
            adm(['-c', self.cachedir, 'stat'])

    def test_invalid_args(self):
        """Test invalid command line args"""
        # Non-existing option
        with assert_raises(SystemExit):
            adm(['--foo'])
        # Option without argument
        with assert_raises(SystemExit):
            adm(['-c'])
        # Unknown subcommand
        with assert_raises(SystemExit):
            adm(['foocmd'])

    def test_stat(self):
        """Basic test for the 'stat' subcommand"""
        # With debug
        eq_(adm(['-d', '-c', self.cachedir, 'stat']), 0)

    def test_stat_fail(self):
        """Failure cases for the 'stat' subcommand"""
        # Non-existent cache dir
        eq_(adm(['-c', 'non-existent', 'stat']), 1)

