import re
import sys
import traceback
from os import environ
from pathlib import Path
from textwrap import dedent
from typing import Dict, ItemsView, Optional

import click
from lxml import etree  # type: ignore
from lxml.builder import E  # type: ignore
from lxml.etree import _Element  # type: ignore

from .layout import KeyboardLayout


def xdg_config_home() -> Path:
    xdg_config = environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config)
    return Path.home() / ".config"


def wayland_running() -> bool:
    xdg_session = environ.get("XDG_SESSION_TYPE")
    if xdg_session:
        return xdg_session.startswith("wayland")
    return False


XKB_HOME = xdg_config_home() / "xkb"
XKB_ROOT = Path(environ.get("XKB_CONFIG_ROOT") or "/usr/share/X11/xkb/")

WAYLAND = wayland_running()

LayoutName = str
LocaleName = str
Variant = Dict[LayoutName, Optional[KeyboardLayout]]
Index = Dict[LocaleName, Variant]


class XKBManager:
    """Wrapper to list/add/remove keyboard drivers to XKB."""

    def __init__(self, root: bool = False) -> None:
        self._as_root = root
        self._rootdir = XKB_ROOT if root else XKB_HOME
        self._index: Index = {}

    @property
    def index(self) -> ItemsView[LocaleName, Variant]:
        return self._index.items()

    @property
    def path(self) -> Path:
        return self._rootdir

    def add(self, layout: KeyboardLayout) -> None:
        locale = layout.meta["locale"]
        variant = layout.meta["variant"]
        if locale not in self._index:
            self._index[locale] = {}
        self._index[locale][variant] = layout

    def remove(self, locale: str, variant: str) -> None:
        if locale not in self._index:
            self._index[locale] = {}
        self._index[locale][variant] = None

    def update(self) -> None:
        update_rules(self._rootdir, self._index)  # XKB/rules/{base,evdev}.xml
        update_symbols(self._rootdir, self._index)  # XKB/symbols/{locales}
        self._index = {}

    def clean(self) -> None:
        """Drop the obsolete 'type' attributes Kalamine used to add."""
        for filename in ["base.xml", "evdev.xml"]:
            filepath = self._rootdir / "rules" / filename
            if not filepath.exists():
                continue
            tree = etree.parse(str(filepath), etree.XMLParser(remove_blank_text=True))
            for variant in tree.xpath("//variant[@type]"):
                variant.attrib.pop("type")

    def list(self, mask: str = "") -> Index:
        layouts = list_rules(self._rootdir, mask)
        return list_symbols(self._rootdir, layouts)

    def list_all(self, mask: str = "") -> Index:
        return list_rules(self._rootdir, mask)

    def has_custom_symbols(self) -> bool:
        """Check if there is a usable xkb/symbols/custom file."""

        custom_path = self._rootdir / "symbols" / "custom"
        if not custom_path.exists():
            return False

        for filename in ["base.xml", "evdev.xml"]:
            filepath = self._rootdir / "rules" / filename
            if not filepath.exists():
                continue
            tree = etree.parse(str(filepath))
            if tree.xpath('//layout/configItem/name[text()="custom"]'):
                return True

        return False

    def ensure_xkb_config_is_ready(self) -> None:
        """Ensure there is an XKB configuration in user-space."""
        # See xkblayout.py for a more extensive version of this feature:
        # https://gitlab.freedesktop.org/whot/xkblayout

        if self._as_root:
            return

        # ensure all expected directories exist (don't care about 'geometry')
        XKB_HOME.mkdir(exist_ok=True)
        for subdir in ["compat", "keycodes", "rules", "symbols", "types"]:
            (XKB_HOME / subdir).mkdir(exist_ok=True)

        # ensure there are XKB rules
        # (new locales and symbols will be added by XKBManager)
        for ruleset in ["evdev"]:  # add 'base', too?
            # xkb/rules/evdev
            rules = XKB_HOME / "rules" / ruleset
            if not rules.exists():
                rules.write_text(
                    dedent(
                        f"""
                        // Generated by Kalamine
                        // Include the system '{ruleset}' file
                        ! include %S/{ruleset}
                        """
                    )
                )
            # xkb/rules/evdev.xml
            xmlpath = XKB_HOME / "rules" / f"{ruleset}.xml"
            if not xmlpath.exists():
                xmlpath.write_text(
                    dedent(
                        """\
                        <?xml version="1.0" encoding="UTF-8"?>
                        <!DOCTYPE xkbConfigRegistry SYSTEM "xkb.dtd">
                        <!-- Generated by Kalamine -->
                        <xkbConfigRegistry version="1.1">
                            <layoutList/>
                        </xkbConfigRegistry>
                        """
                    )
                )


