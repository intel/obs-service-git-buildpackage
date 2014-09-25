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

import logging
import os
import hashlib
import shutil
import fcntl
import re

from gbp.git.repository import GitRepository, GitRepositoryError


# Setup logging
LOGGER = logging.getLogger('gbp-repocache')


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

    def get_ref(self, ref):
        """Get a ref - i.e. where it points to"""
        stdout, _stderr, ret = self._git_inout('symbolic-ref', [ref],
                                               capture_stderr=True)
        if ret:
            return self.rev_parse(ref)
        else:
            return stdout.splitlines()[0]

    def set_ref(self, ref, value):
        """Change a ref"""
        if value.startswith('refs/'):
            _stdout, stderr, ret = self._git_inout('symbolic-ref',
                                                   ['-q', ref, value],
                                                   capture_stderr=True)
            # Currently, git-symbolic-ref always exits with 0.
            # Thus, we check stderr, too
            if ret or stderr:
                raise GitRepositoryError('Failed to set symbolic ref: %s' %
                                         stderr)
        else:
            # Write directly to the file. This is not as intelligent as
            # git-update-ref but this way we can set the ref to anything
            # (e.g. an non-existent sha-1)
            try:
                with open(os.path.join(self.git_dir, ref), 'w') as ref_file:
                    ref_file.write(value + '\n')
            except IOError as err:
                raise GitRepositoryError('Failed write ref %s: %s' % (ref, err))

    def _symlink_refs(self, tgt_path):
        """Symlink refs directory - a relative symlink inside GIT_DIR"""
        tgt_abspath = os.path.abspath(os.path.join(self.git_dir, tgt_path))
        refs_path = os.path.join(self.git_dir, 'refs')
        # Create symlink target directory
        if not os.path.exists(tgt_abspath):
            os.makedirs(tgt_abspath)
        # Remove existing directory or symlink
        if not os.path.islink(refs_path):
            LOGGER.info('Removing old refs directory %s', refs_path)
            shutil.rmtree(refs_path)
        elif os.path.exists(refs_path):
            os.unlink(refs_path)

        LOGGER.debug("Symlinking %s -> %s", tgt_path, refs_path)
        os.symlink(tgt_path, refs_path)

    def force_fetch(self, refs_hack=False):
        """Fetch with specific arguments"""
        # Set HEAD temporarily as fetch with an invalid non-symbolic HEAD fails
        orig_head = self.get_ref('HEAD')
        self.set_ref('HEAD', 'refs/heads/non-existent-tmp-for-fetching')

        if refs_hack:
            # Create temporary refs directory for fetching
            # We need this because Gerrit is able to create refs/heads/* that
            # git refuses to fetch (to refs/heads/*), more specifically
            # branches pointing to tag objects
            alt_refs_root = 'refs.alt'
            alt_refs = os.path.join(alt_refs_root, 'fetch')
            self._symlink_refs(alt_refs_root)

            # Remove possible packed refs as they are not aligned with refs
            # after the hackish fetch, e.g. packed refs might contain refs that
            # do not exist in remote anymore
            packed_refs = os.path.join(self.git_dir, 'packed-refs')
            if os.path.exists(packed_refs):
                os.unlink(packed_refs)

            # Fetch all refs into alternate namespace
            refspec = '+refs/*:refs/fetch/*'
        else:
            # Remove possible refs symlink
            refs_path = os.path.join(self.git_dir, 'refs')
            if os.path.islink(refs_path):
                # Remove link target directory
                link_tgt = os.path.join(self.git_dir, os.readlink(refs_path))
                LOGGER.debug('Removing refs symlink and link target %s',
                             link_tgt)
                shutil.rmtree(link_tgt)
                # Remove link and create empty refs directory
                os.unlink(refs_path)
                os.mkdir(refs_path)

            # Update all refs
            refspec = '+refs/*:refs/*'

        try:
            self._git_command('fetch', ['-q', '-u', '-p', 'origin', refspec])
            try:
                # Fetch remote HEAD separately
                self._git_command('fetch', ['-q', '-u', 'origin', 'HEAD'])
            except GitRepositoryError:
                # If remote HEAD is invalid, invalidate FETCH_HEAD, too
                self.set_ref('FETCH_HEAD',
                             '0000000000000000000000000000000000000000')
        finally:
            self.set_ref('HEAD', orig_head)
            if refs_hack:
                self._symlink_refs(alt_refs)

    def force_checkout(self, commitish):
        """Checkout commitish"""
        self._git_command("checkout", ['--force', commitish])

    def force_clean(self):
        """Clean repository"""
        self._git_command('clean', ['-f', '-f', '-d', '-x'])

    @classmethod
    def clone(cls, path, url, bare=False, refs_hack=False):
        """Create a mirrored clone"""
        if bare:
            return super(MirrorGitRepository, cls).clone(path, url,
                                                         mirror=bare,
                                                         auto_name=False)
        else:
            LOGGER.debug('Initializing non-bare mirrored repo')
            repo = cls.create(path)
            repo.add_remote_repo('origin', url)
            # The refspec is a bit useless as we now use refspec in
            # force_fetch(). But, it's better to have it in config as weel
            # in case somebody somewhere would use the regular fetch() method.
            repo.set_config('remote.origin.fetch', '+refs/*:refs/*', True)
            repo.force_fetch(refs_hack)
            return repo

    def list_tags(self, obj):
        """List tags pointing at certain object"""
        return self._git_inout('tag', ['--points-at', obj])[0].splitlines()

    def get_tag_info(self, tag):
        """Look up data of a tag"""
        stdout, _stderr, ret = self._git_inout('cat-file', ['tag', tag])
        if ret:
            raise GitRepositoryError("'%s' is not an annotated tag" % tag)

        # Very old tags may not have tagger info, use None as default values
        info = {'tagger': {'name': None, 'email': None, 'date': None}}

        info['sha1'] = self.rev_parse(tag)
        tagger_re = re.compile(
                        r'tagger (?P<name>\S.+) <(?P<email>\S+)> (?P<date>.+)')
        num = 0
        lines = stdout.splitlines()
        for num, line in enumerate(lines):
            match = tagger_re.match(line)
            if match:
                info['tagger'] = match.groupdict()
            if line.startswith('tag '):
                info['tagname'] = line.split(' ', 1)[1]
            if not line:
                break

        # Parse subject, skip the blank line after tag/tagger info
        subject_lines = []
        for num, line in enumerate(lines[num+1:], num+1):
            if not line:
                break
            subject_lines.append(line)
        info['subject'] = ' '.join(subject_lines)

        # Get message body, skip the blank line after subject
        info['body'] = ''.join([line + '\n' for line in lines[num+1:]])

        return info


