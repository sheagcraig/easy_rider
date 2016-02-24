#!/usr/bin/python
# Copyright 2016 Shea G. Craig
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
#
# See the License for the specific language governing permissions and
# limitations under the License.

"""Create an override for each recipe in current user's AutoPkgr
recipe_list, and prompt for supplied values.
"""


import argparse
from distutils.version import LooseVersion
import fcntl
import os
import select
import subprocess
from subprocess import check_output, STDOUT
import sys

import FoundationPlist


PKGINFO_EXTENSIONS = (".pkginfo", ".plist")
SEPARATOR = 20 * "-"


def main():
    """Handle arguments and execute commands."""
    args = get_argument_parser().parse_args()
    autopkg_prefs = FoundationPlist.readPlist(
        os.path.expanduser("~/Library/Preferences/com.github.autopkg.plist"))
    RECIPE_OVERRIDE_DIRS = autopkg_prefs["RECIPE_OVERRIDE_DIRS"]
    MUNKI_REPO = autopkg_prefs.get("MUNKI_REPO")

    # repo_data = build_pkginfo_cache(MUNKI_REPO)
    production_cat = FoundationPlist.readPlist(
        os.path.join(MUNKI_REPO, "catalogs/production"))

    if args.pkginfo:
        pkginfo_template = FoundationPlist.readPlist(
            os.path.expanduser(args.pkginfo))["pkginfo"]

    recipe_list_path = os.path.expanduser(
        "~/Library/Application Support/AutoPkgr/recipe_list.txt")
    with open(recipe_list_path) as recipe_list:
        recipes = [recipe.strip() for recipe in recipe_list]

    # TODO: Only does two recipes for testing.
    for recipe in recipes[:2]:
        print "Making override for %s" % recipe
        command = ["/usr/local/bin/autopkg", "make-override", recipe]
        if args.override_dir:
            command.insert(2, "--override-dir=%s" %
                           os.path.realpath(args.override_dir))
        # autopkg will offer to search for missing recipes, and wait for
        # input. Therefore, we use a short timeout to just skip any
        # recipes that are (probably) hung up on the prompt.
        proc = Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE)
        try:
            output, error = proc.communicate(timeout=3)
        except TimeoutError:
            print "\tPlease ensure you have the recipe file for %s." % recipe
            print SEPARATOR
            continue

        failure_string = "An override plist already exists at"
        if failure_string in error:
            print "\t" + error.strip()
            print SEPARATOR
            continue

        override_path = output[output.find("/"):].strip()

        # Rename just-generated override's Input section to Input_Old, unless
        # preserve argument used (and then just copy?).
        # preserve argument is low priority.
        override = FoundationPlist.readPlist(override_path)
        override["Input_Original"] = override["Input"]
        override["Input"] = {}

        # Get most current production version.
        current_version = get_current_production_version(
            production_cat, override)
        print "\tUsing metadata values from {} version {}.".format(
            current_version["name"], current_version["version"])

        # Get important metadata from most current production version
        # falling back to override's original values.
        keys = ("category", "description", "developer", "display_name",
                "MUNKI_REPO_SUBDIR")
        for key in keys:
            current_val = current_version.get(key)
            if current_val:
                override["Input"][key] = current_val
            else:
                override["Input"][key] = override[
                    "Input_Original"].get(key, "")

        # Enforce pkginfo template on new input section.

        # if pkginfo_template:
        #     override_data = FoundationPlist.readPlist(override)
        #     override_data["Input"]["pkginfo_old"] = override_data["Input"].get("pkginfo", {})
        #     override_data["Input"]["pkginfo"] = dict(pkginfo_template)
        #     for key in override_data["Input"]["pkginfo_old"]:
        #         if pkginfo_template.get(key) is None:
        #             override_data["Input"]["pkginfo"][key] = (
        #                 override_data["Input"]["pkginfo_old"][key])

        # Write override.
        print FoundationPlist.writePlistToString(override)


def get_argument_parser():
    """Create our argument parser."""
    description = ("Create an override for each recipe listed in current "
                   "user's AutoPkgr recipe_list. Optionally, prompt for "
                   "values for keys specified with the keys option.")
    parser = argparse.ArgumentParser(description=description)
    arg_help = ("Path to a munki pkginfo plist to include in each override. "
                "Existing pkginfo value will be renamed to "
                "'pkginfo-original'.")
    parser.add_argument("-p", "--pkginfo", help=arg_help)
    arg_help = ("Path to a location other than your autopkg override-dir "
                "to save overrides.")
    parser.add_argument("-o", "--override-dir", help=arg_help)

    # arg_help = "List of INPUT keys to prompt for override values."
    # parser.add_argument("-k", "--keys", help=arg_help)
    # arg_help = ("Drop any keys not specified in the '-k/--keys' argument. "
    #             "This can help prevent overrides from freezing changes to the "
    #             "parent recipe.")
    # parser.add_argument("-d", "--delete-other-keys", help=arg_help,
    #                     action="store_true")
    return parser


