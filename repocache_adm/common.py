#!/usr/bin/python -u
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
"""Common functionality of the adm module"""


def pprint_sz(size):
    """Pretty print file size in human readable format

    >>> pprint_sz(0)
    '0 bytes'
    >>> pprint_sz(1023)
    '1023 bytes'
    >>> pprint_sz(1024*1024)
    '1.0 MB'
    >>> pprint_sz(1024*1024*1024*(1024 + 512))
    '1.5 TB'
    """
    if size < 1024:
        return "%d bytes" % size

    units = ['kB', 'MB', 'GB', 'TB']
    power = unit = None
    for power, unit in enumerate(units, 2):
        if size < pow(1024, power):
            break
    return "%.1f %s" % (float(size) / pow(1024, power - 1), unit)


class SubcommandBase(object):
    """Base class / API for subcommand implementations"""

    name = None
    description = None
    help_msg = None

    @classmethod
    def add_subparser(cls, subparsers):
        """Add and initialize argparse subparser for the subcommand"""
        parser = subparsers.add_parser(cls.name,
                                       description=cls.description,
                                       help=cls.help_msg)
        cls.add_arguments(parser)
        parser.set_defaults(func=cls.main)

    @classmethod
    def add_arguments(cls, parser):
        """Prototype method for adding subcommand specific arguments"""
        pass

    @classmethod
    def main(cls, args):
        """Prototype entry point for subcommands"""
        raise NotImplementedError("Command %s not implemented" % cls.__name__)

