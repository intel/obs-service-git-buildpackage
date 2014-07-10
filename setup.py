#!/usr/bin/python
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
"""Setup script"""

from setuptools import setup


def tag_from_spec(tag):
    """Get value of an rpm tag from the spec file"""
    with open('packaging/obs-service-git-buildpackage.spec', 'r') as spec:
        for line in spec.readlines():
            if line.lower().startswith(tag.lower() + ':'):
                return line.split(':', 1)[1].strip()
    raise Exception("ERROR: unable to parse '%s' from spec file" % tag)

setup(name='obs_service_gbp',
      version=tag_from_spec('Version'),
      description=tag_from_spec('Summary'),
      author='Markus Lehtonen',
      author_email='markus.lehtonen@linux.intel.com',
      url=tag_from_spec('URL'),
      license=tag_from_spec('License'),
      packages=['obs_service_gbp', 'obs_service_gbp_utils', 'gbp_repocache',
                'repocache_adm'],
      data_files=[('/usr/lib/obs/service', ['service/git-buildpackage',
                    'service/git-buildpackage.service']),
                  ('/etc/obs/services', ['config/git-buildpackage'])],
      entry_points={
          'console_scripts': ['repocache-adm = repocache_adm.adm:main']
          }
     )
