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
"""Helper functionality for the GBP OBS source service"""

import os
import grp
import pwd
import sys
from multiprocessing import Process, Queue


_RET_FORK_OK = 0
_RET_FORK_ERR = 1


class GbpServiceError(Exception):
    """General error class for the source service"""
    pass

def _demoted_child_call(uid, gid, ret_data_q, func, args, kwargs):
    """Call a function/method with different uid/gid"""
    # Set UID and GID
    try:
        if uid and uid > 0:
            os.setresuid(uid, uid, uid)
        if gid and gid > 0:
            os.setresgid(gid, gid, gid)
    except OSError as err:
        ret_data_q.put(GbpServiceError("Setting UID/GID (%s:%s) failed: %s" %
                                       (uid, gid, err)))
        sys.exit(_RET_FORK_ERR)
    # Call the function
    try:
        ret = func(*args, **kwargs)
    except Exception as err:
        ret_data_q.put(err)
        sys.exit(_RET_FORK_ERR)
    else:
        ret_data_q.put(ret)
    sys.exit(_RET_FORK_OK)

def sanitize_uid_gid(user, group):
    """Get numerical uid and gid"""
    # Get numerical uid and gid
    uid = -1
    gid = -1
    try:
        if user:
            try:
                uid = int(user)
            except ValueError:
                uid = pwd.getpwnam(user).pw_uid
        if group:
            try:
                gid = int(group)
            except ValueError:
                gid = grp.getgrnam(group).gr_gid
    except KeyError as err:
        raise GbpServiceError('Unable to find UID/GID: %s' % err)
    return (uid, gid)

def fork_call(user, group, func, *args, **kwargs):
    """Fork and call a function. The function should return an integer"""
    # Get numerical uid and gid
    uid, gid = sanitize_uid_gid(user, group)

    # Run function in a child process
    data_q = Queue()
    child = Process(target=_demoted_child_call, args=(uid, gid, data_q, func,
                                                      args, kwargs))
    child.start()
    child.join()
    ret_data = data_q.get()
    ret_code = child.exitcode
    if ret_code == _RET_FORK_OK:
        return ret_data
    else:
        raise ret_data

