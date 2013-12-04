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
"""Tests for the GBP OBS service helper functionality"""

import grp
import pwd
import os
from nose.tools import assert_raises, eq_, ok_  # pylint: disable=E0611
from multiprocessing import Queue

from obs_service_gbp_utils import (fork_call, _demoted_child_call,
                                   GbpServiceError, _RET_FORK_OK)


class _DummyException(Exception):
    """Dummy exception for testing"""
    pass

class TestForkCall(object):
    """Test the functionality for calling functions in a child thread"""

    def __init__(self):
        self._uid = os.getuid()
        self._gid = os.getgid()
        self._name = pwd.getpwuid(self._uid).pw_name
        self._group = grp.getgrgid(self._gid).gr_name

    @staticmethod
    def _no_fork_call(uid, gid, func, *args, **kwargs):
        """For testing demoted call without actually forking"""
        data_q = Queue()
        try:
            _demoted_child_call(uid, gid, data_q, func, args, kwargs)
        except SystemExit as err:
            ret_code = err.code
        ret_data = data_q.get()
        if ret_code == _RET_FORK_OK:
            return ret_data
        else:
            raise ret_data

    @staticmethod
    def _dummy_ok():
        """Helper method returning 'ok'"""
        return 'ok'

    @staticmethod
    def _dummy_raise():
        """Helper method raising an exception"""
        raise _DummyException('Dummy error')

    @staticmethod
    def _dummy_args(arg1, arg2, arg3):
        """Helper method returning all its args"""
        return (arg1, arg2, arg3)

    def test_success(self):
        """Basic test for successful call"""
        eq_(fork_call(None, None, self._dummy_ok), 'ok')

        eq_(fork_call(None, None, self._dummy_args, 1, '2', arg3='foo'),
            (1, '2', 'foo'))

        ok_(os.getpid() != fork_call(None, None, os.getpid))

    def test_fail(self):
        """Tests for function call failures"""
        with assert_raises(_DummyException):
            fork_call(None, None, self._dummy_raise)

        with assert_raises(TypeError):
            fork_call(None, None, self._dummy_ok, 'unexptected_arg')

    def test_demoted_call_no(self):
        """Test running with different UID/GID"""
        eq_(fork_call(self._name, self._group, self._dummy_ok), 'ok')
        eq_(fork_call(self._uid, None, self._dummy_ok), 'ok')
        eq_(fork_call(None, self._gid, self._dummy_ok), 'ok')

        eq_(self._no_fork_call(self._uid, self._gid, self._dummy_ok), 'ok')

    def test_demoted_call_fail(self):
        """Test running with invalid UID/GID"""
        with assert_raises(GbpServiceError):
            fork_call('_non_existent_user', None, self._dummy_ok)
        with assert_raises(GbpServiceError):
            fork_call(None, '_non_existen_group', self._dummy_ok)

        with assert_raises(GbpServiceError):
            self._no_fork_call(99999, None, self._dummy_ok)
        with assert_raises(GbpServiceError):
            self._no_fork_call(None, 99999, self._dummy_ok)
        with assert_raises(_DummyException):
            self._no_fork_call(self._uid, self._gid, self._dummy_raise)

