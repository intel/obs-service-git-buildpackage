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
import shutil
import tempfile
from ConfigParser import SafeConfigParser

from gbp.rpm import guess_spec, NoSpecError
from gbp.scripts.buildpackage import main as gbp_deb
from gbp.scripts.buildpackage_rpm import main as gbp_rpm

from obs_service_gbp import LOGGER, gbplog
from obs_service_gbp_utils import GbpServiceError, GbpChildBTError, fork_call
from obs_service_gbp_utils import sanitize_uid_gid, write_treeish_meta
from gbp_repocache import CachedRepo, CachedRepoError
import gbp_repocache

def have_spec(directory):
    """Find if the package has spec files"""
    try:
        guess_spec(directory, recursive=True)
    except NoSpecError as err:
        if str(err).startswith('No spec file'):
            return False
    return True

def construct_gbp_args(args, config, outdir):
    """Construct args list for git-buildpackage-rpm"""
    # Args common to deb and rpm
    argv_common = ['--git-ignore-branch',
                   '--git-no-hooks',
                   '--git-notify=off',
                   '--git-export-dir=%s' % outdir,
                   '--git-tmp-dir=%s' % config['gbp-tmp-dir']]
    if args.revision:
        argv_common.append('--git-export=%s' % args.revision)
    if args.verbose == 'yes':
        argv_common.append('--git-verbose')

    # Dermine deb and rpm specific args
    argv_rpm = ['git-buildpackage-rpm'] + argv_common
    argv_rpm.extend(['--git-builder=osc',
                     '--git-export-only'])
    if args.spec_vcs_tag:
        argv_rpm.append('--git-spec-vcs-tag=%s' % args.spec_vcs_tag)

    # We need to build this way (i.e. run outside the sources directory)
    # because if run with '-b .' dpkg-source will put it's output to different
    # directory, depending on the version of dpkg
    deb_builder_script = 'cd ..; dpkg-source -b $GBP_BUILD_DIR'
    argv_deb = ['git-buildpackage'] + argv_common
    argv_deb.extend(['--git-purge',
                     '--git-builder=%s' % deb_builder_script])
    return (argv_rpm, argv_deb)

def read_config(filenames):
    '''Read configuration file(s)'''
    defaults = {'repo-cache-dir': '/var/cache/obs/git-buildpackage-repos/',
                'gbp-tmp-dir': '/tmp/obs-service-gbp/',
                'gbp-user': None,
                'gbp-group': None}

    filenames = [os.path.expanduser(fname) for fname in filenames]
    LOGGER.debug('Trying %s config files: %s', len(filenames), filenames)
    parser = SafeConfigParser(defaults=defaults)
    read = parser.read(filenames)
    LOGGER.debug('Read %s config files: %s', len(read), read)

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

def gbp_export(repo, args, config):
    """Export sources with GBP"""
    # Create output directories
    try:
        if not os.path.exists(args.outdir):
            os.makedirs(args.outdir)
        tmp_out = tempfile.mkdtemp(dir=args.outdir)
    except OSError as err:
        LOGGER.error('Failed to create output directory: %s', err)
        return 1
    # Determine UID/GID
    try:
        uid, gid = sanitize_uid_gid(config['gbp-user'], config['gbp-group'])
    except GbpServiceError as err:
        LOGGER.error(err)
        return 1
    # Make temp outdir accessible to the GBP UID/GID
    os.chown(tmp_out, uid, gid)

    # Call GBP
    rpm_args, deb_args = construct_gbp_args(args, config, tmp_out)
    orig_dir = os.path.abspath(os.curdir)
    try:
        os.chdir(repo.repodir)
        specs_found = have_spec('.')
        if args.rpm == 'yes' or (args.rpm == 'auto' and specs_found):
            LOGGER.info('Exporting RPM packaging files with GBP')
            LOGGER.debug('git-buildpackage-rpm args: %s', ' '.join(rpm_args))
            ret = fork_call(uid, gid, gbp_rpm)(rpm_args)
            if ret:
                LOGGER.error('Git-buildpackage-rpm failed, unable to export '
                             'RPM packaging files')
                return 2
        if args.deb == 'yes' or (args.deb== 'auto' and os.path.isdir('debian')):
            LOGGER.info('Exporting Debian source package with GBP')
            LOGGER.debug('git-buildpackage args: %s', ' '.join(deb_args))
            ret = fork_call(uid, gid, gbp_deb)(deb_args)
            if ret:
                LOGGER.error('Git-buildpackage failed, unable to export Debian '
                             'sources package files')
                return 3
        for fname in os.listdir(tmp_out):
            shutil.move(os.path.join(tmp_out, fname),
                        os.path.join(args.outdir, fname))
    except GbpChildBTError as err:
        LOGGER.error('Unhandled exception in GBP:\n'
                     '%s', err.prettyprint_tb())
        LOGGER.error('Failed to export packaging files')
        return 1
    except GbpServiceError as err:
        LOGGER.error('Internal service error when trying to run GBP: %s', err)
        LOGGER.error('This is most likely a configuration error (or a BUG)!')
        return 1
    finally:
        os.chdir(orig_dir)
        shutil.rmtree(tmp_out)
    return 0

def parse_args(argv):
    """Argument parser"""
    default_configs = ['/etc/obs/services/git-buildpackage',
                       '~/.obs/git-buildpackage']

    parser = argparse.ArgumentParser()
    parser.add_argument('--url', help='Remote repository URL', required=True)
    parser.add_argument('--outdir', default='.', help='Output direcory')
    parser.add_argument('--revision', help='Remote repository URL',
                        default='HEAD')
    parser.add_argument('--rpm', choices=['auto', 'yes', 'no'], default='auto',
                        help='Export RPM packaging files')
    parser.add_argument('--deb', choices=['auto', 'yes', 'no'], default='auto',
                        help='Export Debian packaging files')
    parser.add_argument('--verbose', '-v', help='Verbose output',
                        choices=['yes', 'no'])
    parser.add_argument('--spec-vcs-tag', help='Set/update the VCS tag in the'
                                               'spec file')
    parser.add_argument('--config', action='append',
                        help='Config file to use, can be given multiple times')
    parser.add_argument('--git-meta', metavar='FILENAME',
                        help='Write data about the exported revision into '
                             'FILENAME in json format')
    args = parser.parse_args(argv)
    args.outdir = os.path.abspath(args.outdir)

    # Use default config files if --config was not defined
    if args.config is None:
        args.config = default_configs

    return args

def main(argv=None):
    """Main function"""

    args = parse_args(argv)

    LOGGER.info('Starting git-buildpackage source service')
    if args.verbose == 'yes':
        gbplog.setup(color='auto', verbose=True)
        LOGGER.setLevel(gbplog.DEBUG)
        gbp_repocache.LOGGER.setLevel(gbplog.DEBUG)

    config = read_config(args.config)

    # Create / update cached repository
    try:
        repo = CachedRepo(config['repo-cache-dir'], args.url)
        args.revision = repo.update_working_copy(args.revision)
    except CachedRepoError as err:
        LOGGER.error('RepoCache: %s', str(err))
        return 1

    # Run GBP
    ret = gbp_export(repo, args, config)

    # Write git meta file
    if not ret and args.git_meta:
        try:
            write_treeish_meta(repo.repo, args.revision, args.outdir,
                               args.git_meta)
        except GbpServiceError as err:
            LOGGER.error(err)
            ret = 1
    return ret
