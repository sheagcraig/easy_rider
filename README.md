![Why don't you cut your hair?](http://cdn.silodrome.com/wp-content/uploads/2015/07/Easy-Rider-Movie.jpg)

```
usage: easy_rider.py [-h] [-o OVERRIDE_DIR]
                     [-l RECIPE_LIST | -r RECIPES [RECIPES ...]]
                     [-k KEYS [KEYS ...]] [-p PKGINFO]

Create an override for each recipe listed in an Autopkg recipe-list. or a
supplied list of recipe identifiers. (Defaults to current user's AutoPkgr
recipe_list) . The 'Input' will be renamed to 'Input_Original', and a new
'Input' section will be populated with metadata from the most current
production version of that product, followed by metadata from the
'Input_Original' for any blank values. Finally, (optionally with
-p/--pkginfo), a plist of values is added to the 'Input' 'pkginfo' key.

optional arguments:
  -h, --help            show this help message and exit
  -o OVERRIDE_DIR, --override-dir OVERRIDE_DIR
                        Path to a location other than your autopkg override-
                        dir to save overrides.
  -l RECIPE_LIST, --recipe-list RECIPE_LIST
                        Path to a recipe list. If not specified, defaults to
                        use AutoPkgr's recipe_list at ~/Library/Application
                        Support/AutoPkgr.
  -r RECIPES [RECIPES ...], --recipes RECIPES [RECIPES ...]
                        One or more recipe identifiers for which to create
                        overrides.
  -k KEYS [KEYS ...], --keys KEYS [KEYS ...]
                        Input metadata key names (may specify multiple values)
                        to copy from newest production version to 'Input'.
                        Defaults to: ('category', 'description', 'developer',
                        'display_name', 'MUNKI_REPO_SUBDIR')
  -p PKGINFO, --pkginfo PKGINFO
                        Path to a plist file defining override values to
                        enforce. This plist should have a top-level dict
                        element named 'pkginfo'.

Please see the README for use examples and further description.
```

More information forthcoming.
