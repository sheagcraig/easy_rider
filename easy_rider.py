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

"""easy_rider

Create an override for each recipe listed in an Autopkg recipe-list. or a
supplied list of recipe identifiers. (Defaults to current user's AutoPkgr
recipe_list) . The 'Input' will be renamed to 'Input_Original', and a new
'Input' section will be populated with metadata from the most current
production version of that product, followed by metadata from the
'Input_Original' for any blank values. Finally, (optionally with
-p/--pkginfo), a plist of values is added to the 'Input' 'pkginfo' key.
"""


import argparse
from distutils.version import LooseVersion
import fcntl
import os
import select
import subprocess
import sys

import FoundationPlist


ENDC = "\033[0m"
METADATA = ("category", "description", "developer", "display_name")
PKGINFO_EXTENSIONS = (".pkginfo", ".plist")
SEPARATOR = 20 * "-"


class Error(Exception):
    """Class for domain specific exceptions."""


class TimeoutError(Error):
    """Timeout limit exceeded since last I/O."""


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


def main():
    """Set up arguments and start processing."""
    args = get_argument_parser().parse_args()
    autopkg_prefs = FoundationPlist.readPlist(
        os.path.expanduser("~/Library/Preferences/com.github.autopkg.plist"))
    MUNKI_REPO = autopkg_prefs.get("MUNKI_REPO")
    production_cat = FoundationPlist.readPlist(
        os.path.join(MUNKI_REPO, "catalogs/%s" % args.catalog))
    pkginfo_template = (get_pkginfo_template(args.pkginfo) if args.pkginfo else
                        {})

    recipes = args.recipes if args.recipes else get_recipes(args.recipe_list)
    try:
        process_overrides(recipes, args, production_cat, pkginfo_template)
    except KeyboardInterrupt:
        print_error("Bailing!")
    finally:
        reset_term_colors()


def process_overrides(recipes, args, production_cat, pkginfo_template):
    """Start main processing loop.

    Args:
        recipes (list of str): Recipe names/ids to override.
        production_cat (Plist): Munki's 'production' catalog.
        pkginfo_template (Plist): Template pkginfo settings to apply.
    """
    for recipe in recipes:
        print SEPARATOR
        override_path = make_override(recipe, args.override_dir)
        if override_path is None:
            continue

        # Copy just-generated override's Input section to Input_Original.
        override = FoundationPlist.readPlist(override_path)
        override["Input_Original"] = override["Input"]
        override["Input"] = {}
        override["Input"]["pkginfo"] = {}

        current_version = get_current_production_version(
            production_cat, override)
        if current_version:
            apply_current_or_orig_values(override, current_version, args.keys)
        else:
            print_error("\tUnable to determine product 'name'. Skipping "
                        "copying current production metadata!")

        if pkginfo_template:
            apply_pkginfo_template(override, pkginfo_template)

        FoundationPlist.writePlist(override, override_path)


def get_argument_parser():
    """Create our argument parser."""
    description = (
        "Create an override for each recipe listed in an Autopkg recipe-list. "
        "or a supplied list of recipe identifiers. (Defaults to current "
        "user's AutoPkgr recipe_list) . The 'Input' will be renamed to "
        "'Input_Original', and a new 'Input' section will be populated with "
        "metadata from the most current production version of that product, "
        "followed by metadata from the 'Input_Original' for any blank values. "
        "Finally, (optionally with -p/--pkginfo), a plist of values is added "
        "to the 'Input' 'pkginfo' key.")
    epilog = ("Please see the README for use examples and further "
              "description.")
    parser = argparse.ArgumentParser(description=description, epilog=epilog)
    arg_help = ("Path to a location other than your autopkg override-dir "
                "to save overrides.")
    parser.add_argument("-o", "--override-dir", help=arg_help)

    group = parser.add_mutually_exclusive_group()
    arg_help = ("Path to a recipe list. If not specified, defaults to use "
                "AutoPkgr's recipe_list at "
                "~/Library/Application Support/AutoPkgr.")
    group.add_argument("-l", "--recipe-list", help=arg_help)
    arg_help = "One or more recipe identifiers for which to create overrides."
    group.add_argument("-r", "--recipes", help=arg_help, nargs="+")

    arg_help = ("Input metadata key names (may specify multiple values) to "
                "copy from newest production version to 'Input'. Defaults to: "
                "%(default)s")
    parser.add_argument("-k", "--keys", help=arg_help, nargs="+",
                        default=METADATA)
    arg_help = ("Path to a plist file defining override values to enforce. "
                "This plist should have a top-level dict element named "
                "'pkginfo'. ")
    parser.add_argument("-p", "--pkginfo", help=arg_help)
    arg_help = ("Name of Munki catalog from which to search current pkginfo "
                "values. (Defaults to '%(default)s)'")
    parser.add_argument("-c", "--catalog", help=arg_help, default="production")
    return parser


