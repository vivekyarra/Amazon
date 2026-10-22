"""Render a SYNTHETIC/GENERATED humanoid squat video for pose-verifier fixtures.

The figure is ray-traced from 3D capsules/ellipsoids (skin, clothing, face features) and
posed by forward kinematics. Every rep is generated from its own seeded parameters
(depth, tempo, sway, arm raise), every frame has fresh sensor noise, and nothing is
looped or copied between reps. The output is NOT a recording of a person and NOT a Ring
recording; it exists so the real MediaPipe pose engine has physically complete
movements to process. Counts are never written here; they come only from pose inference.

Usage:
  python scripts/generate-synthetic-squats.py --plan full15 --output out.mp4
Plans: full15 (15 full reps), half15 (15 half-squats), full14 (first 14 reps of full15).
"""

import argparse
import json
import math
import subprocess
from pathlib import Path

import numpy as np

np.seterr(invalid="ignore", divide="ignore")

W, H, FPS = 960, 720, 15
SKIN, SHIRT, SHORTS = (0.86, 0.64, 0.50), (0.15, 0.38, 0.70), (0.16, 0.16, 0.20)
SHOE, HAIR, EYE, LIP = (0.92, 0.92, 0.95), (0.18, 0.11, 0.07), (0.06, 0.05, 0.05), (0.62, 0.32, 0.30)


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def skeleton(flex, arm, yaw, sway, stance=0.24, toe_out=(1.1, 0.4), hip_width=0.19):
    """Return body primitives for knee flexion `flex` (radians, 0 = standing)."""
    # Ankles dorsiflex ~45 deg at the bottom; the rest is hip travel, so full reps finish with
    # thighs about parallel, hips back and the torso leaning forward over the feet.
    shin_tilt = 0.36 * flex
    thigh_tilt = flex - shin_tilt
    lean = 0.10 + 0.55 * thigh_tilt
    shin, thigh, torso = 0.43, 0.45, 0.50
    body = rot_y(yaw)

    def world(p):
        return body @ np.array(p, float) + np.array([sway, 0.0, 0.0])

    parts = []
    hips, knees, ankles = [], [], []
    for side in (-1, 1):
        ankle = np.array([stance * side, 0.085, 0.0])
        # Wide stance: feet and knees turn out together and track over the toes; hips stay
        # level. toe_out is (left-of-screen leg, right-of-screen leg); with the body yawed the
        # turn-out is uneven so both knees present a similar, clearly bent angle to the camera.
        turn = rot_y(side * toe_out[side > 0])
        knee = ankle + turn @ np.array([0.0, shin * math.cos(shin_tilt), shin * math.sin(shin_tilt)])
        hip = knee + turn @ np.array([0.0, thigh * math.cos(thigh_tilt), -thigh * math.sin(thigh_tilt)])
        hip[0] = hip_width * side
        toe = ankle + turn @ np.array([0.0, -0.05, 0.16])
        hips.append(hip)
        knees.append(knee)
        ankles.append(ankle)
        parts += [
            ("cap", world(ankle), world(toe), 0.05, SHOE),
            ("cap", world(knee), world(ankle), 0.06, SKIN),
            ("cap", world(hip), world((hip + knee) / 2), 0.092, SHORTS),
            ("cap", world((hip + knee) / 2), world(knee), 0.075, SKIN),
        ]
    pelvis = (hips[0] + hips[1]) / 2
    up = np.array([0.0, math.cos(lean), math.sin(lean)])
    chest = pelvis + up * torso
    neck = chest + up * 0.07 + np.array([0, 0.03, 0])
    head = neck + np.array([0, 0.13, 0.02 + 0.25 * math.sin(lean) * 0.2])
    parts += [
        ("ell", world(pelvis + up * 0.06), body @ rot_x(lean), (0.18, 0.12, 0.12), SHORTS),
        ("ell", world(pelvis + up * 0.30), body @ rot_x(lean), (0.19, 0.25, 0.125), SHIRT),
        ("cap", world(chest), world(neck), 0.058, SKIN),
        ("ell", world(head), body, (0.088, 0.115, 0.098), SKIN),
        ("ell", world(head + np.array([0, 0.035, -0.015])), body, (0.092, 0.095, 0.098), HAIR),
    ]
    for side in (-1, 1):
        parts += [
            ("sph", world(head + np.array([0.034 * side, 0.012, 0.088])), 0.013, EYE),
            ("sph", world(head + np.array([0.034 * side, 0.036, 0.086])), 0.012, HAIR),
            ("sph", world(head + np.array([0.093 * side, -0.005, 0.0])), 0.022, SKIN),
        ]
    parts += [
        ("sph", world(head + np.array([0, -0.012, 0.102])), 0.017, SKIN),
        (
            "cap",
            world(head + np.array([-0.022, -0.055, 0.088])),
            world(head + np.array([0.022, -0.055, 0.088])),
            0.008,
            LIP,
        ),
    ]
    # Arms: raised forward for balance, elbows slightly bent.
    for side in (-1, 1):
        shoulder = chest + np.array([0.19 * side, -0.02, 0])
        d1 = np.array([0.03 * side, -math.cos(arm), math.sin(arm)])
        elbow = shoulder + 0.29 * d1 / np.linalg.norm(d1)
        a2 = arm + 0.25 + 0.2 * (arm > 0.6)
        d2 = np.array([-0.02 * side, -math.cos(a2), math.sin(a2)])
        wrist = elbow + 0.26 * d2 / np.linalg.norm(d2)
        parts += [
            ("sph", world(shoulder), 0.072, SHIRT),
            ("cap", world(shoulder), world(elbow), 0.056, SKIN),
            ("cap", world(elbow), world(wrist), 0.046, SKIN),
            ("sph", world(wrist + d2 / np.linalg.norm(d2) * 0.06), 0.045, SKIN),
        ]
    return parts


