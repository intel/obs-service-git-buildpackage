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
from nose.tools import assert_raises

from gbp.git.repository import GitRepository, GitRepositoryError

from obs_service_gbp import CachedRepo, CachedRepoError
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
        return orig_repo

    @classmethod
    def setup_class(cls):
        """Test class setup"""
        # Don't let git see that we're (possibly) under a git directory
        os.environ['GIT_CEILING_DIRECTORIES'] = os.getcwd()
        # Create temporary workdir
        cls.workdir = os.path.abspath(tempfile.mkdtemp(prefix='%s_' %
                                     __name__, dir='.'))
        cls.orig_dir = os.getcwd()
        os.chdir(cls.workdir)
        # Use cache in our workdir
        cls.cachedir = os.path.join(cls.workdir, 'cache')
        os.environ['CACHEDIR'] = cls.cachedir
        # Create an orig repo for testing
        cls.orig_repo = cls.create_orig_repo('orig').path

    @classmethod
    def teardown_class(cls):
        """Test class teardown"""
        os.chdir(cls.orig_dir)
        if not 'DEBUG_NOSETESTS' in os.environ:
            shutil.rmtree(cls.workdir)


class TestBasicFunctionality(UnitTestsBase):
    """Base class for unit tests"""

    def setup(self):
        """Test case setup"""
        # Change to a temporary directory
        self.tmpdir = tempfile.mkdtemp(dir=self.workdir)
        os.chdir(self.tmpdir)

    def teardown(self):
        """Test case teardown"""
        # Restore original working dir
        os.chdir(self.workdir)
        if not 'DEBUG_NOSETESTS' in os.environ:
            shutil.rmtree(self.tmpdir)

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
        assert service(['--url', self.orig_repo]) == 0

    def test_options_outdir(self):
        """Test the --outdir option"""
        outdir = os.path.join(self.tmpdir, 'outdir')
        assert service(['--url', self.orig_repo, '--outdir=%s' % outdir]) == 0
        assert os.path.isdir(outdir)

    def test_options_revision(self):
        """Test the --revision option"""
        assert service(['--url', self.orig_repo, '--revision=master']) == 0
        assert service(['--url', self.orig_repo, '--revision=foobar']) == 1

    def test_options_verbose(self):
        """Test the --verbose option"""
        assert service(['--url', self.orig_repo, '--verbose=yes']) == 0
        with assert_raises(SystemExit):
            service(['--url', self.orig_repo, '--verbose=foob'])

    def test_options_spec_vcs_tag(self):
        """Test the --spec-vcs-tag option"""
        assert service(['--url', self.orig_repo,
                        '--spec-vcs-tag=orig/%(tagname)s']) == 0


class TestCachedRepo(UnitTestsBase):
    """Test CachedRepo class"""

    def test_invalid_url(self):
        """Test invalid url"""
        with assert_raises(CachedRepoError):
            CachedRepo('foo/bar.git')

    def test_clone_and_fetch(self):
        """Basic test for cloning and fetching"""
        # Clone
        repo = CachedRepo(self.orig_repo)
        assert repo
        assert repo.repo.bare
        repo._release_lock()
        # Fetch
        repo2 = CachedRepo(self.orig_repo)
        assert repo2
        assert repo.repo.path == repo2.repo.path

    def test_corrupted_cache(self):
        """Test recovering from corrupted cache"""
        # Clone
        repo = CachedRepo(self.orig_repo)
        # Corrupt repo
        shutil.rmtree(os.path.join(repo.repo.path, 'refs'))
        with assert_raises(GitRepositoryError):
            repo.repo.rev_parse('HEAD')
        repo._release_lock()
        # Update and check status
        repo = CachedRepo(self.orig_repo)
        assert repo.repo.rev_parse('HEAD')

    def test_cache_access_error(self):
        """Test cached directory with invalid permissions"""
        # Check base cachedir creation access error
        os.chmod(self.workdir, 0)
        with assert_raises(CachedRepoError):
            repo = CachedRepo(self.orig_repo)
        os.chmod(self.workdir, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
        repo = CachedRepo(self.orig_repo)
        repo._release_lock()

        # Check cache access error
        os.chmod(self.cachedir, 0)
        with assert_raises(CachedRepoError):
            repo = CachedRepo(self.orig_repo)
        os.chmod(self.cachedir, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
        repo = CachedRepo(self.orig_repo)