def get_pkginfo_template(pkginfo_template_path):
    """Return the pkginfo top-level key from a plist file."""
    pkginfo_template = FoundationPlist.readPlist(
        os.path.expanduser(pkginfo_template_path)).get("pkginfo")
    if not pkginfo_template:
        sys.exit("Pkginfo template format incorrect!. Quitting.")
    return pkginfo_template


def get_recipes(recipe_list_path):
    """Return a list of recipes read from a recipe list."""
    autopkgr_path = os.path.expanduser(
        "~/Library/Application Support/AutoPkgr/recipe_list.txt")
    recipe_list_path = recipe_list_path if recipe_list_path else autopkgr_path
    if not os.path.exists(recipe_list_path):
        sys.exit("recipe_list file %s does not exist!" % recipe_list_path)
    with open(recipe_list_path) as recipe_list:
        recipes = [recipe.strip() for recipe in recipe_list if
                   recipe.strip() != "com.github.autopkg.munki.makecatalogs"
                   and not recipe.strip().startswith("local")]
    return recipes


def make_override(recipe, override_dir):
    """Make an override and return its path.

    Args:
        recipe (str): Recipe name.
        override_dir (str): Path in which to create overrides.

    Returns:
        str path to new override, or None for errors or pre-existing
        overrides.
    """
    print "Making override for %s" % recipe
    command = ["/usr/local/bin/autopkg", "make-override", recipe]
    if override_dir:
        command.insert(2, "--override-dir=%s" %
                        os.path.realpath(override_dir))
    # autopkg will offer to search for missing recipes, and wait for
    # input. Therefore, we use a short timeout to just skip any
    # recipes that are (probably) hung up on the prompt.
    proc = Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
    try:
        output, error = proc.communicate(timeout=3)
    except TimeoutError:
        print_error(
            "\tPlease ensure you have the recipe file for %s." % recipe)
        return None

    failure_string = "An override plist already exists at"
    if failure_string in error:
        print_error("\t" + error.strip())
        return None

    return output[output.find("/"):].strip()


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
    return (max(pkginfos, key=lambda x: LooseVersion(x["version"])) if pkginfos
            else {})


def apply_current_or_orig_values(override, current_version, keys):
    """Get important metadata from current or original recipe.

    Args:
        override (Plist): Override plist object.
        current_version (dict): Munki pkginfo dict.
        keys (tuple/list): Metadata keys to consider.
    """
    print "\tUsing metadata values from {} version {}.".format(
        current_version["name"], current_version["version"])
    for key in keys:
        current_val = current_version.get(key)
        if current_val:
            override["Input"]["pkginfo"][key] = current_val
        else:
            override["Input"]["pkginfo"][key] = override[
                "Input_Original"].get("pkginfo", {}).get(key, "")


def apply_pkginfo_template(override, pkginfo_template):
    """Force values from pkginfo_template on override's pkginfo."""
    # Need to "convert" Objc object to dict.
    override["Input"]["pkginfo"].update(dict(pkginfo_template))
    # pkginfo = override["Input"]["pkginfo"]
    # orig_pkginfo  = override["Input_Original"].get("pkginfo", {})
    # for key, val in orig_pkginfo.items():
    #     if key not in pkginfo or pkginfo[key] is None:
    #         pkginfo[key] = orig_pkginfo[key]
    print "\tApplied pkginfo template."


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


def print_error(message):
    print >> sys.stderr, "\033[1;38;5;196m" + message
    print ENDC,


def reset_term_colors():
    """Ensure terminal colors are normal."""
    sys.stdout.write(ENDC)


if __name__ == "__main__":
    main()
