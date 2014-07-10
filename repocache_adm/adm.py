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
"""The repocache-adm tool"""

import logging
import sys

from argparse import ArgumentParser

from repocache_adm.cmd_stat import Stat


def parse_args(argv):
    """Command line argument parser"""

    parser = ArgumentParser()
    parser.add_argument('-c', '--cache-dir', required=True,
                        help='Repocache base directory')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Debug output')
    subparsers = parser.add_subparsers()

    # Add subcommands
    for subcommand in (Stat,):
        subcommand.add_subparser(subparsers)

    return parser.parse_args(argv)


def main(argv=None):
    """Main entry point for the command line tool"""
    logging.basicConfig()
    args = parse_args(argv)
    if args.debug:
        logging.root.setLevel(logging.DEBUG)

    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())

