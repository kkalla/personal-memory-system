#!/usr/bin/env python3
"""Validate offline regression fixture structure, never agent behavior (Python 3.9+)."""

import argparse
import json
from pathlib import Path
import re
import sys


CASE_FIELDS = ("id", "coverage", "source_notes", "situation", "prior_memories", "steps")
COVERAGE = {
    "global-preference", "project-constraint", "scope-inference", "unrelated-project",
    "candidate-exclusion", "current-instruction-conflict", "one-off-exception",
    "topic-change", "paraphrased-search", "cross-environment", "no-project-context",
}


def require(condition, path, message):
    if not condition:
        raise ValueError("%s: %s" % (path, message))


def record(value, path, fields):
    require(isinstance(value, dict), path, "expected object")
    for field in fields:
        require(field in value, path + "." + field, "required field missing")
    for field in value:
        require(field in fields, path + "." + field, "unknown field")


def text(value, path):
    require(isinstance(value, str) and bool(value.strip()), path, "expected nonblank string")


def items(value, path, nonempty=True):
    require(isinstance(value, list), path, "expected array")
    require(not nonempty or bool(value), path, "expected nonempty array")
    return [("%s[%d]" % (path, index), item) for index, item in enumerate(value)]


def strings(value, path, nonempty=True):
    for item_path, item in items(value, path, nonempty):
        text(item, item_path)


def project(value, path):
    if value is not None:
        text(value, path)


def choice(value, path, choices):
    text(value, path)
    require(value in choices, path, "expected one of %s" % ", ".join(sorted(choices)))


def boolean(value, path):
    require(type(value) is bool, path, "expected boolean")


def validate(suite):
    record(suite, "suite", ("schema_version", "environments", "cases"))
    require(type(suite["schema_version"]) is int and suite["schema_version"] == 1,
            "schema_version", "expected integer 1")
    strings(suite["environments"], "environments")
    require(sorted(suite["environments"]) == ["claude-code", "codex"],
            "environments", "expected claude-code and codex exactly once")
    seen = set()
    for path, case in items(suite["cases"], "cases"):
        record(case, path, CASE_FIELDS)
        text(case["id"], path + ".id")
        require(re.fullmatch(r"MR-[0-9]{3}", case["id"]) is not None,
                path + ".id", "expected MR-NNN")
        require(case["id"] not in seen, path + ".id", "duplicate case ID")
        seen.add(case["id"])
        for item_path, item in items(case["coverage"], path + ".coverage"):
            choice(item, item_path, COVERAGE)
        for source_path, source in items(case["source_notes"], path + ".source_notes"):
            record(source, source_path, ("filename", "adaptation"))
            text(source["filename"], source_path + ".filename")
            require(re.fullmatch(r"(?:user|feedback|project|reference)_[a-z0-9-]+\.md",
                                 source["filename"]) is not None,
                    source_path + ".filename", "expected source basename, not a path")
            text(source["adaptation"], source_path + ".adaptation")
        situation = case["situation"]
        situation_path = path + ".situation"
        record(situation, situation_path, ("project_id", "context", "task_rules"))
        project(situation["project_id"], situation_path + ".project_id")
        text(situation["context"], situation_path + ".context")
        strings(situation["task_rules"], situation_path + ".task_rules", nonempty=False)
        memory_ids = set()
        for memory_path, memory in items(case["prior_memories"], path + ".prior_memories",
                                         nonempty=False):
            record(memory, memory_path, ("id", "kind", "scope", "status", "project_id",
                                         "scope_inferred", "body"))
            text(memory["id"], memory_path + ".id")
            require(memory["id"] not in memory_ids, memory_path + ".id", "duplicate memory ID")
            memory_ids.add(memory["id"])
            choice(memory["kind"], memory_path + ".kind", {"user", "feedback", "project", "reference"})
            choice(memory["scope"], memory_path + ".scope", {"global", "project"})
            choice(memory["status"], memory_path + ".status", {"confirmed", "candidate"})
            project(memory["project_id"], memory_path + ".project_id")
            boolean(memory["scope_inferred"], memory_path + ".scope_inferred")
            require((memory["scope"] == "project") == (memory["project_id"] is not None),
                    memory_path + ".project_id", "project scope requires ID; global requires null")
            require(not memory["scope_inferred"] or memory["scope"] == "project",
                    memory_path + ".scope_inferred", "inferred scope must stay project-local")
            text(memory["body"], memory_path + ".body")
        for step_path, step in items(case["steps"], path + ".steps"):
            record(step, step_path, ("user_request", "project_id", "topic_changed",
                                     "expected_behaviors", "forbidden_behaviors"))
            text(step["user_request"], step_path + ".user_request")
            project(step["project_id"], step_path + ".project_id")
            boolean(step["topic_changed"], step_path + ".topic_changed")
            strings(step["expected_behaviors"], step_path + ".expected_behaviors")
            strings(step["forbidden_behaviors"], step_path + ".forbidden_behaviors")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, key, "duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("non-finite JSON number: %s" % value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="JSON fixture path (read only)")
    args = parser.parse_args()
    try:
        suite = json.loads(args.path.read_text(encoding="utf-8"),
                           object_pairs_hook=unique_object, parse_constant=reject_constant)
        validate(suite)
    except (OSError, ValueError) as error:
        print("STRUCTURE FAIL: %s" % error, file=sys.stderr)
        return 1
    print("STRUCTURE PASS: %d cases; agent behavior NOT RUN; recall integration NOT RUN"
          % len(suite["cases"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
