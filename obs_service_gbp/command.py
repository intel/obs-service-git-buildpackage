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
"""The git-buildpackage source service for OBS"""

import os
import argparse

from gbp.scripts.buildpackage_rpm import main as gbp_rpm

from obs_service_gbp import LOGGER, gbplog, CachedRepo, CachedRepoError

def construct_gbp_args(args):
    """Construct args list for git-buildpackage-rpm"""
    argv = ['argv[0] stub',
            '--git-builder=osc',
            '--git-export-only',
            '--git-ignore-branch']
    if args.outdir:
        argv.append('--git-export-dir=%s' % os.path.abspath(args.outdir))
    else:
        argv.append('--git-export-dir=%s' % os.path.abspath(os.curdir))
    if args.revision:
        argv.append('--git-export=%s' % args.revision)
    if args.verbose == 'yes':
        argv.append('--git-verbose')
    if args.spec_vcs_tag:
        argv.append('--git-spec-vcs-tag=%s' % args.spec_vcs_tag)
    return argv


def parse_args(argv):
    """Argument parser"""

    parser = argparse.ArgumentParser()
    parser.add_argument('--url', help='Remote repository URL', required=True)
    parser.add_argument('--outdir', help='Output direcory')
    parser.add_argument('--revision', help='Remote repository URL',
                        default='HEAD')
    parser.add_argument('--verbose', '-v', help='Verbose output',
                        choices=['yes', 'no'])
    parser.add_argument('--spec-vcs-tag', help='Set/update the VCS tag in the'
                                               'spec file')
    return parser.parse_args(argv)

def main(argv=None):
    """Main function"""

    LOGGER.info('Starting git-buildpackage source service')
    args = parse_args(argv)

    if args.verbose == 'yes':
        gbplog.setup(color='auto', verbose=True)
        LOGGER.setLevel(gbplog.DEBUG)

    # Create / update cached repository
    try:
        repo = CachedRepo(args.url)
        args.revision = repo.update_working_copy(args.revision)
    except CachedRepoError as err:
        LOGGER.error('RepoCache: %s' % str(err))
        return 1

    # Export sources with GBP
    gbp_args = construct_gbp_args(args)
    os.chdir(repo.repodir)
    LOGGER.info('Exporting packaging files with GBP')
    ret = gbp_rpm(gbp_args)
    if ret:
        LOGGER.error('Git-buildpackage-rpm failed, unable to export packaging '
                     'files')
        return 2

    return 0
