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
from nose.tools import assert_raises, eq_, ok_  # pylint: disable=E0611

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
        eq_(repo.get_config('foo.bar'), 'bax')

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

    def test_force_fetch(self):
        """Test fetching"""
        repo = MirrorGitRepository.clone('testrepo', self.orig_repo.path)

        # Make remote HEAD invalid
        orig_branch = self.orig_repo.get_branch()
        with open(os.path.join(self.orig_repo.git_dir, 'HEAD'), 'w') as head:
            head.write('ref: refs/heads/non-existent-branch\n')

        # Local HEAD should be invalid after fetch
        repo.force_fetch()
        eq_(repo.get_ref('FETCH_HEAD'),
            '0000000000000000000000000000000000000000')

        # Fetch should succeed even if local head is invalid
        repo.set_ref('HEAD', '1234567890123456789012345678901234567890')
        repo.force_fetch()
        eq_(repo.get_ref('HEAD'), '1234567890123456789012345678901234567890')

        # Restore orig repo HEAD
        self.orig_repo.set_branch(orig_branch)

    def test_get_tag_info(self):
        """Test get_tag_info() method"""
        repo = MirrorGitRepository.clone('testrepo', self.orig_repo.path)
        tagger = {'name': 'John Doe',
                  'email': 'j@example.com',
                  'date': '1390000000 +0200'}
        os.environ['GIT_COMMITTER_NAME'] = tagger['name']
        os.environ['GIT_COMMITTER_EMAIL'] = tagger['email']
        os.environ['GIT_COMMITTER_DATE'] = tagger['date']

        # Non-tag
        with assert_raises(GitRepositoryError):
            info = repo.get_tag_info('HEAD')

        # Completely empty message
        repo.create_tag('tag1', msg=' ')
        info = repo.get_tag_info('tag1')
        eq_(info['tagger'], tagger)
        eq_(info['subject'], '')
        eq_(info['body'], '')
        eq_(info['sha1'], repo.rev_parse('tag1'))

        # Empty message body
        repo.create_tag('tag2', msg='Tag subject')
        info = repo.get_tag_info('tag2')
        eq_(info['tagger'], tagger)
        eq_(info['subject'], 'Tag subject')
        eq_(info['body'], '')

        # Multi-line subject with body
        repo.create_tag('tag3', msg='Tag\nsubject\n\nTag\nbody')
        info = repo.get_tag_info('tag3')
        eq_(info['tagger'], tagger)
        eq_(info['subject'], 'Tag subject')
        eq_(info['body'], 'Tag\nbody\n')

        # Clean environmemt
        del os.environ['GIT_COMMITTER_NAME']
        del os.environ['GIT_COMMITTER_EMAIL']
        del os.environ['GIT_COMMITTER_DATE']


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
        repo.close()
        shutil.move(self.orig_repo.path, self.orig_repo.path + '.tmp')
        with assert_raises(CachedRepoError):
            repo = self.MockCachedRepo(self.orig_repo.path)
        shutil.move(self.orig_repo.path + '.tmp', self.orig_repo.path)

    def test_clone_and_fetch(self):
        """Basic test for cloning and fetching"""
        # Clone
        repo = self.MockCachedRepo(self.orig_repo.path)
        ok_(repo)
        ok_(repo.repo.bare is not True)
        sha = repo.repo.rev_parse('master')
        path = repo.repo.path
        repo.close()
        # Make new commit in "upstream"
        self.update_repository_file(self.orig_repo, 'foo.txt', 'more data\n')
        # Fetch
        repo = self.MockCachedRepo(self.orig_repo.path)
        ok_(repo)
        eq_(path, repo.repo.path)
        ok_(sha != repo.repo.rev_parse('master'))

    def test_update_working_copy(self):
        """Test update functionality"""
        repo = self.MockCachedRepo(self.orig_repo.path)
        # Check that the refs are mapped correctly
        sha = repo.update_working_copy('HEAD~1')
        eq_(sha, self.orig_repo.rev_parse('HEAD~1'))
        sha = self.orig_repo.rev_parse('HEAD')
        eq_(sha, repo.update_working_copy('HEAD'))
        eq_(sha, repo.update_working_copy(sha))

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
        repo.close()

        # Change upstream, after this index cached repo will be out-of-sync
        # from orig HEAD
        self.orig_repo.set_branch('HEAD~1')
        repo = self.MockCachedRepo(self.orig_repo.path)
        eq_(repo.update_working_copy(shas[0]), shas[0])

    def test_close(self):
        """Test closing of cached repo"""
        repo = self.MockCachedRepo(self.orig_repo.path)
        ok_(repo)
        # Operating on a closed repository should fail
        repo.close()
        with assert_raises(CachedRepoError):
            repo.update_working_copy('HEAD')
        with assert_raises(CachedRepoError):
            _repo_obj = repo.repo
        with assert_raises(CachedRepoError):
            _repo_dir = repo.repodir

        # Multiple closes should be ok
        repo.close()

    def test_update_bare(self):
        """Test update for bare repository"""
        repo = self.MockCachedRepo(self.orig_repo.path, bare=True)
        with assert_raises(CachedRepoError):
            repo.update_working_copy('HEAD')

    def test_invalid_remote_head(self):
        """Test clone/update from remote whose HEAD is invalid"""
        repo = self.MockCachedRepo(self.orig_repo.path)
        repo.close()

        # Make remote HEAD point to a non-existent branch
        orig_branch = self.orig_repo.get_branch()
        with open(os.path.join(self.orig_repo.git_dir, 'HEAD'), 'w') as head:
            head.write('ref: refs/heads/non-existent-branch\n')

        repo = self.MockCachedRepo(self.orig_repo.path)
        # Local HEAD should be invalid, now
        with assert_raises(CachedRepoError):
            repo.update_working_copy('HEAD')
        repo.close()

        # Init/fetch with invalid local HEAD should succeed
        repo = self.MockCachedRepo(self.orig_repo.path)

        # Test valid refs, too
        ok_(repo.update_working_copy('master'))

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
        repo.close()
        # Update and check status
        repo = self.MockCachedRepo(self.orig_repo.path)
        ok_(repo.repo.rev_parse('HEAD'))

    def test_changing_repotype(self):
        """Test changing repo type from bare -> normal"""
        # Clone
        repo = self.MockCachedRepo(self.orig_repo.path, bare=True)
        eq_(repo.repo.bare, True)
        repo.close()
        repo = self.MockCachedRepo(self.orig_repo.path, bare=False)
        eq_(repo.repo.bare, False)

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
        repo.close()

        # Check cache base dir access error
        os.chmod(self.cachedir, 0)
        with assert_raises(CachedRepoError):
            try:
                repo = self.MockCachedRepo(self.orig_repo.path)
            finally:
                os.chmod(self.cachedir, s_rwx)
        repo = self.MockCachedRepo(self.orig_repo.path)
        subdir = os.path.dirname(repo.repodir)
        repo.close()

        # Check cache subdir access error
        os.chmod(subdir, 0)
        with assert_raises(CachedRepoError):
            try:
                repo = self.MockCachedRepo(self.orig_repo.path)
            finally:
                os.chmod(subdir, s_rwx)
        repo = self.MockCachedRepo(self.orig_repo.path)
        repo.close()

        # Check repodir delete error
        os.chmod(subdir, stat.S_IREAD | stat.S_IEXEC)
        with assert_raises(CachedRepoError):
            try:
                # Change repo type -> tries to delete
                repo = self.MockCachedRepo(self.orig_repo.path, bare=True)
            finally:
                os.chmod(subdir, s_rwx)

