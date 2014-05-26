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
"""Tests for the GBP OBS service helper functionality"""

import grp
import json
import pwd
import os
from functools import partial
from nose.tools import assert_raises, eq_, ok_  # pylint: disable=E0611
from multiprocessing import Queue

from gbp_repocache import MirrorGitRepository
from obs_service_gbp_utils import fork_call, _demoted_child_call, _RET_FORK_OK
from obs_service_gbp_utils import write_treeish_meta
from obs_service_gbp_utils import GbpServiceError, GbpChildBTError

from tests import UnitTestsBase


class _DummyException(Exception):
    """Dummy exception for testing"""
    pass

class TestForkCall(object):
    """Test the functionality for calling functions in a child thread"""

    def __init__(self):
        self._uid = os.getuid()
        self._gid = os.getgid()
        self._name = pwd.getpwuid(self._uid).pw_name
        self._group = grp.getgrgid(self._gid).gr_name

    @staticmethod
    def _no_fork_call(uid, gid, func):
        """For testing demoted call without actually forking"""
        def _no_fork_call_runner(uid, gid, func, *args, **kwargs):
            """Actual workhorse"""
            data_q = Queue()
            try:
                _demoted_child_call(uid, gid, data_q,
                                    partial(func, *args, **kwargs))
            except SystemExit as err:
                ret_code = err.code
            ret_data = data_q.get()
            if ret_code == _RET_FORK_OK:
                return ret_data
            else:
                raise ret_data
        return partial(_no_fork_call_runner, uid, gid, func)

    @staticmethod
    def _dummy_ok():
        """Helper method returning 'ok'"""
        return 'ok'

    @staticmethod
    def _dummy_raise():
        """Helper method raising an exception"""
        raise _DummyException('Dummy error')

    @staticmethod
    def _dummy_args(arg1, arg2, arg3):
        """Helper method returning all its args"""
        return (arg1, arg2, arg3)

    def test_success(self):
        """Basic test for successful call"""
        eq_(fork_call(None, None, self._dummy_ok)(), 'ok')

        eq_(fork_call(None, None, self._dummy_args)(1, '2', arg3='foo'),
            (1, '2', 'foo'))

        ok_(os.getpid() != fork_call(None, None, os.getpid)())

    def test_fail(self):
        """Tests for function call failures"""
        with assert_raises(GbpChildBTError) as exc:
            fork_call(None, None, self._dummy_raise)()
        eq_(exc.exception.typ, _DummyException)

        with assert_raises(GbpChildBTError) as exc:
            fork_call(None, None, self._dummy_ok)('unexptected_arg')
        eq_(exc.exception.typ, TypeError)

    def test_demoted_call_no(self):
        """Test running with different UID/GID"""
        eq_(fork_call(self._name, self._group, self._dummy_ok)(), 'ok')
        eq_(fork_call(self._uid, None, self._dummy_ok)(), 'ok')
        eq_(fork_call(None, self._gid, self._dummy_ok)(), 'ok')

        eq_(self._no_fork_call(self._uid, self._gid, self._dummy_ok)(), 'ok')

    def test_demoted_call_fail(self):
        """Test running with invalid UID/GID"""
        with assert_raises(GbpServiceError):
            fork_call('_non_existent_user', None, self._dummy_ok)()
        with assert_raises(GbpServiceError):
            fork_call(None, '_non_existen_group', self._dummy_ok)()

        with assert_raises(GbpServiceError):
            self._no_fork_call(99999, None, self._dummy_ok)()
        with assert_raises(GbpServiceError):
            self._no_fork_call(None, 99999, self._dummy_ok)()
        with assert_raises(GbpChildBTError) as exc:
            self._no_fork_call(self._uid, self._gid, self._dummy_raise)()
        eq_(exc.exception.typ, _DummyException)

