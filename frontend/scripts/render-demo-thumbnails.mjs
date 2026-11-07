/**
 * Renders a gallery thumbnail for each demo part:
 * public/demos/<slug>/thumbnail.webp, from the demo's last version.
 *
 * It copies the studio viewer's look (face and edge colours, lights, the
 * fixed three-quarter camera of ThumbnailCapture, 480×360 WebP), so demo
 * cards match the thumbnails of users' own parts. Run it again after
 * a design in backend/demos/designs/ changes:
 *
 *   PLAYWRIGHT_PATH=$(npm root -g)/playwright node scripts/render-demo-thumbnails.mjs
 *
 * Needs Playwright with Chromium; it is not a project dependency.
 */
import { createReadStream, existsSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { dirname, extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const demosDir = join(frontend, "public", "demos");
// npm workspaces may install three in the frontend or at the repository root.
const threeRoot = [join(frontend, "node_modules", "three"), join(frontend, "..", "node_modules", "three")]
  .find((path) => existsSync(join(path, "build", "three.module.js")));
if (!threeRoot) throw new Error("three is not installed; run npm install first.");

// Keep in step with ViewportPane.tsx and the porcelain --clay colour.
const PAGE = `<!doctype html>
<html><head><meta charset="utf-8">
<script type="importmap">{"imports":{"three":"/three/build/three.module.js","three/addons/":"/three/examples/jsm/"}}</script>
</head><body style="margin:0">
<canvas id="c" width="1200" height="900"></canvas>
<script type="module">
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const canvas = document.getElementById("c");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);

window.renderThumbnail = async (url) => {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#ddd3c2");
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  for (const [position, intensity] of [[[5, 8, 5], 1.2], [[-5, 5, -5], 0.6], [[0, -5, 5], 0.4]]) {
    const light = new THREE.DirectionalLight(0xffffff, intensity);
    light.position.set(...position);
    scene.add(light);
  }
  const gltf = await new GLTFLoader().loadAsync(url);
  const model = gltf.scene;
  model.scale.setScalar(100);
  model.traverse((child) => {
    if (child.isLineSegments) {
      child.material = new THREE.LineBasicMaterial({ color: 0x1b1e24 });
    } else if (child.isMesh && child.material.isMeshStandardMaterial) {
      child.material = child.material.clone();
      child.material.color = new THREE.Color(0x8a93a3);
      child.material.metalness = 0.18;
      child.material.roughness = 0.48;
      child.material.polygonOffset = true;
      child.material.polygonOffsetFactor = 1;
      child.material.polygonOffsetUnits = 1;
    }
  });
  // <Center> in the viewer.
  const centre = new THREE.Box3().setFromObject(model).getCenter(new THREE.Vector3());
  model.position.sub(centre);
  scene.add(model);

  const sphere = new THREE.Box3().setFromObject(model).getBoundingSphere(new THREE.Sphere());
  const shot = new THREE.PerspectiveCamera(35, canvas.width / canvas.height, sphere.radius / 100, sphere.radius * 100);
  const verticalHalf = THREE.MathUtils.degToRad(shot.fov / 2);
  const horizontalHalf = Math.atan(Math.tan(verticalHalf) * shot.aspect);
  const distance = (sphere.radius * 1.15) / Math.sin(Math.min(verticalHalf, horizontalHalf));
  shot.position.copy(sphere.center).add(new THREE.Vector3(1, 0.85, 1).normalize().multiplyScalar(distance));
  shot.lookAt(sphere.center);
  renderer.render(scene, shot);

  const output = document.createElement("canvas");
  output.width = 480;
  output.height = 360;
  output.getContext("2d").drawImage(canvas, 0, 0, 480, 360);
  return output.toDataURL("image/webp", 0.82);
};
window.ready = true;
</script></body></html>`;

const TYPES = { ".js": "text/javascript", ".glb": "model/gltf-binary", ".json": "application/json" };
const server = createServer((request, response) => {
  const path = decodeURIComponent(new URL(request.url, "http://local").pathname);
  if (path === "/") {
    response.writeHead(200, { "content-type": "text/html" }).end(PAGE);
    return;
  }
  const [base, rest] = path.startsWith("/three/")
    ? [threeRoot, path.slice("/three/".length)]
    : [demosDir, path.replace(/^\/demos\//, "")];
  const file = normalize(join(base, rest));
  if (!file.startsWith(base) || !existsSync(file)) {
    response.writeHead(404).end();
    return;
  }
  // Demo models are stored gzipped; serve them as the site does (next.config.ts).
  const headers = file.endsWith(".glb.gz")
    ? { "content-type": "model/gltf-binary", "content-encoding": "gzip" }
    : { "content-type": TYPES[extname(file)] ?? "application/octet-stream" };
  response.writeHead(200, headers);
  createReadStream(file).pipe(response);
});
await new Promise((ready) => server.listen(0, "127.0.0.1", ready));
const origin = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--ignore-gpu-blocklist"] });
try {
  const page = await browser.newPage();
  page.on("pageerror", (error) => console.error("page error:", error.message));
  await page.goto(origin);
  await page.waitForFunction(() => window.ready === true);
  const { demos } = JSON.parse(readFileSync(join(demosDir, "index.json"), "utf8"));
  for (const { slug } of demos) {
    const demo = JSON.parse(readFileSync(join(demosDir, slug, "demo.json"), "utf8"));
    const last = demo.steps[demo.steps.length - 1];
    const dataUrl = await page.evaluate((url) => window.renderThumbnail(url), `/demos/${slug}/${last.glb}`);
    const image = Buffer.from(dataUrl.split(",")[1], "base64");
    writeFileSync(join(demosDir, slug, "thumbnail.webp"), image);
    console.log(`${slug}: thumbnail.webp (${Math.round(image.length / 1024)} KB)`);
  }
} finally {
  await browser.close();
  server.close();
}
