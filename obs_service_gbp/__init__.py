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
"""Helpers for the git-buildpackage OBS source service"""

import os
import sys
import hashlib
import shutil
import fcntl

import gbp.log as gbplog
from gbp.git.repository import GitRepository, GitRepositoryError


# Setup logging
logger = gbplog.getLogger('source_service')
logger.setLevel(gbplog.INFO)

class CachedRepoError(Exception):
    """Repository cache errors"""
    pass


class CachedRepo(object):
    """Object representing a cached repository"""

    def __init__(self, url):
        self.basedir = '/var/cache/obs/git-buildpackage-repos/'
        self.repodir = None
        self.repo = None
        self.lock = None

        # Check repository cache base
        if 'CACHEDIR' in os.environ:
            self.basedir = os.environ['CACHEDIR']
        logger.debug("Using cache basedir '%s'" % self.basedir)
        if not os.path.exists(self.basedir):
            logger.debug('Creating missing cache basedir')
            try:
                os.makedirs(self.basedir)
            except OSError as err:
                raise CachedRepoError('Failed to create cache base dir: %s' %
                                     str(err))

        # Safe dir name
        reponame = url.split('/')[-1].split(':')[-1]
        postfix = hashlib.sha1(url).hexdigest()
        reponame = reponame + '_' + postfix
        self.repodir = os.path.join(self.basedir, reponame)

        # Acquire lock
        logger.debug("Acquiring repository lock")
        try:
            self.lock = open(self.repodir + '.lock', 'w')
        except IOError as err:
            raise CachedRepoError('Unable to open repo lock file: %s' % err)
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        logger.debug("Repository lock acquired")

        # Update repo cache
        if os.path.exists(self.repodir):
            try:
                self.repo = GitRepository(self.repodir)
            except GitRepositoryError:
                pass
            if not self.repo:
                logger.info('Removing corrupted repo cache %s' % self.repodir)
                try:
                    shutil.rmtree(self.repodir)
                except OSError as err:
                    raise CachedRepoError('Failed to remove repo cache dir: %s'
                                         % str(err))
            else:
                logger.info('Fetching from remote')
                self.repo.fetch()

        if not self.repo:
            logger.info('Cloning from %s' % url)
            try:
                self.repo = GitRepository.clone(self.repodir, url,
                                                mirror=True, auto_name=False)
            except GitRepositoryError as err:
                raise CachedRepoError('Failed to clone: %s' % str(err))

    def _release_lock(self):
        """Release the repository lock"""
        if self.lock:
            fcntl.flock(self.lock, fcntl.LOCK_UN)

    def __del__(self):
        self._release_lock()