class Camera:
    def __init__(self, eye, target, fov):
        self.eye = np.array(eye, float)
        f = np.array(target, float) - self.eye
        f /= np.linalg.norm(f)
        r = np.cross(f, [0, 1, 0])
        r /= np.linalg.norm(r)
        u = np.cross(r, f)
        t = math.tan(math.radians(fov) / 2)
        self.f, self.r, self.u, self.t = f, r, u, t
        ys, xs = np.mgrid[0:H, 0:W]
        px = (2 * (xs + 0.5) / W - 1) * t * W / H
        py = (1 - 2 * (ys + 0.5) / H) * t
        d = f[None, None] + px[..., None] * r + py[..., None] * u
        self.dirs = (d / np.linalg.norm(d, axis=-1, keepdims=True)).reshape(-1, 3)

    def pixels(self, center, radius):
        """Flat pixel indices whose rays may hit a bounding sphere (conservative screen rect)."""
        v = np.asarray(center) - self.eye
        z = v @ self.f
        scale = H / (2 * self.t * z)
        cx = W / 2 + (v @ self.r) * scale
        cy = H / 2 - (v @ self.u) * scale
        rp = radius * scale * 1.25 + 3
        x0, x1 = max(0, int(cx - rp)), min(W, int(cx + rp) + 1)
        y0, y1 = max(0, int(cy - rp)), min(H, int(cy + rp) + 1)
        if x0 >= x1 or y0 >= y1:
            return np.zeros(0, int)
        ys, xs = np.mgrid[y0:y1, x0:x1]
        return (ys * W + xs).ravel()


def hit_sphere(o, d, c, r):
    oc = o - c
    b = d @ oc
    h = b * b - (oc @ oc - r * r)
    t = -b - np.sqrt(np.maximum(h, 0))
    t = np.where(h > 0, t, np.inf)
    p = o + d * t[:, None]
    return t, (p - c) / r


