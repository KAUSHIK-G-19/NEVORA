import { AfterViewInit, Component, ElementRef, OnDestroy, ViewChild } from '@angular/core';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

@Component({ selector: 'app-three-canvas', standalone: true, template: '<div #canvasHost class="canvas-host"><div class="loader"><span></span>Loading twin <b>--</b></div></div>', styles: [':host{display:block;position:absolute;inset:0}.canvas-host{position:absolute;inset:0}.loader{position:absolute;inset:50% auto auto 50%;transform:translate(-50%,-50%);color:#7f9398;font:500 10px/1 "DM Mono",monospace;letter-spacing:.16em;text-transform:uppercase;display:flex;gap:10px;align-items:center;transition:opacity .5s}.loader span{width:8px;height:8px;border:1px solid #9ef01a;border-top-color:transparent;border-radius:50%;animation:spin .8s linear infinite}.loader b{color:#9ef01a;font-weight:400}@keyframes spin{to{transform:rotate(360deg)}}'] })
export class ThreeCanvasComponent implements AfterViewInit, OnDestroy {
  @ViewChild('canvasHost', { static: true }) host!: ElementRef<HTMLDivElement>;
  private renderer!: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera!: THREE.PerspectiveCamera;
  private controls!: OrbitControls;
  private model = new THREE.Group();
  private animationId = 0;
  private pointer = new THREE.Vector2();
  private clock = new THREE.Clock();

  ngAfterViewInit(): void {
    const element = this.host.nativeElement;
    this.scene.fog = new THREE.FogExp2(0x081014, 0.035);
    this.camera = new THREE.PerspectiveCamera(32, element.clientWidth / element.clientHeight, 0.1, 100);
    this.camera.position.set(0.3, 0.25, 5.5);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(element.clientWidth, element.clientHeight);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.25;
    element.appendChild(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true; this.controls.enableZoom = false; this.controls.enablePan = false; this.controls.enabled = false;
    this.addLighting(); this.createFallback(); this.loadModel();
    window.addEventListener('resize', this.resize); window.addEventListener('pointermove', this.move);
    this.animate();
  }

  private addLighting(): void {
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.8));
    const key = new THREE.DirectionalLight(0xffffff, 2); key.position.set(5, 10, 7); key.castShadow = true; this.scene.add(key);
    const rim = new THREE.PointLight(0x00f2fe, 16, 8); rim.position.set(-3, 1.5, -2); this.scene.add(rim);
    const lime = new THREE.PointLight(0x9ef01a, 8, 5); lime.position.set(3, -1, 2); this.scene.add(lime);
  }

  private createFallback(): void {
    const shell = new THREE.Mesh(new THREE.BoxGeometry(2.7, 1.05, 1.65, 5, 3, 5), new THREE.MeshPhysicalMaterial({ color: 0x9ba5a7, metalness: 0.86, roughness: 0.2, clearcoat: 0.5 }));
    shell.castShadow = true; shell.receiveShadow = true; this.model.add(shell);
    const inset = new THREE.Mesh(new THREE.BoxGeometry(2.45, 0.92, 1.4), new THREE.MeshPhysicalMaterial({ color: 0x172326, metalness: 0.9, roughness: 0.3 })); inset.position.y = 0.1; this.model.add(inset);
    const stripe = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.025, 0.025), new THREE.MeshBasicMaterial({ color: 0x9ef01a })); stripe.position.set(0, 0.56, 0.84); this.model.add(stripe);
    const port = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.22, 0.08), new THREE.MeshStandardMaterial({ color: 0x071012, metalness: 0.7 })); port.position.set(-0.85, -0.18, 0.85); this.model.add(port);
    this.model.rotation.set(0.08, -0.42, 0.02); this.model.position.y = 0.05; this.scene.add(this.model);
  }

  private loadModel(): void {
    new GLTFLoader().load('assets/models/nevora_mac_casing.glb', (gltf) => { this.model.clear(); this.model.add(gltf.scene); gltf.scene.traverse((child) => { if (child instanceof THREE.Mesh) { child.castShadow = true; child.receiveShadow = true; } }); }, undefined, () => { /* The procedural casing remains as the offline fallback. */ });
  }

  private animate = (): void => { const elapsed = this.clock.getElapsedTime(); this.model.position.y = Math.sin(elapsed * 1.5) * 0.2; this.model.rotation.y = -0.42 + elapsed * 0.035 + this.pointer.x * 0.08; this.model.rotation.x = 0.08 + this.pointer.y * 0.05; this.controls.update(); this.renderer.render(this.scene, this.camera); this.animationId = requestAnimationFrame(this.animate); };
  private move = (event: PointerEvent): void => { this.pointer.x = (event.clientX / window.innerWidth) * 2 - 1; this.pointer.y = (event.clientY / window.innerHeight) * 2 - 1; };
  private resize = (): void => { const element = this.host.nativeElement; this.camera.aspect = element.clientWidth / element.clientHeight; this.camera.updateProjectionMatrix(); this.renderer.setSize(element.clientWidth, element.clientHeight); };
  ngOnDestroy(): void { cancelAnimationFrame(this.animationId); window.removeEventListener('resize', this.resize); window.removeEventListener('pointermove', this.move); this.renderer.dispose(); }
}
