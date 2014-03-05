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
"""Tests for the Git repository cache"""

import os
import shutil
import stat
from nose.tools import eq_, assert_raises # pylint: disable=E0611

from gbp.git.repository import GitRepositoryError

from gbp_repocache import MirrorGitRepository, CachedRepo, CachedRepoError
from tests import UnitTestsBase


class TestMirrorGitRepository(UnitTestsBase):
    """Test the special mirrored GitRepository class"""

    def test_set_config(self):
        """Test the set config functionality"""
        repo = MirrorGitRepository.create('testrepo')
        with assert_raises(GitRepositoryError):
            repo.set_config('foo', 'bar')
        repo.set_config('foo.bar', 'baz')
        repo.set_config('foo.bar', 'bax', replace=True)
        assert repo.get_config('foo.bar') == 'bax'

    def test_get_set_ref(self):
        """Test setting and getting ref"""
        repo = MirrorGitRepository.clone('testrepo', self.orig_repo.path)
        remote_head = 'refs/heads/' + self.orig_repo.get_branch()

        eq_(repo.get_ref('HEAD'), remote_head)
        with assert_raises(GitRepositoryError):
            repo.get_ref('MY_REF')

        repo.set_ref('MY_REF', repo.get_ref('HEAD'))
        eq_(repo.get_ref('MY_REF'), remote_head)

        sha1 = repo.rev_parse('HEAD')
        repo.set_ref('MY_REF', sha1)
        eq_(repo.get_ref('MY_REF'), sha1)


class TestCachedRepo(UnitTestsBase):
    """Test CachedRepo class"""

    def MockCachedRepo(self, url, **kwargs):
        """Automatically use suitable cache dir"""
        return CachedRepo(self.cachedir, url, **kwargs)

    def test_invalid_url(self):
        """Test invalid url"""
        with assert_raises(CachedRepoError):
            self.MockCachedRepo('foo/bar.git')
        with assert_raises(CachedRepoError):
            self.MockCachedRepo('foo/baz.git', bare=True)

        # Try updating from non-existing repo
        repo = self.MockCachedRepo(self.orig_repo.path)
        del repo
        shutil.move(self.orig_repo.path, self.orig_repo.path + '.tmp')
        with assert_raises(CachedRepoError):
            repo = self.MockCachedRepo(self.orig_repo.path)
        shutil.move(self.orig_repo.path + '.tmp', self.orig_repo.path)

    def test_clone_and_fetch(self):
        """Basic test for cloning and fetching"""
        # Clone
        repo = self.MockCachedRepo(self.orig_repo.path)
        assert repo
        assert repo.repo.bare is not True
        sha = repo.repo.rev_parse('master')
        path = repo.repo.path
        del repo
        # Make new commit in "upstream"
        self.update_repository_file(self.orig_repo, 'foo.txt', 'more data\n')
        # Fetch
        repo = self.MockCachedRepo(self.orig_repo.path)
        assert repo
        assert path == repo.repo.path
        assert sha != repo.repo.rev_parse('master')

    def test_update_working_copy(self):
        """Test update functionality"""
        repo = self.MockCachedRepo(self.orig_repo.path)
        # Check that the refs are mapped correctly
        sha = repo.update_working_copy('HEAD~1')
        assert sha == self.orig_repo.rev_parse('HEAD~1')
        sha = self.orig_repo.rev_parse('HEAD')
        assert sha == repo.update_working_copy('HEAD')
        assert sha == repo.update_working_copy(sha)

        with assert_raises(CachedRepoError):
            sha = repo.update_working_copy('foo/bar')

    def test_update_dirty_index(self):
        """Test situation where index is out-of-sync with HEAD"""

        self.update_repository_file(self.orig_repo, 'foo.txt', 'more data\n')
        shas = [self.orig_repo.rev_parse('HEAD~2'),
                self.orig_repo.rev_parse('HEAD~1'),
                self.orig_repo.rev_parse('HEAD')]
        repo = self.MockCachedRepo(self.orig_repo.path)
        repo.update_working_copy(shas[-1])
        del repo

        # Change upstream, after this index cached repo will be out-of-sync
        # from orig HEAD
        self.orig_repo.set_branch('HEAD~1')
        repo = self.MockCachedRepo(self.orig_repo.path)
        assert repo.update_working_copy(shas[0]) == shas[0]

    def test_update_bare(self):
        """Test update for bare repository"""
        repo = self.MockCachedRepo(self.orig_repo.path, bare=True)
        with assert_raises(CachedRepoError):
            repo.update_working_copy('HEAD')

    def test_invalid_remote_head(self):
        """Test clone/update from remote whose HEAD is invalid"""
        repo = self.MockCachedRepo(self.orig_repo.path)
        del repo

        # Make remote HEAD point to a non-existent branch
        orig_branch = self.orig_repo.get_branch()
        with open(os.path.join(self.orig_repo.git_dir, 'HEAD'), 'w') as head:
            head.write('ref: refs/heads/non-existent-branch\n')

        repo = self.MockCachedRepo(self.orig_repo.path)
        # Local HEAD should be invalid, now
        with assert_raises(CachedRepoError):
            repo.update_working_copy('HEAD')
        # Test valid refs, too
        assert repo.update_working_copy('master')

        # Reset orig repo to original state
        self.orig_repo.set_branch(orig_branch)

    def test_corrupted_cache(self):
        """Test recovering from corrupted cache"""
        # Clone
        repo = self.MockCachedRepo(self.orig_repo.path)
        # Corrupt repo
        shutil.rmtree(os.path.join(repo.repo.path, '.git/refs'))
        with assert_raises(GitRepositoryError):
            repo.repo.rev_parse('HEAD')
        del repo
        # Update and check status
        repo = self.MockCachedRepo(self.orig_repo.path)
        assert repo.repo.rev_parse('HEAD')

    def test_changing_repotype(self):
        """Test changing repo type from bare -> normal"""
        # Clone
        repo = self.MockCachedRepo(self.orig_repo.path, bare=True)
        assert repo.repo.bare == True
        del repo
        repo = self.MockCachedRepo(self.orig_repo.path, bare=False)
        assert repo.repo.bare == False

    def test_cache_access_error(self):
        """Test cached directory with invalid permissions"""
        s_rwx = stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC

        # Check base cachedir creation access error
        os.chmod(self.workdir, 0)
        with assert_raises(CachedRepoError):
            try:
                repo = self.MockCachedRepo(self.orig_repo.path)
            finally:
                os.chmod(self.workdir, s_rwx)
        repo = self.MockCachedRepo(self.orig_repo.path)
        del repo

        # Check cache base dir access error
        os.chmod(self.cachedir, 0)
        with assert_raises(CachedRepoError):
            try:
                repo = self.MockCachedRepo(self.orig_repo.path)
            finally:
                os.chmod(self.cachedir, s_rwx)
        repo = self.MockCachedRepo(self.orig_repo.path)
        subdir = os.path.dirname(repo.repodir)
        del repo

        # Check cache subdir access error
        os.chmod(subdir, 0)
        with assert_raises(CachedRepoError):
            try:
                repo = self.MockCachedRepo(self.orig_repo.path)
            finally:
                os.chmod(subdir, s_rwx)
        repo = self.MockCachedRepo(self.orig_repo.path)
        del repo

        # Check repodir delete error
        os.chmod(subdir, stat.S_IREAD | stat.S_IEXEC)
        with assert_raises(CachedRepoError):
            try:
                # Change repo type -> tries to delete
                repo = self.MockCachedRepo(self.orig_repo.path, bare=True)
            finally:
                os.chmod(subdir, s_rwx)