def hit_capsule(o, d, a, b, r):
    ba, oa = b - a, o - a
    baba = ba @ ba
    bard = d @ ba
    baoa = oa @ ba
    rdoa = d @ oa
    oaoa = oa @ oa
    aa = baba - bard * bard
    bb = baba * rdoa - baoa * bard
    cc = baba * oaoa - baoa * baoa - r * r * baba
    h = bb * bb - aa * cc
    safe = np.where(np.abs(aa) < 1e-9, 1e-9, aa)
    t = np.where(h >= 0, (-bb - np.sqrt(np.maximum(h, 0))) / safe, np.inf)
    y = baoa + t * bard
    body_ok = (h >= 0) & (y > 0) & (y < baba)
    t_body = np.where(body_ok, t, np.inf)
    t1, _ = hit_sphere(o, d, a, r)
    t2, _ = hit_sphere(o, d, b, r)
    t = np.minimum(t_body, np.minimum(t1, t2))
    p = o + d * t[:, None]
    proj = np.clip(((p - a) @ ba) / baba, 0, 1)
    n = (p - (a + proj[:, None] * ba)) / r
    return t, n


def hit_ellipsoid(o, d, c, rot, radii):
    radii = np.array(radii)
    lo = (rot.T @ (o - c)) / radii
    ld = (d @ rot) / radii
    a = np.sum(ld * ld, axis=1)
    b = ld @ lo
    cc = lo @ lo - 1
    h = b * b - a * cc
    t = np.where(h > 0, (-b - np.sqrt(np.maximum(h, 0))) / a, np.inf)
    lp = lo + ld * t[:, None]
    n = (lp / radii) @ rot.T
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    return t, n


def render(parts, cam, rng, light):
    o = cam.eye
    d = cam.dirs
    n_pix = d.shape[0]
    depth = np.full(n_pix, np.inf)
    normal = np.zeros((n_pix, 3))
    color = np.zeros((n_pix, 3))
    for part in parts:
        if part[0] == "cap":
            idx = cam.pixels((part[1] + part[2]) / 2, np.linalg.norm(part[2] - part[1]) / 2 + part[3])
            t, n = hit_capsule(o, d[idx], part[1], part[2], part[3])
            col = part[4]
        elif part[0] == "sph":
            idx = cam.pixels(part[1], part[2])
            t, n = hit_sphere(o, d[idx], part[1], part[2])
            col = part[3]
        else:
            idx = cam.pixels(part[1], max(part[3]))
            t, n = hit_ellipsoid(o, d[idx], part[1], part[2], part[3])
            col = part[4]
        closer = (t > 0) & (t < depth[idx])
        sel = idx[closer]
        depth[sel] = t[closer]
        normal[sel] = n[closer]
        color[sel] = col
    hit = np.isfinite(depth)
    # Key light + opposite fill + sky ambient, with a soft highlight from the key.
    light = light / np.linalg.norm(light)
    fill = np.array([-light[0], 0.35, light[2]])
    fill /= np.linalg.norm(fill)
    diffuse = np.clip(normal @ light, 0, 1)
    rim = np.clip(1 - np.abs(np.sum(normal * -d, 1)), 0, 1)
    shade = 0.20 + 0.58 * diffuse + 0.16 * np.clip(normal @ fill, 0, 1) + 0.10 * (0.5 + 0.5 * normal[:, 1])
    shade -= 0.06 * rim
    half = light - d
    half /= np.linalg.norm(half, axis=1, keepdims=True)
    spec = 0.10 * np.clip(np.sum(normal * half, 1), 0, 1) ** 24
    img = np.zeros((n_pix, 3))
    # Background: wall above y=0, wooden floor below, computed from the ray/plane intersections.
    t_floor = np.where(d[:, 1] < -1e-6, -o[1] / np.minimum(d[:, 1], -1e-6), np.inf)
    fp = o + d * t_floor[:, None]
    stripes = 0.5 + 0.5 * np.sin(fp[:, 0] * 18 + np.sin(fp[:, 2] * 3) * 0.6)
    floor = np.array([0.55, 0.40, 0.27]) * (0.82 + 0.12 * stripes[:, None])
    shadow = np.exp(-((fp[:, 0] - 0.0) ** 2 + (fp[:, 2]) ** 2) / 0.18)
    floor *= (1 - 0.35 * shadow)[:, None]
    wall = np.array([0.78, 0.80, 0.76]) * (0.92 + 0.06 * d[:, 1:2])
    img[:] = np.where((t_floor < 9)[:, None], floor, wall)
    img[hit] = color[hit] * shade[hit, None] + spec[hit, None]
    img = img.reshape(H, W, 3)
    img += rng.normal(0, 0.012, img.shape)
    return (np.clip(img, 0, 1)[..., ::-1] * 255).astype(np.uint8)


