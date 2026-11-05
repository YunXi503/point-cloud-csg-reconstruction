from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import bpy
import bmesh


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(argv) != 2:
        raise SystemExit("usage: blender --background file.blend --python script.py -- mesh.stl manifest.json")
    output_stl, output_manifest = (Path(value) for value in argv)
    target = bpy.context.view_layer.objects.active
    if target is None or target.type != "MESH":
        raise RuntimeError("Blend active object is not a mesh.")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = target.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    working = bmesh.new()
    working.from_mesh(mesh)
    bmesh.ops.triangulate(working, faces=working.faces[:])
    working.faces.ensure_lookup_table()
    matrix = evaluated.matrix_world
    output_stl.parent.mkdir(parents=True, exist_ok=True)
    with output_stl.open("w", encoding="ascii", newline="\n") as stream:
        stream.write("solid evaluated_mesh\n")
        for face in working.faces:
            normal = face.normal.normalized()
            stream.write(f"  facet normal {normal.x:.17g} {normal.y:.17g} {normal.z:.17g}\n")
            stream.write("    outer loop\n")
            for vertex in face.verts:
                world = matrix @ vertex.co
                stream.write(f"      vertex {world.x:.17g} {world.y:.17g} {world.z:.17g}\n")
            stream.write("    endloop\n")
            stream.write("  endfacet\n")
        stream.write("endsolid evaluated_mesh\n")
    manifest = {
        "blend_file": bpy.data.filepath,
        "active_object": target.name,
        "source_vertices": len(target.data.vertices),
        "source_polygons": len(target.data.polygons),
        "evaluated_vertices": len(mesh.vertices),
        "triangulated_faces": len(working.faces),
        "output_mesh": output_stl.name,
        "output_sha256": sha256(output_stl),
        "scope": "evaluated active mesh only; SamplePoints and NormalsLines are not exported",
    }
    output_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    working.free()
    evaluated.to_mesh_clear()


if __name__ == "__main__":
    main()
