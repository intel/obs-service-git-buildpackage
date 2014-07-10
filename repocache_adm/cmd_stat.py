#!/usr/bin/python -u
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
"""The stat subcommand"""

import logging
import os
import subprocess

from repocache_adm.common import SubcommandBase, pprint_sz

class Stat(SubcommandBase):
    """Subcommand for checking the repo cache"""

    name = 'stat'
    description = 'Display repocache status'
    help_msg = None

    @classmethod
    def main(cls, args):
        """Entry point for 'check' subcommand"""

        log = logging.getLogger(cls.name)

        path = os.path.abspath(args.cache_dir)
        if not os.path.isdir(args.cache_dir):
            log.error("repocache basedir '%s' not found", path)
            return 1

        log.info("Checking repository cache in '%s'", path)

        popen = subprocess.Popen(['du', '-d2', '-B1', '-0'], cwd=path,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = popen.communicate()
        if popen.returncode:
            log.error("Failed to run 'du': %s", err)
            return 1

        total_sz = -1
        num_repos = 0
        for line in out.split('\0'):
            if not line:
                continue
            size, name = line.split()
            if name == '.':
                total_sz = int(size)
            else:
                base = os.path.split(name)[0]
                if base != '.':
                    # This is a repository
                    num_repos += 1

        pretty_sz = " (%s)" % pprint_sz(total_sz) if total_sz >= 1024 else ""
        print "Status of %s:" % path
        print "Total of %d repos taking %d bytes%s of disk space" % \
                (num_repos, total_sz, pretty_sz)
        return 0