def ease(x):
    return 0.5 - 0.5 * math.cos(math.pi * min(1, max(0, x)))


def rep_plan(kind, count, seed):
    rng = np.random.default_rng(seed)
    reps = []
    for i in range(count):
        depth = rng.uniform(128, 136) if kind == "full" else rng.uniform(42, 62)
        reps.append(
            dict(
                index=i + 1,
                bottom_flexion_deg=round(float(depth), 2),
                descend_s=round(float(rng.uniform(0.9, 1.3)), 3),
                hold_s=round(float(rng.uniform(0.25, 0.45)), 3),
                ascend_s=round(float(rng.uniform(0.85, 1.2)), 3),
                stand_s=round(float(rng.uniform(0.7, 1.05)), 3),
                yaw_offset_deg=round(float(rng.uniform(-3, 3)), 2),
                sway_m=round(float(rng.uniform(-0.02, 0.02)), 4),
                arm_raise=round(float(rng.uniform(0.85, 1.05)), 3),
            )
        )
    return reps


def timeline(reps, lead_s=1.2):
    """Yield (flexion_rad, arm_rad, yaw_offset_deg, sway_m, rep_index) per output frame."""
    frames = [(0.0, 0.0, 0.0, 0.0, 0)] * int(lead_s * FPS)
    for r in reps:
        bottom = math.radians(r["bottom_flexion_deg"])
        r["start_frame"] = len(frames)
        for phase, dur in (
            ("down", r["descend_s"]),
            ("hold", r["hold_s"]),
            ("up", r["ascend_s"]),
            ("stand", r["stand_s"]),
        ):
            n = max(1, round(dur * FPS))
            if phase == "hold":
                r["bottom_frame"] = len(frames) + n // 2
            if phase == "stand":
                r["end_frame"] = len(frames) + n - 1
            for k in range(n):
                x = (k + 1) / n
                f = {"down": ease(x), "hold": 1.0, "up": 1 - ease(x), "stand": 0.0}[phase]
                frames.append(
                    (
                        bottom * f,
                        1.6 * r["arm_raise"] * f * min(1, bottom / 1.9),
                        r["yaw_offset_deg"] * f,
                        r["sway_m"] * f,
                        r["index"],
                    )
                )
    return frames


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", choices=["full15", "full14", "half15"], required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--yaw", type=float, default=20.0, help="body yaw vs camera (deg); 0 = head-on")
    args = parser.parse_args()
    kind = "half" if args.plan == "half15" else "full"
    reps = rep_plan(kind, 15, args.seed + (1 if kind == "half" else 0))
    if args.plan == "full14":
        reps = reps[:14]
    frames = timeline(reps)
    cam = Camera((0.0, 1.0, 3.9), (0.0, 0.88, 0.0), 31)
    rng = np.random.default_rng(args.seed + 7)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pixel_format",
            "bgr24",
            "-video_size",
            f"{W}x{H}",
            "-framerate",
            str(FPS),
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-metadata",
            "comment=SYNTHETIC/GENERATED humanoid render - not a person, not Ring",
            str(out),
        ],
        stdin=subprocess.PIPE,
    )
    for flex, arm, yaw_off, sway, _ in frames:
        parts = skeleton(flex, arm, math.radians(args.yaw + yaw_off), sway)
        proc.stdin.write(render(parts, cam, rng, np.array([0.3, 0.75, 0.95])).tobytes())
    proc.stdin.close()
    if proc.wait():
        raise SystemExit("ffmpeg encoding failed")
    plan = dict(
        plan=args.plan,
        seed=args.seed,
        yaw_deg=args.yaw,
        fps=FPS,
        size=[W, H],
        frames=len(frames),
        reps=reps,
        provenance="SYNTHETIC",
    )
    out.with_suffix(".plan.json").write_text(json.dumps(plan, indent=2) + "\n", newline="\n")
    print(json.dumps({k: v for k, v in plan.items() if k != "reps"}))


if __name__ == "__main__":
    main()
