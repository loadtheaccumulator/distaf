#  This file is part of DiSTAF
#  Copyright (C) 2015-2016  Red Hat, Inc. <http://www.redhat.com>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License along
#  with this program; if not, write to the Free Software Foundation, Inc.,
#  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.


from distaf.util import tc, testcase
from distaf.distaf_base_class import DistafTestClass


@testcase("text_to_stdout_stderr")
class TextToStdoutStderr(DistafTestClass):
    """Run some commands against remote servers to
    test sending data to stdout and stderr.

    To test speed differences, set combinations of...
        use_ssh : True|False
        use_controlpersist : True|False    # requires use_ssh : True
        skip_log_inject : True|False

    Run with...
        time python main.py -d example -t text_to_stdout_stderr
    """
    def setup(self):
        return True

    def run(self):
        retstat = 0
        tc.logger.info("Send load of output to stdout")
        for node in tc.all_nodes:
            command = "for i in $(seq 1 100); do ls -Rail /etc; done"
            rcode, _, _ = tc.run(node, command)
            if rcode != 0:
                retstat = retstat | rcode

        tc.logger.info("Send load of output to stderr")
        for node in tc.all_nodes:
            command = "for i in $(seq 1 100); do ls -Rail /etc >&2; done"
            rcode, _, _ = tc.run(node, command)
            if rcode != 0:
                retstat = retstat | rcode

        if retstat == 0:
            return True

        return False

    def cleanup(self):
        return True

    def teardown(self):
        return True
