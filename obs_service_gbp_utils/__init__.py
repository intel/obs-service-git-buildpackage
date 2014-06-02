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

import json
import os
import grp
import pwd
import sys
from functools import partial
from multiprocessing import Process, Queue
from traceback import format_exception_only, extract_tb, format_list

_RET_FORK_OK = 0
_RET_FORK_ERR = 1


class GbpServiceError(Exception):
    """General error class for the source service"""
    pass

class GbpChildBTError(Exception):
    """Exception for handling unhandled child exceptions in fork_call()"""
    def __init__(self, *args):
        self.typ, self.val, traceback = sys.exc_info()
        self.tb_list = extract_tb(traceback)
        super(GbpChildBTError, self).__init__(*args)

    def prettyprint_tb(self):
        """Get traceback in a format easier to comprehend"""
        child_tb = format_list(self.tb_list)
        child_tb += format_exception_only(self.typ, self.val)
        sep = '-' * 4 + ' CHILD TRACEBACK ' + '-' * 50 + '\n'
        pp_tb = sep + ''.join(child_tb) + sep
        return pp_tb


def _demoted_child_call(uid, gid, ret_data_q, func):
    """Call a function/method with different uid/gid"""
    # Set UID and GID
    try:
        if uid and uid > 0:
            os.setresuid(uid, uid, uid)
            # Set environment
            os.environ['HOME'] = pwd.getpwuid(uid).pw_dir
        if gid and gid > 0:
            os.setresgid(gid, gid, gid)
    except OSError as err:
        ret_data_q.put(GbpServiceError("Setting UID/GID (%s:%s) failed: %s" %
                                       (uid, gid, err)))
        sys.exit(_RET_FORK_ERR)
    # Call the function
    try:
        # Func must be a callable without arguments
        ret = func()
    except Exception as err:
        ret_data_q.put(GbpChildBTError())
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

def _fork_call(user, group, func, *args, **kwargs):
    """Wrapper for actual logic of fork_call()"""
    # Get numerical uid and gid
    uid, gid = sanitize_uid_gid(user, group)

    # Run function in a child process
    data_q = Queue()
    child = Process(target=_demoted_child_call,
                    args=(uid, gid, data_q, partial(func, *args, **kwargs)))
    child.start()
    child.join()
    ret_data = data_q.get()
    ret_code = child.exitcode
    if ret_code == _RET_FORK_OK:
        return ret_data
    else:
        raise ret_data

def fork_call(user, group, func):
    """Fork and call a function. The function should return an integer.
       Returns a callable that runs the function."""
    return partial(_fork_call, user, group, func)

def _commit_info_in_json(repo, committish):
    """Get info about a committish in json-serializable format"""
    ret = {}
    info = repo.get_commit_info(committish)
    ret['sha1'] = repo.rev_parse('%s^0' % committish)
    ret['subject'] = info['subject']
    ret['body'] = info['body']
    ret['author'] = {'name': info['author'].name,
                     'email': info['author'].email,
                     'date': info['author'].date}
    ret['committer'] = {'name': info['committer'].name,
                        'email': info['committer'].email,
                        'date': info['committer'].date}
    ret['files'] = info['files']
    return ret

def _tag_list_in_json(repo, treeish):
    """Get list of tags pointing to a treeish object in json format"""
    # Get information about (annotated) tags pointing to the treeish object
    info = []
    for tag in repo.list_tags(treeish):
        # Only take annotated tags, and, filter out the treeish itself in case
        # it is a tag.
        if (repo.get_obj_type(tag) == 'tag' and
            repo.rev_parse(tag) != repo.rev_parse(treeish)):
            info.append(repo.get_tag_info(tag))
    return info

def write_treeish_meta(repo, treeish, outdir, filename):
    """Write all information about a treeish in json format to a file"""
    meta = {'treeish': treeish}
    obj_type = repo.get_obj_type(treeish)
    if obj_type == 'tag':
        meta['tag'] = repo.get_tag_info(treeish)
        meta['tag']['tags'] = _tag_list_in_json(repo, treeish)
    if obj_type in ('tag', 'commit'):
        meta['commit'] = _commit_info_in_json(repo, treeish)
        # Get information about (annotated) tags pointing to the commit
        meta['commit']['tags'] = []
        meta['commit']['tags'] = _tag_list_in_json(repo, treeish + '^0')

    # No dir components allowed in filename
    filepath = os.path.join(outdir, os.path.basename(filename))

    if os.path.exists(filepath):
        raise GbpServiceError("File '%s' already exists, refusing to "
                              "overwrite" % filename)
    try:
        with open(filepath, 'w') as meta_fp:
            json.dump(meta, meta_fp, indent=4)
    except IOError as err:
        raise GbpServiceError("Failed to write '%s': %s" % (filename, err))