def get_override_name(identifier):
    """Use autopkg info to determine the filename for the override."""
    pass


def build_pkginfo_cache(repo):
    """Build a dictionary of pkgsinfo.

    Args:
        repo: String path to the base of a Munki repo.

    Returns:
        Dictionary of pkgsinfo with:
            key: path to pkginfo
            val: pkginfo dictionary
    """
    pkginfos, _ = build_pkginfo_cache_with_errors(repo)
    return pkginfos


def build_pkginfo_cache_with_errors(repo):
    """Build a dictionary of pkgsinfo.

    Args:
        repo: String path to the base of a Munki repo.

    Returns:
        Tuple of:
            Dictionary of pkgsinfo with:
                key: path to pkginfo.
                val: pkginfo dictionary.
            Dictionary of errors with:
                key: path to pkginfo.
                val: Exception message.

    """
    pkginfos = {}
    errors = {}
    pkginfo_dir = os.path.join(repo, "pkgsinfo")
    for dirpath, _, filenames in os.walk(pkginfo_dir):
        for ifile in filter(is_pkginfo, filenames):
            path = os.path.join(dirpath, ifile)
            try:
                pkginfo_file = FoundationPlist.readPlist(path)
            except FoundationPlist.FoundationPlistException as error:
                errors[path] = error.message
                next

            pkginfos[path] = pkginfo_file

    return (pkginfos, errors)


def is_pkginfo(candidate):
    return os.path.splitext(candidate)[-1].lower() in PKGINFO_EXTENSIONS


def get_current_production_version(production_cat, override):
    input_name = override["Input_Original"].get("NAME")
    if not input_name:
        pkginfo = override["Input_Original"].get("pkginfo")
        if pkginfo:
            input_name = pkginfo.get("name")
        # If we haven't found a name yet, we can't look up the product.
        if not input_name:
            return {}

    pkginfos = [item for item in production_cat if item["name"] == input_name]
    return max(pkginfos, key=lambda x: LooseVersion(x["version"]))


class Error(Exception):
    """Class for domain specific exceptions."""


class TimeoutError(Error):
    """Timeout limit exceeded since last I/O."""


def set_file_nonblock(f, non_blocking=True):
    """Set non-blocking flag on a file object.

    Args:
      f: file
      non_blocking: bool, default True, non-blocking mode or not
    """
    flags = fcntl.fcntl(f.fileno(), fcntl.F_GETFL)
    if bool(flags & os.O_NONBLOCK) != non_blocking:
        flags ^= os.O_NONBLOCK
    fcntl.fcntl(f.fileno(), fcntl.F_SETFL, flags)


class Popen(subprocess.Popen):
    """Subclass of subprocess.Popen to add support for timeouts."""

    def timed_readline(self, f, timeout):
        """Perform readline-like operation with timeout.

        Args:
            f: file object to .readline() on
            timeout: int, seconds of inactivity to raise error at
        Raises:
            TimeoutError, if timeout is reached
        """
        set_file_nonblock(f)

        output = []
        inactive = 0
        while 1:
            (rlist, dummy_wlist, dummy_xlist) = select.select(
                [f], [], [], 1.0)

            if not rlist:
                inactive += 1  # approx -- py select doesn't return tv
                if inactive >= timeout:
                    break
            else:
                inactive = 0
                c = f.read(1)
                output.append(c)  # keep newline
                if c == '' or c == '\n':
                    break

        set_file_nonblock(f, non_blocking=False)

        if inactive >= timeout:
            raise TimeoutError  # note, an incomplete line can be lost
        else:
            return ''.join(output)

    def communicate(self, std_in=None, timeout=0):
        """Communicate, optionally ending after a timeout of no activity.

        Args:
            std_in: str, to send on stdin
            timeout: int, seconds of inactivity to raise error at
        Returns:
            (str or None, str or None) for stdout, stderr
        Raises:
            TimeoutError, if timeout is reached
        """
        if timeout <= 0:
            return super(Popen, self).communicate(input=std_in)

        fds = []
        stdout = []
        stderr = []

        if self.stdout is not None:
            set_file_nonblock(self.stdout)
            fds.append(self.stdout)
        if self.stderr is not None:
            set_file_nonblock(self.stderr)
            fds.append(self.stderr)

        if std_in is not None and sys.stdin is not None:
            sys.stdin.write(std_in)

        returncode = None
        inactive = 0
        while returncode is None:
            (rlist, dummy_wlist, dummy_xlist) = select.select(
                fds, [], [], 1.0)

            if not rlist:
                inactive += 1
                if inactive >= timeout:
                    raise TimeoutError
            else:
                inactive = 0
                for fd in rlist:
                    if fd is self.stdout:
                        stdout.append(fd.read())
                    elif fd is self.stderr:
                        stderr.append(fd.read())

            returncode = self.poll()

        if self.stdout is not None:
            stdout = ''.join(stdout)
        else:
            stdout = None
        if self.stderr is not None:
            stderr = ''.join(stderr)
        else:
            stderr = None

        return (stdout, stderr)


if __name__ == "__main__":
    main()
