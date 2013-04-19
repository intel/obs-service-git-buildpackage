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

from ConfigParser import SafeConfigParser
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

def read_config(filenames):
    '''Read configuration file(s)'''
    defaults = {'repo-cache-dir': '/var/cache/obs/git-buildpackage-repos/'}

    filenames = [os.path.expanduser(fname) for fname in filenames]
    LOGGER.debug('Trying %s config files: %s' % (len(filenames), filenames))
    parser = SafeConfigParser(defaults=defaults)
    read = parser.read(filenames)
    LOGGER.debug('Read %s config files: %s' % (len(read), read))

    # Add our one-and-only section, if it does not exist
    if not parser.has_section('general'):
        parser.add_section('general')

    # Read overrides from environment
    for key in defaults.keys():
        envvar ='OBS_GIT_BUILDPACKAGE_%s' % key.replace('-', '_').upper()
        if envvar in os.environ:
            parser.set('general', key, os.environ[envvar])

    # We only use keys from one section, for now
    return dict(parser.items('general'))

def parse_args(argv):
    """Argument parser"""
    default_configs = ['/etc/obs/services/git-buildpackage',
                       '~/.obs/git-buildpackage']

    parser = argparse.ArgumentParser()
    parser.add_argument('--url', help='Remote repository URL', required=True)
    parser.add_argument('--outdir', help='Output direcory')
    parser.add_argument('--revision', help='Remote repository URL',
                        default='HEAD')
    parser.add_argument('--verbose', '-v', help='Verbose output',
                        choices=['yes', 'no'])
    parser.add_argument('--spec-vcs-tag', help='Set/update the VCS tag in the'
                                               'spec file')
    parser.add_argument('--config', default=default_configs, action='append',
                        help='Config file to use, can be given multiple times')
    return parser.parse_args(argv)

def main(argv=None):
    """Main function"""

    args = parse_args(argv)

    LOGGER.info('Starting git-buildpackage source service')
    if args.verbose == 'yes':
        gbplog.setup(color='auto', verbose=True)
        LOGGER.setLevel(gbplog.DEBUG)

    config = read_config(args.config)

    # Create / update cached repository
    try:
        repo = CachedRepo(config['repo-cache-dir'], args.url)
        args.revision = repo.update_working_copy(args.revision)
    except CachedRepoError as err:
        LOGGER.error('RepoCache: %s' % str(err))
        return 1

    # Export sources with GBP
    gbp_args = construct_gbp_args(args)
    orig_dir = os.path.abspath(os.curdir)
    try:
        os.chdir(repo.repodir)
        LOGGER.info('Exporting packaging files with GBP')
        ret = gbp_rpm(gbp_args)
    finally:
        os.chdir(orig_dir)
    if ret:
        LOGGER.error('Git-buildpackage-rpm failed, unable to export packaging '
                 'files')
        return 2

    return 0