class TestGitMeta(UnitTestsBase):
    """Test writing treeish meta into a file"""

    @classmethod
    def setup_class(cls):
        """Set-up tests"""
        # Fake committer and author
        author = {'name': 'John Doe',
                  'email': 'j@example.com',
                  'date': '1390000000 +0200'}
        os.environ['GIT_AUTHOR_NAME'] = author['name']
        os.environ['GIT_AUTHOR_EMAIL'] = author['email']
        os.environ['GIT_AUTHOR_DATE'] = author['date']
        committer = {'name': 'Jane Doe',
                     'email': 'j2@example.com',
                     'date': '1391000000 +0200'}
        os.environ['GIT_COMMITTER_NAME'] = committer['name']
        os.environ['GIT_COMMITTER_EMAIL'] = committer['email']
        os.environ['GIT_COMMITTER_DATE'] = committer['date']

        # Initialize repo
        super(TestGitMeta, cls).setup_class()
        cls.repo = MirrorGitRepository.clone('myrepo', cls._template_repo.path)

        # Create test tags
        cls.repo.create_tag('tag', msg='Subject\n\nBody')
        cls.repo.create_tag('tag2', msg='Subject 2')
        cls.repo.create_tag('light_tag')

        # Reference meta
        cls.tag_meta = {'tagname': 'tag',
                        'sha1': cls.repo.rev_parse('tag'),
                        'tagger': committer,
                        'subject': 'Subject',
                        'body': 'Body\n'}

        commit = cls.repo.rev_parse('tag^0')
        cls.commit_meta = {'sha1': commit,
                           'author': author,
                           'committer': committer,
                           'subject': 'Add debian packaging files',
                           'body': '',
                           'files':
                                {'A': ['debian/changelog', 'debian/control']}}
        cls.tags_meta = [cls.tag_meta,
                         {'tagname': 'tag2',
                          'sha1': cls.repo.rev_parse('tag2'),
                          'tagger': committer,
                          'subject': 'Subject 2',
                          'body': ''}]

    @classmethod
    def teardown_class(cls):
        """Clean-up"""
        del os.environ['GIT_AUTHOR_NAME']
        del os.environ['GIT_AUTHOR_EMAIL']
        del os.environ['GIT_AUTHOR_DATE']
        del os.environ['GIT_COMMITTER_NAME']
        del os.environ['GIT_COMMITTER_EMAIL']
        del os.environ['GIT_COMMITTER_DATE']
        super(TestGitMeta, cls).teardown_class()

    def test_tag(self):
        """Test meta from tag object"""
        write_treeish_meta(self.repo, 'tag', '.', 'meta1.txt')
        # Read back and check
        with open('meta1.txt') as meta_fp:
            meta = json.load(meta_fp)
        eq_(meta['treeish'], 'tag')
        eq_(meta['tag'], self.tag_meta)
        eq_(meta['tags'], self.tags_meta)
        eq_(meta['commit'], self.commit_meta)

    def test_commit(self):
        """Test meta from commit object"""
        write_treeish_meta(self.repo, 'HEAD', '.', 'meta2.txt')
        # Read back and check
        with open('meta2.txt') as meta_fp:
            meta = json.load(meta_fp)
        eq_(meta['treeish'], 'HEAD')
        ok_('tag' not in meta)
        eq_(meta['tags'], self.tags_meta)
        eq_(meta['commit'], self.commit_meta)

    def test_tree(self):
        """Test meta from tree object"""
        tree = self.repo.write_tree()
        write_treeish_meta(self.repo, tree, '.', 'meta3.txt')
        # Read back and check
        with open('meta3.txt') as meta_fp:
            meta = json.load(meta_fp)
        eq_(meta['treeish'], tree)
        ok_('tag' not in meta)
        ok_('tags' not in meta)
        ok_('commit' not in meta)

    def test_failures(self):
        """Failure cases"""
        write_treeish_meta(self.repo, 'HEAD', '.', 'meta4.txt')

        # Overwriting existing file should fail and not change file
        orig_stat = os.stat('meta4.txt')
        with assert_raises(GbpServiceError):
            write_treeish_meta(self.repo, 'tag', '.', 'meta4.txt')
        eq_(os.stat('meta4.txt'), orig_stat)

        # Non-existent dir -> failure
        with assert_raises(GbpServiceError):
            write_treeish_meta(self.repo, 'tag', 'non-existent-dir', 'meta.txt')

