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
"""Tests for the git-buildpackage OBS source service"""

import os
import shutil
import stat
import tempfile
from nose.tools import assert_raises # pylint: disable=E0611

from gbp.git.repository import GitRepository, GitRepositoryError

from obs_service_gbp import MirrorGitRepository, CachedRepo, CachedRepoError
from obs_service_gbp.command import main as service


TEST_DATA_DIR = os.path.abspath(os.path.join('tests', 'data'))

class UnitTestsBase(object):
    """Base class for unit tests"""

    @classmethod
    def create_orig_repo(cls, name):
        """Create test repo"""
        orig_repo = GitRepository.create(os.path.join(cls.workdir, name))
        orig_repo.commit_dir(TEST_DATA_DIR, 'Initial version', 'master',
                             create_missing_branch=True)
        orig_repo.force_head('master', hard=True)
        # Make new commit
        cls.update_repository_file(orig_repo, 'foo.txt', 'new data\n')
        return orig_repo

    @classmethod
    def setup_class(cls):
        """Test class setup"""
        # Don't let git see that we're (possibly) under a git directory
        os.environ['GIT_CEILING_DIRECTORIES'] = os.getcwd()
        # Create temporary workdir
        cls.workdir = os.path.abspath(tempfile.mkdtemp(prefix='%s_' %
                                                       cls.__name__, dir='.'))
        cls.orig_dir = os.getcwd()
        os.chdir(cls.workdir)
        # Create an orig repo for testing
        cls._template_repo = cls.create_orig_repo('orig')

    @classmethod
    def teardown_class(cls):
        """Test class teardown"""
        os.chdir(cls.orig_dir)
        if not 'DEBUG_NOSETESTS' in os.environ:
            shutil.rmtree(cls.workdir)

    @staticmethod
    def update_repository_file(repo, filename, data):
        """Append data to file in git repository and commit changes"""
        with open(os.path.join(repo.path, filename), 'a') as filep:
            filep.write(data)
        repo.add_files(filename)
        repo.commit_files(filename, "Update %s" % filename)

    def __init__(self):
        self.orig_repo = None
        self.tmpdir = None
        self.cachedir = None

    def setup(self):
        """Test class setup"""
        # Change to a temporary directory
        self.tmpdir = os.path.abspath(tempfile.mkdtemp(prefix='test_',
                                                       dir=self.workdir))
        os.chdir(self.tmpdir)
        # Use cache in our tmpdir
        suffix = os.path.basename(self.tmpdir).replace('test', '')
        self.cachedir = os.path.join(self.workdir, 'cache' + suffix)
        os.environ['OBS_GIT_BUILDPACKAGE_REPO_CACHE_DIR'] = self.cachedir
        # Create temporary "orig" repository
        repo_dir = os.path.join(self.workdir, 'orig' + suffix)
        shutil.copytree(self._template_repo.path, repo_dir)
        self.orig_repo = GitRepository(repo_dir)

    def teardown(self):
        """Test case teardown"""
        # Restore original working dir
        os.chdir(self.workdir)
        if not 'DEBUG_NOSETESTS' in os.environ:
            shutil.rmtree(self.orig_repo.path)
            if os.path.exists(self.cachedir):
                shutil.rmtree(self.cachedir)
            shutil.rmtree(self.tmpdir)


class TestBasicFunctionality(UnitTestsBase):
    """Base class for unit tests"""

    def test_invalid_options(self):
        """Test invalid options"""
        # Non-existing option
        with assert_raises(SystemExit):
            service(['--foo'])
        # Option without argument
        with assert_raises(SystemExit):
            assert service(['--url'])
        # Invalid repo
        assert service(['--url=foo/bar.git']) != 0

    def test_basic_export(self):
        """Test that export works"""
        assert service(['--url', self.orig_repo.path]) == 0

    def test_gbp_failure(self):
        """Test git-buildpackage failure"""
        assert service(['--url', self.orig_repo.path, '--outdir=foo/bar']) == 2

    def test_options_outdir(self):
        """Test the --outdir option"""
        outdir = os.path.join(self.tmpdir, 'outdir')
        args = ['--url', self.orig_repo.path, '--outdir=%s' % outdir]
        assert service(args) == 0
        assert os.path.isdir(outdir)

    def test_options_revision(self):
        """Test the --revision option"""
        assert service(['--url', self.orig_repo.path, '--revision=master']) == 0
        assert service(['--url', self.orig_repo.path, '--revision=foobar']) == 1

    def test_options_verbose(self):
        """Test the --verbose option"""
        assert service(['--url', self.orig_repo.path, '--verbose=yes']) == 0
        with assert_raises(SystemExit):
            service(['--url', self.orig_repo.path, '--verbose=foob'])

    def test_options_spec_vcs_tag(self):
        """Test the --spec-vcs-tag option"""
        assert service(['--url', self.orig_repo.path,
                        '--spec-vcs-tag=orig/%(tagname)s']) == 0

    def test_options_config(self):
        """Test the --config option"""
        # Create config file
        with open('my.conf', 'w') as conf:
            conf.write('[general]\n')
            conf.write('repo-cache-dir = my-repo-cache\n')

        # Mangle environment
        default_cache = os.environ['OBS_GIT_BUILDPACKAGE_REPO_CACHE_DIR']
        del os.environ['OBS_GIT_BUILDPACKAGE_REPO_CACHE_DIR']

        # Check that the repo cache we configured is actually used
        assert (service(['--url', self.orig_repo.path, '--config', 'my.conf'])
                == 0)
        assert not os.path.exists(default_cache), os.listdir('.')
        assert os.path.exists('my-repo-cache'), os.listdir('.')


class TestObsRepoGitRepository(UnitTestsBase):
    """Test the special GitRepository class"""

    def test_set_config(self):
        """Test the set config functionality"""
        repo = MirrorGitRepository.create('testrepo')
        with assert_raises(GitRepositoryError):
            repo.set_config('foo', 'bar')
        repo.set_config('foo.bar', 'baz')
        repo.set_config('foo.bar', 'bax', replace=True)
        assert repo.get_config('foo.bar') == 'bax'


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
        # Check base cachedir creation access error
        os.chmod(self.workdir, 0)
        with assert_raises(CachedRepoError):
            repo = self.MockCachedRepo(self.orig_repo.path)
        os.chmod(self.workdir, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
        repo = self.MockCachedRepo(self.orig_repo.path)
        del repo

        # Check cache base dir access error
        os.chmod(self.cachedir, 0)
        with assert_raises(CachedRepoError):
            repo = self.MockCachedRepo(self.orig_repo.path)
        os.chmod(self.cachedir, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
        repo = self.MockCachedRepo(self.orig_repo.path)
        del repo

        # Check repodir delete eror
        os.chmod(self.cachedir, stat.S_IREAD | stat.S_IEXEC)
        with assert_raises(CachedRepoError):
            # Change repo type -> tries to delete
            repo = self.MockCachedRepo(self.orig_repo.path, bare=True)
        os.chmod(self.cachedir, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)

