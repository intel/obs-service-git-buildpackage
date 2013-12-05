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
"""Git repository cache"""

import os
import hashlib
import shutil
import fcntl

import gbp.log as gbplog
from gbp.git.repository import GitRepository, GitRepositoryError


# Setup logging
LOGGER = gbplog.getLogger('gbp-repocache')
LOGGER.setLevel(gbplog.INFO)


class MirrorGitRepository(GitRepository): # pylint: disable=R0904
    """Special Git repository to enable a mirrored clone with a working copy"""

    def set_config(self, name, value, replace=False):
        """Add a config value"""
        args = ['--replace-all'] if replace else ['--add']
        args.extend([name, value])
        stderr, ret = self._git_inout('config', args)[1:]
        if ret:
            raise GitRepositoryError('Failed to set config %s=%s (%s)' %
                                     (name, value, stderr))

    def force_fetch(self):
        """Fetch with specific arguments"""
        # Update all refs
        self._git_command('fetch', ['-q', '-u', '-p', 'origin'])
        try:
            # Fetch remote HEAD separately
            self._git_command('fetch', ['-q', '-u', 'origin', 'HEAD'])
        except GitRepositoryError:
            # If remote HEAD is invalid, invalidate FETCH_HEAD, too
            with open(os.path.join(self.git_dir, 'FETCH_HEAD'), 'w') as fhead:
                fhead.write('0000000000000000000000000000000000000000\n')

    def force_checkout(self, commitish):
        """Checkout commitish"""
        self._git_command("checkout", ['--force', commitish])

    def force_clean(self):
        """Clean repository"""
        self._git_command('clean', ['-f', '-d', '-x'])

    @classmethod
    def clone(cls, path, url, bare=False):
        """Create a mirrored clone"""
        if bare:
            return super(MirrorGitRepository, cls).clone(path, url,
                                                         mirror=bare,
                                                         auto_name=False)
        else:
            LOGGER.debug('Initializing non-bare mirrored repo')
            repo = cls.create(path)
            repo.add_remote_repo('origin', url)
            repo.set_config('remote.origin.fetch', '+refs/*:refs/*', True)
            repo.force_fetch()
            return repo


class CachedRepoError(Exception):
    """Repository cache errors"""
    pass


class CachedRepo(object):
    """Object representing a cached repository"""

    def __init__(self, base_dir, url, bare=False):
        self.basedir = base_dir
        self.repodir = None
        self.repo = None
        self.lock = None

        # Safe repo dir name
        urlbase, reponame = self._split_url(url)
        subdir = hashlib.sha1(urlbase).hexdigest() # pylint: disable=E1101
        self.repodir = os.path.join(self.basedir, subdir, reponame)

        self._init_cache_dir()
        self._init_git_repo(url, bare)

    def _init_cache_dir(self):
        """Check and initialize repository cache base directory"""
        LOGGER.debug("Using cache basedir '%s'", self.basedir)
        _subdir = os.path.dirname(self.repodir)
        if not os.path.exists(_subdir):
            LOGGER.debug('Creating missing cache subdir %s', _subdir)
            try:
                os.makedirs(_subdir)
            except OSError as err:
                raise CachedRepoError('Failed to create cache subdir %s: %s' %
                                      (_subdir, str(err)))

    def _acquire_lock(self, repodir):
        """Acquire the repository lock"""
        LOGGER.debug("Acquiring repository lock for %s", repodir)
        try:
            self.lock = open(repodir + '.lock', 'w')
        except IOError as err:
            raise CachedRepoError('Unable to open repo lock file: %s' % err)
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        LOGGER.debug("Repository lock acquired")

    def _release_lock(self):
        """Release the repository lock"""
        if self.lock:
            fcntl.flock(self.lock, fcntl.LOCK_UN)
            self.lock = None

    @staticmethod
    def _split_url(url):
        """Split URL to base and reponame

        >>> CachedRepo._split_url('http://foo.com/bar')
        ('http://foo.com', 'bar')
        >>> CachedRepo._split_url('foo.com:bar')
        ('foo.com', 'bar')
        >>> CachedRepo._split_url('/foo/bar')
        ('/foo', 'bar')
        >>> CachedRepo._split_url('foo/')
        ('', 'foo')
        """
        sanitized = url.rstrip('/')
        split = sanitized.rsplit('/', 1)
        # Try to get base right for ssh-style "URLs", like git@github.com:foo
        if len(split) == 1:
            split = sanitized.rsplit(':', 1)
        base = split[0] if len(split) > 1 else ''
        repo = split[-1]
        return (base, repo)

    def _init_git_repo(self, url, bare):
        """Clone / update a remote git repository"""
        LOGGER.debug('Caching %s in %s', url, self.repodir)
        # Create subdir, if it doesn't exist
        if not os.path.exists(os.path.dirname(self.repodir)):
            os.makedirs(os.path.dirname(self.repodir))
        # Acquire repository lock
        self._acquire_lock(self.repodir)

        if os.path.exists(self.repodir):
            try:
                self.repo = MirrorGitRepository(self.repodir)
            except GitRepositoryError:
                pass
            if not self.repo or self.repo.bare != bare:
                LOGGER.info('Removing corrupted repo cache %s', self.repodir)
                try:
                    self.repo = None
                    shutil.rmtree(self.repodir)
                except OSError as err:
                    raise CachedRepoError('Failed to remove repo cache dir: %s'
                                         % str(err))
            else:
                LOGGER.info('Fetching from remote')
                try:
                    self.repo.force_fetch()
                except GitRepositoryError as err:
                    raise CachedRepoError('Failed to fetch from remote: %s' %
                                           err)
        if not self.repo:
            LOGGER.info('Cloning from %s', url)
            try:
                self.repo = MirrorGitRepository.clone(self.repodir, url,
                                                      bare=bare)
            except GitRepositoryError as err:
                raise CachedRepoError('Failed to clone: %s' % err)

    def __del__(self):
        self._release_lock()

    def update_working_copy(self, commitish='HEAD', submodules=True):
        """Reset HEAD to the given commit-ish"""
        if self.repo.bare:
            raise CachedRepoError('Cannot update working copy of a bare repo')

        # Update HEAD from FETCH_HEAD, so that HEAD points to remote HEAD.
        # We do it this way because FETCH_HEAD may point to an invalid object
        # and we don't wont to update the working copy at this point.
        shutil.copyfile(os.path.join(self.repo.git_dir, 'FETCH_HEAD'),
                        os.path.join(self.repo.git_dir, 'HEAD'))
        # Clean: just in case - this should be never ever really be necessary
        # unless somebody manually hacks the cached repository introducing
        # local changes
        self.repo.force_clean()
        # Resolve commit-ish to sha-1 and set HEAD (and working copy) to it
        try:
            sha = self.repo.rev_parse(commitish)
            self.repo.force_checkout(sha)
        except GitRepositoryError as err:
            raise CachedRepoError("Unknown ref '%s': %s" % (commitish, err))
        self.repo.force_head(sha, hard=True)
        if submodules:
            self.repo.update_submodules(init=True, recursive=True, fetch=True)
        return sha

