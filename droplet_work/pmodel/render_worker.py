"""pmodel.render_worker — headless Blender HD render worker (runs ON THE GPU BOX).

NOT imported by caller.py — the API box has no `bpy` dependency. Install on a GPU
machine in a Python venv whose version EXACTLY matches the bpy release
(bpy 5.x -> Python 3.13, 4.x -> 3.11, 3.6 -> 3.10):

    sudo apt-get install -y libxrender1 libxi6 libxxf86vm1 libxfixes3 libxkbcommon0 \
        libgl1 libsm6 libice6 libxrandr2 libfontconfig1 xz-utils python3.13 python3.13-venv
    python3.13 -m venv /opt/blenderenv && /opt/blenderenv/bin/pip install bpy boto3
    # systemd: XDG_RUNTIME_DIR=/tmp /opt/blenderenv/bin/python -m pmodel.render_worker

It polls HDRENDER_QUEUE_DIR for `{job}.json` (written by pmodel.hdrender on the API
box, via a shared/synced dir), renders a Cycles PNG (OptiX GPU when available), uploads
to Spaces, and writes `{job}.done`. Job coords are already Blender (Z-up).
"""
import glob
import json
import math
import os
import sys
import time

import bpy  # import FIRST (before mathutils/gpu)
from mathutils import Euler, Vector

QUEUE = os.environ.get("HDRENDER_QUEUE_DIR", "/srv/hdrender/queue")
OUT = os.environ.get("HDRENDER_OUT_DIR", "/tmp")
SAMPLES = int(os.environ.get("HDRENDER_SAMPLES", "128"))
RES = (os.environ.get("HDRENDER_RES", "1920x1080") or "1920x1080").split("x")
DEVICE = (os.environ.get("HDRENDER_DEVICE", "OPTIX") or "OPTIX").upper()


def _material(name, rgb):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = 0.55
    return m


def _enable_gpu():
    if DEVICE == "CPU":
        return False
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = DEVICE  # OPTIX | CUDA | HIP | ONEAPI | METAL
    prefs.get_devices()  # MUST call to populate
    found = False
    for d in prefs.devices:
        d.use = (d.type != "CPU")
        found = found or (d.type != "CPU")
    return found


def render_job(job: dict, png_path: str):
    bpy.ops.wm.read_factory_settings(use_empty=True)  # clean slate (module loads a default scene)
    scene = bpy.context.scene

    for i, b in enumerate(job.get("boxes", [])):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=b.get("pos", [0, 0, 0]))
        o = bpy.context.active_object
        sx, sy, sz = b.get("size", [1, 1, 1])
        o.scale = (max(sx, 0.001) / 2, max(sy, 0.001) / 2, max(sz, 0.001) / 2)  # cube size=1 -> half-extents
        rot = float(b.get("rot", 0.0) or 0.0)
        if rot:
            o.rotation_euler = Euler((0.0, 0.0, rot), "XYZ")
        o.data.materials.append(_material(f"m{i}", b.get("color", [0.8, 0.8, 0.8])))

    # ground
    bpy.ops.mesh.primitive_plane_add(size=120, location=(0, 0, 0))
    bpy.context.active_object.data.materials.append(_material("ground", [0.2, 0.2, 0.22]))

    # lights: key sun + soft area fill
    sd = bpy.data.lights.new("Sun", "SUN")
    sd.energy = 3.2
    su = bpy.data.objects.new("Sun", sd)
    scene.collection.objects.link(su)
    su.rotation_euler = (math.radians(52), 0, math.radians(40))
    ad = bpy.data.lights.new("Fill", "AREA")
    ad.energy = 800
    ad.size = 8
    fa = bpy.data.objects.new("Fill", ad)
    scene.collection.objects.link(fa)
    fa.location = (6, -6, 8)

    # camera aimed at origin
    cd = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cd)
    scene.collection.objects.link(cam)
    cam.location = Vector(job.get("camera", [9, -9, 7]))
    cam.rotation_euler = (Vector((0, 0, 0.6)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam

    # render settings: Cycles (+GPU when available)
    scene.render.engine = "CYCLES"
    scene.cycles.samples = SAMPLES
    scene.render.resolution_x, scene.render.resolution_y = int(RES[0]), int(RES[1])
    scene.render.image_settings.file_format = "PNG"
    scene.cycles.device = "GPU" if _enable_gpu() else "CPU"
    scene.render.filepath = png_path
    bpy.ops.render.render(write_still=True)


def _upload(path, key):
    import boto3

    s3 = boto3.client(
        "s3",
        region_name=os.environ["AIM_SPACES_REGION"],
        endpoint_url=os.environ["AIM_SPACES_ENDPOINT"],
        aws_access_key_id=os.environ["AIM_SPACES_KEY"],
        aws_secret_access_key=os.environ["AIM_SPACES_SECRET"],
    )
    with open(path, "rb") as f:
        s3.put_object(Bucket=os.environ["AIM_SPACES_BUCKET"], Key=key, Body=f.read(), ContentType="image/png")


def loop():
    os.makedirs(OUT, exist_ok=True)
    while True:
        for jf in sorted(glob.glob(os.path.join(QUEUE, "*.json"))):
            done = jf[:-5] + ".done"
            if os.path.exists(done):
                continue
            try:
                job = json.load(open(jf))
                png = os.path.join(OUT, job["id"] + ".png")
                render_job(job, png)
                _upload(png, job["result_key"])
                json.dump({"ok": True, "ts": time.time()}, open(done, "w"))
            except Exception as e:  # noqa: BLE001
                json.dump({"ok": False, "error": str(e)[:300]}, open(done, "w"))
        time.sleep(2)


if __name__ == "__main__":
    if len(sys.argv) == 4:  # one-shot: render_worker.py job.json out.png result_key
        j = json.load(open(sys.argv[1]))
        render_job(j, sys.argv[2])
        _upload(sys.argv[2], sys.argv[3])
    else:
        loop()