""" On GNU/Linux, keyboard layouts must be installed in /usr/share/X11/xkb. To
    be able to revert a layout installation, Kalamine marks layouts like this:

    - XKB/symbols/[locale]: layout definitions
        // KALAMINE::[NAME]::BEGIN
        xkb_symbols "[name]" { ... }
        // KALAMINE::[NAME]::END

    Earlier versions of XKalamine used to mark index files as well but recent
    versions of Gnome do not support the custom `type` attribute any more, which
    must be removed:

    - XKB/rules/{base,evdev}.xml: layout references
        <variant type="kalamine">
            <configItem>
                <name>lafayette42</name>
                <description>French (Lafayette42)</description>
            </configItem>
        </variant>

    Even worse, the Lafayette project has released a first installer before
    the XKalamine installer was developed, so we have to handle this situation
    too:

    - XKB/symbols/[locale]: layout definitions
        // LAFAYETTE::BEGIN
        xkb_symbols "lafayette"   { ... }
        xkb_symbols "lafayette42" { ... }
        // LAFAYETTE::END

    - XKB/rules/{base,evdev}.xml: layout references
        <variant type="lafayette">
            <configItem>
                <name>lafayette</name>
                <description>French (Lafayette)</description>
            </configItem>
        </variant>
        <variant type="lafayette">
            <configItem>
                <name>lafayette42</name>
                <description>French (Lafayette42)</description>
            </configItem>
        </variant>

    Consequence: these two Lafayette layouts must be uninstalled together.
    Because of the way they are grouped in symbols/fr, it is impossible to
    remove one without removing the other.
"""


def clean_legacy_lafayette() -> None:
    return


###############################################################################
# Helpers: XKB/symbols
#


LEGACY_MARK = {"begin": "// LAFAYETTE::BEGIN\n", "end": "// LAFAYETTE::END\n"}


def get_symbol_mark(name: str) -> Dict[str, str]:
    return {
        "begin": "// KALAMINE::" + name.upper() + "::BEGIN\n",
        "end": "// KALAMINE::" + name.upper() + "::END\n",
    }


def is_new_symbol_mark(line: str) -> Optional[str]:
    if not line.endswith("::BEGIN\n"):
        return None

    if line.startswith("// KALAMINE::"):
        return line[13:-8].lower()  # XXX Kalamine expects lowercase names

    return "lafayette"  # line.startswith("// LAFAYETTE::"):  # obsolete marker


def update_symbols_locale(path: Path, named_layouts: Variant) -> None:
    """Update Kalamine layouts in an xkb/symbols/[locale] file."""

    text = ""
    modified_text = False
    with path.open("r+", encoding="utf-8") as symbols:
        # look for Kalamine layouts to be updated or removed
        between_marks = False
        closing_mark = ""
        for line in symbols:
            name = is_new_symbol_mark(line)
            if name:
                if name in named_layouts.keys():
                    closing_mark = line[:-6] + "END\n"
                    modified_text = True
                    between_marks = True
                    text = text.rstrip()
                else:
                    text += line
            elif line.endswith("::END\n"):
                if between_marks and line.startswith(closing_mark):
                    between_marks = False
                    closing_mark = ""
                else:
                    text += line
            elif not between_marks:
                text += line

        # clear previous Kalamine layouts if needed
        if modified_text:
            symbols.seek(0)
            symbols.write(text.rstrip() + "\n")
            symbols.truncate()

        # add new Kalamine layouts
        locale = path.name
        for name, layout in named_layouts.items():
            if layout is None:
                print(f"      - {locale}/{name}")
            else:
                print(f"      + {locale}/{name}")
                mark = get_symbol_mark(name)
                symbols.write("\n")
                symbols.write(mark["begin"])
                symbols.write(
                    re.sub(  # drop lines starting with '//#'
                        r"^//#.*\n", "", layout.xkb_symbols, flags=re.MULTILINE
                    ).rstrip()
                    + "\n"
                )
                symbols.write(mark["end"])

        symbols.close()


