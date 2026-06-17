#****************************************************************************
#* out.py -- the `dfm-out` helper CLI
#*
#* Copyright 2023-2026 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may
#* not use this file except in compliance with the License.
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software
#* distributed under the License is distributed on an "AS IS" BASIS,
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#* See the License for the specific language governing permissions and
#* limitations under the License.
#*
#****************************************************************************
"""``dfm-out`` -- a thin argv -> append-only-file writer for shell tasks.

Scripts run inside a DFM shell task can hand structured results back to the
graph without writing JSON by hand::

    dfm-out fileset --filetype verilogSource gen.sv pkg.sv
    dfm-out env  SIM_SEED=42
    dfm-out path /opt/tools/bin
    dfm-out error "synthesis failed" --file top.sv --line 10
    dfm-out item --type my_pkg.Report key=val n:=3     # n:= => JSON-typed value

Each verb reads the destination path from the ``DFM_*`` env var the runner
exported and appends one line.  Scripts may always fall back to raw
``echo >> "$DFM_OUTPUT"``.  Run outside a DFM task (env var unset) -> non-zero
exit with a clear message.
"""
import argparse
import json
import os
import sys
from typing import List, Optional


def _append_line(env_var: str, line: str) -> int:
    """Append one line to the file named by ``env_var``. Returns an exit code."""
    path = os.environ.get(env_var)
    if not path:
        sys.stderr.write(
            "dfm-out: $%s is not set -- are you running inside a DFM shell task?\n"
            % env_var)
        return 2
    with open(path, "a") as fp:
        fp.write(line)
        if not line.endswith("\n"):
            fp.write("\n")
    return 0


def _parse_kv(items: List[str]) -> dict:
    """Parse k=v (string) and k:=v (JSON-typed) tokens into a dict."""
    out = {}
    for tok in items:
        if ":=" in tok:
            k, v = tok.split(":=", 1)
            out[k] = json.loads(v)
        elif "=" in tok:
            k, v = tok.split("=", 1)
            out[k] = v
        else:
            raise ValueError("expected key=value or key:=json, got %r" % tok)
    return out


def _cmd_fileset(args) -> int:
    item = {"type": "std.FileSet"}
    if args.filetype:
        item["filetype"] = args.filetype
    item["basedir"] = args.basedir
    item["files"] = list(args.files)
    if args.incdir:
        item["incdirs"] = list(args.incdir)
    return _append_line("DFM_OUTPUT", json.dumps(item, separators=(",", ":")))


def _cmd_item(args) -> int:
    try:
        fields = _parse_kv(args.assignments)
    except ValueError as e:
        sys.stderr.write("dfm-out item: %s\n" % e)
        return 2
    item = {"type": args.type}
    item.update(fields)
    return _append_line("DFM_OUTPUT", json.dumps(item, separators=(",", ":")))


def _cmd_env(args) -> int:
    rc = 0
    for tok in args.assignments:
        if "=" not in tok:
            sys.stderr.write("dfm-out env: expected KEY=VALUE, got %r\n" % tok)
            return 2
        rc |= _append_line("DFM_ENV", tok)
    return rc


def _cmd_path(args) -> int:
    rc = 0
    for d in args.dirs:
        rc |= _append_line("DFM_PATH", d)
    return rc


def _cmd_marker(severity: str, args) -> int:
    marker = {"severity": severity, "msg": args.msg}
    if args.file:
        loc = {"path": args.file}
        if args.line is not None:
            loc["line"] = args.line
        if args.pos is not None:
            loc["pos"] = args.pos
        marker["loc"] = loc
    return _append_line("DFM_MARKERS", json.dumps(marker, separators=(",", ":")))


def _add_marker_parser(sub, name):
    p = sub.add_parser(name, help="append a %s marker to $DFM_MARKERS" % name)
    p.add_argument("msg", help="marker message")
    p.add_argument("--file", default=None, help="source file the marker refers to")
    p.add_argument("--line", type=int, default=None, help="line number")
    p.add_argument("--pos", type=int, default=None, help="column/position")
    p.set_defaults(func=lambda a, _sev=name: _cmd_marker(_sev, a))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dfm-out",
        description="Emit data items / env / markers from a DFM shell task.")
    sub = parser.add_subparsers(dest="verb", required=True)

    p_fs = sub.add_parser("fileset", help="append a std.FileSet to $DFM_OUTPUT")
    p_fs.add_argument("--filetype", default=None, help="fileset filetype (e.g. verilogSource)")
    p_fs.add_argument("--basedir", default=".", help="fileset basedir ('.' => rundir)")
    p_fs.add_argument("--incdir", action="append", default=[], help="include directory (repeatable)")
    p_fs.add_argument("files", nargs="+", help="files in the set")
    p_fs.set_defaults(func=_cmd_fileset)

    p_it = sub.add_parser("item", help="append an arbitrary typed item to $DFM_OUTPUT")
    p_it.add_argument("--type", required=True, help="data item type name")
    p_it.add_argument("assignments", nargs="*", help="key=val (string) or key:=json (typed)")
    p_it.set_defaults(func=_cmd_item)

    p_env = sub.add_parser("env", help="append KEY=VALUE lines to $DFM_ENV")
    p_env.add_argument("assignments", nargs="+", help="KEY=VALUE")
    p_env.set_defaults(func=_cmd_env)

    p_path = sub.add_parser("path", help="append directories to $DFM_PATH")
    p_path.add_argument("dirs", nargs="+", help="directories to prepend to PATH")
    p_path.set_defaults(func=_cmd_path)

    for sev in ("error", "warning", "info"):
        _add_marker_parser(sub, sev)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
