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

import grp
import json
import mock
import os
import stat
from nose.tools import assert_raises, eq_, ok_ # pylint: disable=E0611

from obs_service_gbp.command import main as service
from obs_service_gbp_utils import GbpServiceError
from tests import UnitTestsBase


class FakeGbpError(Exception):
    """Exception for testing gbp crashes"""
    pass

def _mock_gbp():
    """Fake gbp main function for testing"""
    raise FakeGbpError()

def _mock_fork_call(*args, **kwargs):
    """Fake fork_call function for testing"""
    raise GbpServiceError("Mock error, args: %s, kwargs: %s" % (args, kwargs))


class TestService(UnitTestsBase):
    """Tests for the obsservice-git-buildpackage script"""
    s_rwx = stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC

    def _check_files(self, files, directory=''):
        """Check that the tmpdir content matches expectations"""
        found = set(os.listdir(os.path.join(self.tmpdir, directory)))
        expect = set(files)
        eq_(found, expect, "Expected: %s, Found: %s" % (expect, found))

    def test_invalid_options(self):
        """Test invalid options"""
        # Non-existing option
        with assert_raises(SystemExit):
            service(['--foo'])
        # Option without argument
        with assert_raises(SystemExit):
            ok_(service(['--url']))
        # Invalid repo
        ok_(service(['--url=foo/bar.git']) != 0)

    def test_basic_rpm_export(self):
        """Test that rpm export works"""
        eq_(service(['--url', self.orig_repo.path, '--revision=rpm']), 0)
        self._check_files(['test-package.spec', 'test-package_0.1.tar.gz'])

    def test_basic_deb_export(self):
        """Test that deb export works"""
        eq_(service(['--url', self.orig_repo.path, '--revision=deb']), 0)
        self._check_files(['test-package_0.1.dsc', 'test-package_0.1.tar.gz'])

    def test_empty_export(self):
        """Test case where nothing is exported"""
        eq_(service(['--url', self.orig_repo.path, '--revision=source']), 0)
        self._check_files([])
        eq_(service(['--url', self.orig_repo.path, '--rpm=no', '--deb=no']), 0)
        self._check_files([])

    def test_basic_dual_export(self):
        """Test that simultaneous rpm and deb export works"""
        eq_(service(['--url', self.orig_repo.path]), 0)
        self._check_files(['test-package.spec', 'test-package_0.1.dsc',
                           'test-package_0.1.tar.gz'])

    def test_gbp_rpm_failure(self):
        """Test git-buildpackage-rpm failure"""
        os.mkdir('foo')
        os.chmod('foo', 0)
        try:
            eq_(service(['--url', self.orig_repo.path, '--outdir=foo']), 1)
        finally:
            os.chmod('foo', self.s_rwx)
        eq_(service(['--url', self.orig_repo.path, '--rpm=yes',
                        '--revision=source']), 2)

    def test_gbp_deb_failure(self):
        """Test git-buildpackage (deb) failure"""
        eq_(service(['--url', self.orig_repo.path, '--deb=yes',
                        '--revision=source']), 3)

    @mock.patch('obs_service_gbp.command.gbp_deb', _mock_gbp)
    def test_deb_crash(self):
        """Test crash in git-buildpackage"""
        eq_(service(['--url', self.orig_repo.path, '--revision=deb']), 1)

    @mock.patch('obs_service_gbp.command.gbp_rpm', _mock_gbp)
    def test_rpm_crash(self):
        """Test crash in git-buildpackage-rpm"""
        eq_(service(['--url', self.orig_repo.path, '--revision=rpm']), 1)

    @mock.patch('obs_service_gbp.command.fork_call', _mock_fork_call)
    def test_service_error(self):
        """Test internal/configuration error"""
        eq_(service(['--url', self.orig_repo.path]), 1)

    def test_options_outdir(self):
        """Test the --outdir option"""
        outdir = os.path.join(self.tmpdir, 'outdir')
        args = ['--url', self.orig_repo.path, '--outdir=%s' % outdir]
        eq_(service(args), 0)
        self._check_files(['test-package.spec', 'test-package_0.1.dsc',
                           'test-package_0.1.tar.gz'], outdir)

    def test_options_revision(self):
        """Test the --revision option"""
        eq_(service(['--url', self.orig_repo.path, '--revision=master']), 0)
        self._check_files(['test-package.spec', 'test-package_0.1.dsc',
                           'test-package_0.1.tar.gz'])
        eq_(service(['--url', self.orig_repo.path, '--revision=foobar']), 1)

    def test_options_verbose(self):
        """Test the --verbose option"""
        eq_(service(['--url', self.orig_repo.path, '--verbose=yes']), 0)
        with assert_raises(SystemExit):
            service(['--url', self.orig_repo.path, '--verbose=foob'])

    def test_options_spec_vcs_tag(self):
        """Test the --spec-vcs-tag option"""
        eq_(service(['--url', self.orig_repo.path,
                        '--spec-vcs-tag=orig/%(tagname)s']), 0)

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
        ok_((service(['--url', self.orig_repo.path, '--config', 'my.conf']))
                == 0)
        ok_(not os.path.exists(default_cache), os.listdir('.'))
        ok_(os.path.exists('my-repo-cache'), os.listdir('.'))

    def test_options_config2(self):
        """Test that empty/non-existent config file is ok"""
        with open('my.conf', 'w') as conf:
            conf.write('[foo-section]\n')

        ok_((service(['--url', self.orig_repo.path, '--config', 'my.conf']))
                == 0)

    def test_options_git_meta(self):
        """Test the --git-meta option"""
        eq_(service(['--url', self.orig_repo.path, '--git-meta=_git_meta']), 0)

        # Check that the file was created and is json parseable
        with open('_git_meta') as meta_fp:
            json.load(meta_fp)

        # Test failure
        eq_(service(['--url', self.orig_repo.path,
                     '--git-meta=test-package.spec']), 1)

    def test_user_group_config(self):
        """Test setting the user and group under which gbp is run"""
        # Changing to current user/group should succeed
        os.environ['OBS_GIT_BUILDPACKAGE_GBP_USER'] = str(os.getuid())
        os.environ['OBS_GIT_BUILDPACKAGE_GBP_GROUP'] = \
                grp.getgrgid(os.getgid()).gr_name
        eq_(service(['--url', self.orig_repo.path, '--revision=rpm']), 0)

        # Changing to non-existent user should fail
        os.environ['OBS_GIT_BUILDPACKAGE_GBP_USER'] = '_non_existent_user'
        del os.environ['OBS_GIT_BUILDPACKAGE_GBP_GROUP']
        eq_(service(['--url', self.orig_repo.path, '--revision=rpm']), 1)

        # Return env
        del os.environ['OBS_GIT_BUILDPACKAGE_GBP_USER']

