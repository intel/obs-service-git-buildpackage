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
"""Unit tests, helper functionality"""

import os
import shutil
import tempfile

from gbp.git.repository import GitRepository, GitRepositoryError


TEST_DATA_DIR = os.path.abspath(os.path.join('tests', 'data'))

class UnitTestsBase(object):
    """Base class for unit tests"""

    @classmethod
    def create_orig_repo(cls, name):
        """Create test repo"""
        repo_path = os.path.join(cls.workdir, name)
        repo = GitRepository.create(repo_path)

        # First, commit sources only and create branch 'sources'
        sources = [src for src in os.listdir(TEST_DATA_DIR)
                       if not src in ['packaging', 'debian']]
        repo.add_files(sources, work_tree=TEST_DATA_DIR)
        repo.commit_staged('Initial version')
        # Make one new commit
        cls.update_repository_file(repo, 'foo.txt', 'new data\n')
        repo.create_branch('source')

        # Create branch with rpm packaging only
        repo.add_files('packaging', work_tree=TEST_DATA_DIR)
        repo.commit_staged('Add rpm packaging files')
        repo.create_branch('rpm')

        # Master has both debian and rpm packaging
        repo.add_files('debian', work_tree=TEST_DATA_DIR)
        repo.commit_staged('Add debian packaging files')

        # Create branch with deb packaging only
        repo.create_branch('deb', 'source')
        repo.set_branch('deb')
        repo.add_files('debian', work_tree=TEST_DATA_DIR)
        repo.commit_staged('Add deb packaging files')

        repo.set_branch('master')
        repo.force_head('master', hard=True)
        return repo

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
        """Test case setup"""
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