class CachedRepoError(Exception):
    """Repository cache errors"""
    pass


class CachedRepo(object):
    """Object representing a cached repository"""

    def __init__(self, base_dir, url, bare=False, refs_hack=False):
        self._basedir = base_dir
        self._repodir = None
        self._repo = None
        self._lock = None
        self._refs_hack = refs_hack

        # Safe repo dir name
        urlbase, reponame = self._split_url(url)
        subdir = hashlib.sha1(urlbase).hexdigest() # pylint: disable=E1101
        self._repodir = os.path.join(self._basedir, subdir, reponame)

        self._init_cache_dir()
        self._init_git_repo(url, bare)

    def _init_cache_dir(self):
        """Check and initialize repository cache base directory"""
        LOGGER.debug("Using cache basedir '%s'", self._basedir)
        _subdir = os.path.dirname(self._repodir)
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
            self._lock = open(repodir + '.lock', 'w')
        except IOError as err:
            raise CachedRepoError('Unable to open repo lock file: %s' % err)
        fcntl.flock(self._lock, fcntl.LOCK_EX)
        LOGGER.debug("Repository lock acquired")

    def _release_lock(self):
        """Release the repository lock"""
        if self._lock:
            fcntl.flock(self._lock, fcntl.LOCK_UN)
            self._lock.close()
            self._lock = None

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
        LOGGER.debug('Caching %s in %s', url, self._repodir)
        # Acquire repository lock
        self._acquire_lock(self._repodir)

        if os.path.exists(self._repodir):
            try:
                self._repo = MirrorGitRepository(self._repodir)
            except GitRepositoryError:
                pass
            if not self._repo or self._repo.bare != bare:
                LOGGER.info('Removing corrupted repo cache %s', self._repodir)
                try:
                    self._repo = None
                    shutil.rmtree(self._repodir)
                except OSError as err:
                    raise CachedRepoError('Failed to remove repo cache dir: %s'
                                         % str(err))
            else:
                LOGGER.info('Fetching from remote')
                try:
                    self._repo.force_fetch(refs_hack=self._refs_hack)
                except GitRepositoryError as err:
                    raise CachedRepoError('Failed to fetch from remote: %s' %
                                           err)
        if not self._repo:
            LOGGER.info('Cloning from %s', url)
            try:
                self._repo = MirrorGitRepository.clone(self._repodir, url,
                                    bare=bare, refs_hack=self._refs_hack)
            except GitRepositoryError as err:
                raise CachedRepoError('Failed to clone: %s' % err)

    def __del__(self):
        self._release_lock()

    def _check_instance(self):
        """Check that the cached repo is "open", raise an exception if not."""
        if not self._lock:
            raise CachedRepoError('Trying to operate on closed CachedRepo'
                                   'instance')

    @property
    def repo(self):
        """Get the GitRepository instance of the cached repo"""
        self._check_instance()
        return self._repo

    @property
    def repodir(self):
        """Get the file system path to the cached git repository"""
        self._check_instance()
        return self._repodir

    def close(self):
        """Close the cached git repository rendering it unusable.
        Releases locks to make the cache directory usable for another
        CachedRepository object. You should not operate on closed CachedRepo
        instances.
        """
        self._release_lock()
        self._repo = None

    def update_working_copy(self, commitish='HEAD', submodules=True):
        """Reset HEAD to the given commit-ish"""
        self._check_instance()
        if self.repo.bare:
            raise CachedRepoError('Cannot update working copy of a bare repo')

        # Update HEAD from FETCH_HEAD, so that HEAD points to remote HEAD.
        # We do it this way because FETCH_HEAD may point to an invalid object
        # and we don't want to update the working copy at this point.
        self.repo.set_ref('HEAD', self.repo.get_ref('FETCH_HEAD'))

        # Clean: just in case - this should never ever really be necessary
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

