"""Small offline Draft 2020-12 *subset* checker for the bundled M2 schema.

Handles the keywords actually used by the M2 schema (not a general JSON Schema
implementation). No dependency and no false claim that arbitrary JSON Schemas
are supported. Future schema keywords must be added here before use.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib.resources import files

@lru_cache(maxsize=1)
def schema():
    return json.loads(files("royalty_research").joinpath("schemas/m2_extraction.schema.json").read_text(encoding="utf-8"))


def validate_shape(data):
    root = schema()
    problems=[]

    def walk(value,rule,path):
        if "$ref" in rule:
            address=rule["$ref"]
            if not address.startswith("#/$defs/"):
                problems.append(f"{path}: unsupported schema reference")
                return
            walk(value,root["$defs"][address.rsplit("/",1)[-1]],path)
            return
        if "const" in rule and value != rule["const"]:
            problems.append(f"{path}: const mismatch")
        if "enum" in rule and value not in rule["enum"]:
            problems.append(f"{path}: value not permitted by enum")
        ts=rule.get("type",[])
        if isinstance(ts,str):ts=[ts]
        def matches(t):
            return (t=="null" and value is None or t=="string" and isinstance(value,str) or
                    t=="integer" and type(value) is int or t=="object" and isinstance(value,dict) or
                    t=="array" and isinstance(value,list))
        if ts and not any(matches(t) for t in ts):
            problems.append(f"{path}: wrong type");return
        if isinstance(value,str):
            if len(value)<rule.get("minLength",0):problems.append(f"{path}: too short")
            if "pattern" in rule and not re.fullmatch(rule["pattern"],value):problems.append(f"{path}: pattern mismatch")
        if type(value) is int and "minimum" in rule and value<rule["minimum"]:
            problems.append(f"{path}: below minimum")
        if isinstance(value,list) and "items" in rule:
            for i,x in enumerate(value):walk(x,rule["items"],f"{path}[{i}]")
        if isinstance(value,dict):
            required=rule.get("required",[])
            for k in required:
                if k not in value:problems.append(f"{path}.{k}: missing required field")
            props=rule.get("properties",{})
            for k,v in value.items():
                child=props.get(k)
                if child is None:
                    ap=rule.get("additionalProperties",True)
                    if ap is False:problems.append(f"{path}.{k}: unexpected field")
                    elif isinstance(ap,dict):walk(v,ap,f"{path}.{k}")
                else:walk(v,child,f"{path}.{k}")
    walk(data,root,"$")
    return problems