def update_symbols(xkb_root: Path, kb_index: Index) -> None:
    """Update Kalamine layouts in all xkb/symbols files."""

    for locale, named_layouts in kb_index.items():
        path = xkb_root / "symbols" / locale
        if not path.exists():
            with path.open("w") as file:
                file.write("// Generated by Kalamine")
                file.close()

        try:
            click.echo(f"... {path}")
            update_symbols_locale(path, named_layouts)

        except Exception as exc:
            exit_FileNotWritable(exc, path)


def list_symbols(xkb_root: Path, kb_index: Index) -> Index:
    """Filter input layouts: only keep the ones defined with Kalamine."""

    filtered_index: Index = {}
    for locale, variants in sorted(kb_index.items()):
        path = xkb_root / "symbols" / locale
        if not path.exists():
            continue

        with open(path, "r", encoding="utf-8") as symbols:
            for line in symbols:
                name = is_new_symbol_mark(line)
                if name is None:
                    continue
                if name in variants.keys():
                    if locale not in filtered_index:
                        filtered_index[locale] = {}
                    filtered_index[locale][name] = variants[name]

    return filtered_index


###############################################################################
# Helpers: XKB/rules
#


def get_rules_locale(tree: etree.ElementTree, locale: LocaleName) -> _Element:
    query = f'//layout/configItem/name[text()="{locale}"]/../..'
    result = tree.xpath(query)
    if len(result) != 1:
        tree.xpath("//layoutList")[0].append(
            E.layout(E.configItem(E.name(locale)), E.variantList())
        )
    return tree.xpath(query)[0]


def remove_rules_variant(variant_list: _Element, name: str) -> None:
    query = f'variant/configItem/name[text()="{name}"]/../..'
    for variant in variant_list.xpath(query):
        variant.getparent().remove(variant)


def add_rules_variant(variant_list: _Element, name: str, description: str) -> None:
    variant_list.append(
        E.variant(E.configItem(E.name(name), E.description(description)))
    )


def update_rules(xkb_root: Path, kb_index: Index) -> None:
    """Update references in XKB/rules/{base,evdev}.xml."""

    for filename in ["base.xml", "evdev.xml"]:
        filepath = xkb_root / "rules" / filename
        if not filepath.exists():
            continue

        try:
            tree = etree.parse(filepath, etree.XMLParser(remove_blank_text=True))

            for locale, named_layouts in kb_index.items():
                vlist = get_rules_locale(tree, locale).xpath("variantList")
                if len(vlist) != 1:
                    exit(f"Error: unexpected xml format in {filepath}.")
                for name, layout in named_layouts.items():
                    remove_rules_variant(vlist[0], name)
                    if layout is not None:
                        description = layout.meta["description"]
                        add_rules_variant(vlist[0], name, description)

            tree.write(
                filepath, pretty_print=True, xml_declaration=True, encoding="utf-8"
            )
            click.echo(f"... {filepath}")

        except Exception as exc:
            exit_FileNotWritable(exc, filepath)


def list_rules(xkb_root: Path, mask: str = "*") -> Index:
    """List all matching XKB layouts."""

    if mask in ("", "*"):
        locale_mask = "*"
        variant_mask = "*"
    else:
        m = mask.split("/")
        if len(m) == 2:
            locale_mask, variant_mask = m
        else:
            locale_mask = mask
            variant_mask = "*"

    kb_index: Index = {}
    for filename in ["base.xml", "evdev.xml"]:
        filepath = xkb_root / "rules" / filename
        if not filepath.exists():
            continue

        tree = etree.parse(filepath)
        for variant in tree.xpath("//variant"):
            locale = variant.xpath("../../configItem/name")[0].text
            name = variant.xpath("configItem/name")[0].text
            desc = variant.xpath("configItem/description")[0].text

            if locale_mask in ("*", locale) and variant_mask in ("*", name):
                if locale not in kb_index:
                    kb_index[locale] = {}
                kb_index[locale][name] = desc

    return kb_index


###############################################################################
# Exception Handling (there must be a better way...)
#


def exit_FileNotWritable(exception: Exception, path: Path) -> None:
    if isinstance(exception, PermissionError):  # noqa: F821
        raise exception
    if isinstance(exception, IOError):
        click.echo("")
        sys.exit(f"Error: could not write to file {path}.")
    else:
        click.echo("")
        sys.exit(f"Error: {exception}.\n{traceback.format_exc()}")
