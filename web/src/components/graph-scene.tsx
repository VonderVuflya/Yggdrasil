import { t, useI18n } from "../lib/i18n";
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { GraphData, Memory } from "../lib/types";
export default function GraphScene({
  data,
  selectedId,
  onSelect,
  onUnsupported,
  reset,
}: {
  data: GraphData;
  selectedId?: string;
  onSelect: (memory: Memory) => void;
  onUnsupported: () => void;
  reset: number;
}) {
  useI18n();
  const host = useRef<HTMLDivElement>(null);
  const callbacks = useRef({ onSelect, onUnsupported });
  callbacks.current = { onSelect, onUnsupported };
  useEffect(() => {
    if (!host.current) return;
    const container = host.current;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      callbacks.current.onUnsupported();
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    container.append(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 2000);
    camera.position.set(0, 20, 380);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = false;
    controls.minDistance = 60;
    controls.maxDistance = 800;
    const nodes: THREE.Mesh[] = [];
    const position = new Map<string, THREE.Vector3>();
    const geometry = new THREE.SphereGeometry(2.8, 10, 8);
    const normal = new THREE.MeshBasicMaterial();
    const selected = new THREE.MeshBasicMaterial();
    data.nodes.forEach((node, i) => {
      const count = data.nodes.length;
      const y = 1 - ((i + 0.5) / count) * 2;
      const radius = Math.sqrt(1 - y * y);
      const angle = i * 2.399963;
      const p = new THREE.Vector3(
        Math.cos(angle) * radius * 115,
        y * 105,
        Math.sin(angle) * radius * 115,
      );
      position.set(node.id, p);
      const mesh = new THREE.Mesh(
        geometry,
        node.id === selectedId ? selected : normal,
      );
      mesh.position.copy(p);
      if (node.id === selectedId) mesh.scale.setScalar(1.8);
      mesh.userData = { node };
      nodes.push(mesh);
      scene.add(mesh);
    });
    const lineMaterials = [
      new THREE.LineBasicMaterial({
        transparent: true,
        opacity: 0.65,
      }),
      new THREE.LineBasicMaterial({
        transparent: true,
        opacity: 0.65,
      }),
      new THREE.LineBasicMaterial({
        transparent: true,
        opacity: 0.65,
      }),
    ];
    const lineGeometries: THREE.BufferGeometry[] = [];
    for (const edge of data.edges) {
      const a = position.get(edge.from_id),
        b = position.get(edge.to_id);
      if (!a || !b) continue;
      const geo = new THREE.BufferGeometry().setFromPoints([a, b]);
      lineGeometries.push(geo);
      scene.add(
        new THREE.Line(
          geo,
          lineMaterials[
            edge.rel_type === "SUPERSEDES"
              ? 1
              : edge.rel_type === "CONTRADICTS"
                ? 2
                : 0
          ],
        ),
      );
    }
    const render = () => renderer.render(scene, camera);
    const updateColors = () => {
      const styles = getComputedStyle(container);
      const color = (name: string) => styles.getPropertyValue(name).trim();
      normal.color.set(color("--graph-node"));
      selected.color.set(color("--graph-selected"));
      lineMaterials[0].color.set(color("--graph-edge"));
      lineMaterials[1].color.set(color("--warning"));
      lineMaterials[2].color.set(color("--destructive"));
      render();
    };
    updateColors();
    // Update materials in place: changing appearance must not reset the camera.
    window.addEventListener("ygg-theme-changed", updateColors);
    controls.addEventListener("change", render);
    const resize = () => {
      const { width, height } = container.getBoundingClientRect();
      renderer.setSize(width, height);
      camera.aspect = width / Math.max(1, height);
      camera.updateProjectionMatrix();
      render();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let down = { x: 0, y: 0 };
    const onDown = (event: PointerEvent) => {
      down = { x: event.clientX, y: event.clientY };
    };
    const onUp = (event: PointerEvent) => {
      if (Math.hypot(event.clientX - down.x, event.clientY - down.y) > 5)
        return;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        (-(event.clientY - rect.top) / rect.height) * 2 + 1,
      );
      raycaster.setFromCamera(pointer, camera);
      const intersection = raycaster.intersectObjects(nodes)[0];
      if (intersection)
        callbacks.current.onSelect(intersection.object.userData.node as Memory);
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("ygg-theme-changed", updateColors);
      observer.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      geometry.dispose();
      normal.dispose();
      selected.dispose();
      lineMaterials.forEach((m) => m.dispose());
      lineGeometries.forEach((g) => g.dispose());
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [data, selectedId, reset]);
  return (
    <div
      ref={host}
      className="graph-three"
      aria-label={t(
        "3D knowledge graph. For keyboard access, use the records below.",
      )}
      role="img"
    />
  );
}
